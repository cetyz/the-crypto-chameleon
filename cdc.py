import hmac
import hashlib
import time
import copy
import json
import requests
import pandas as pd
from typing import Dict, Any, Optional, Union, List
from urllib.parse import urljoin
import logging

class CryptoComAPI:
    """
    Python wrapper for the Crypto.com Exchange API
    
    Handles authentication, request preparation, and API communication
    with proper error handling and rate limiting.
    """
    
    PRODUCTION_URL = "https://api.crypto.com/exchange/v1/"
    SANDBOX_URL = "https://uat-api.3ona.co/exchange/v1/"
    MAX_RETRIES = 3
    RETRY_DELAY = 0.5  # seconds
    MAX_NESTING_LEVEL = 3  # Maximum level for nested parameters
    
    def __init__(
        self, 
        api_key: str,
        secret_key: str,
        use_sandbox: bool = False,
        timeout: int = 30,
        max_retries: int = 3,
        logger: Optional[logging.Logger] = None
    ):
        """
        Initialize the Crypto.com API client
        
        Args:
            api_key: Your API key
            secret_key: Your API secret key
            use_sandbox: Whether to use the sandbox environment
            timeout: Request timeout in seconds
            max_retries: Maximum number of retries for failed requests
            logger: Custom logger, if None a default logger will be created
        """
        self.api_key = api_key
        self.secret_key = secret_key
        self.base_url = self.SANDBOX_URL if use_sandbox else self.PRODUCTION_URL
        self.timeout = timeout
        self.max_retries = max_retries
        
        # Set up logging
        self.logger = logger if logger else logging.getLogger(__name__)
        if not self.logger.handlers:
            handler = logging.StreamHandler()
            handler.setFormatter(logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s'))
            self.logger.addHandler(handler)
            self.logger.setLevel(logging.INFO)
            
        # Rate limiting tracking
        self._last_request_time = 0
        self._request_count = 0
        
    def _generate_signature(
        self, 
        method: str, 
        request_id: int, 
        params: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        Generate the HMAC-SHA256 signature required for authenticated requests
        Following the exact format from official Crypto.com documentation
        
        Args:
            method: API method being called
            request_id: Unique request identifier
            params: Request parameters
                
        Returns:
            Dict with complete request payload including signature
        """
        # Create nonce (timestamp in milliseconds)
        nonce = int(time.time() * 1000)
        
        # Create the request structure (API key goes at top level, not in params)
        request = {
            "id": request_id,
            "method": method,
            "api_key": self.api_key,
            "params": params,
            "nonce": nonce
        }
        
        # Prepare parameter string for signature using only the params (not including api_key)
        param_str = self._prepare_request_params(params)
        
        # Create the signature payload string
        # Format: method + id + api_key + params_string + nonce (exact order from docs)
        payload_str = method + str(request_id) + self.api_key + param_str + str(nonce)
        self.logger.debug(f"Signature payload: {payload_str}")
        
        # Generate HMAC-SHA256 signature
        signature = hmac.new(
            bytes(self.secret_key, 'utf-8'),
            msg=bytes(payload_str, 'utf-8'),
            digestmod=hashlib.sha256
        ).hexdigest()
        
        # Add signature to the request structure
        request["sig"] = signature
        
        return request
    
    def _prepare_request_params(self, params: Dict[str, Any], level: int = 0) -> str:
        """
        Convert parameters to string format required for signature generation
        Following the exact algorithm from official Crypto.com documentation
        
        Args:
            params: Parameters to be converted
            level: Current nesting level
            
        Returns:
            String representation of parameters
        """
        if level >= self.MAX_NESTING_LEVEL:
            return str(params)
            
        return_str = ""
        # Sort keys alphabetically (exact match with official docs)
        for key in sorted(params):
            return_str += key
            value = params[key]
            
            if value is None:
                return_str += 'null'
            elif isinstance(value, list):
                for subObj in value:
                    if isinstance(subObj, dict):
                        return_str += self._prepare_request_params(subObj, level + 1)
                    else:
                        return_str += str(subObj)
            elif isinstance(value, dict):
                return_str += self._prepare_request_params(value, level + 1)
            else:
                return_str += str(value)
                
        return return_str
    
    def _make_request(
        self, 
        method: str, 
        params: Optional[Dict[str, Any]] = None, 
        request_id: Optional[int] = None,
        auth_required: bool = True,
        http_method: str = "POST"
    ) -> Dict[str, Any]:
        """
        Execute API request with error handling and retries
        
        Args:
            method: API method to call
            params: Request parameters
            request_id: Unique request ID (generated if None)
            auth_required: Whether authentication is required
            http_method: HTTP method to use (GET or POST)
                
        Returns:
            API response as dictionary
                
        Raises:
            ValueError: For invalid parameters
            ConnectionError: For network issues
            TimeoutError: When request times out
            RuntimeError: For API errors
        """
        # Generate request ID if not provided
        if request_id is None:
            request_id = int(time.time() * 1000)
                
        # Check rate limits
        self._check_rate_limit()
            
        # Prepare base URL
        url = urljoin(self.base_url, method)
        
        # Prepare headers
        headers = {'Content-Type': 'application/json'}
            
        # Generate request data based on authentication requirement
        if auth_required:
            request_data = self._generate_signature(method, request_id, params or {})
            self.logger.debug(f"Authenticated request data: {json.dumps(request_data, default=str)}")
        else:
            request_data = {
                "id": request_id,
                "method": method,
                "params": params or {},
                "nonce": int(time.time() * 1000)
            }
                
        # Log request (excluding sensitive data)
        log_data = copy.deepcopy(request_data)
        if 'sig' in log_data:
            log_data['sig'] = '***'
        self.logger.debug(f"Making {http_method} request to {url}: {json.dumps(log_data, default=str)}")
            
        # Execute request with retries
        retry_count = 0
        last_exception = None
            
        while retry_count < self.max_retries:
            try:
                if http_method.upper() == "GET":
                    # For GET requests with parameters in query string
                    response = requests.get(
                        url,
                        params=params,
                        headers=headers,
                        timeout=self.timeout
                    )
                else:
                    # For POST requests with JSON body
                    response = requests.post(
                        url,
                        json=request_data,
                        headers=headers,
                        timeout=self.timeout
                    )
                    
                # Update rate limit tracking
                self._last_request_time = time.time()
                self._request_count += 1
                    
                # Check for HTTP errors
                response.raise_for_status()
                    
                # Parse response
                result = response.json()
                self.logger.debug(f"Response: {json.dumps(result, default=str)}")
                    
                # Check for API errors
                if 'code' in result and result['code'] != 0:
                    error_msg = f"API Error {result.get('code')}: {result.get('message', 'Unknown error')}"
                    self.logger.error(error_msg)
                    raise RuntimeError(error_msg)
                        
                return result
                    
            except requests.exceptions.Timeout as e:
                last_exception = TimeoutError(f"Request timed out: {str(e)}")
                self.logger.warning(f"Request timed out (attempt {retry_count + 1}/{self.max_retries})")
                    
            except requests.exceptions.ConnectionError as e:
                last_exception = ConnectionError(f"Connection error: {str(e)}")
                self.logger.warning(f"Connection error (attempt {retry_count + 1}/{self.max_retries}): {str(e)}")
                    
            except requests.exceptions.HTTPError as e:
                status_code = e.response.status_code
                response_text = e.response.text
                self.logger.error(f"HTTP Error {status_code}: {response_text}")
                    
                # Don't retry client errors except for rate limiting
                if status_code == 429:  # Too Many Requests
                    last_exception = RuntimeError(f"Rate limit exceeded: {str(e)}")
                    self.logger.warning(f"Rate limit exceeded (attempt {retry_count + 1}/{self.max_retries})")
                elif 400 <= status_code < 500:
                    error_msg = f"HTTP Error {status_code}: {response_text}"
                    self.logger.error(error_msg)
                    raise RuntimeError(error_msg)
                else:
                    last_exception = RuntimeError(f"Server error: {str(e)}")
                    self.logger.warning(f"Server error (attempt {retry_count + 1}/{self.max_retries}): {str(e)}")
                        
            except json.JSONDecodeError as e:
                last_exception = ValueError(f"Invalid JSON response: {str(e)}")
                self.logger.error(f"Invalid JSON response: {str(e)}")
                    
            except Exception as e:
                last_exception = RuntimeError(f"Unexpected error: {str(e)}")
                self.logger.error(f"Unexpected error: {str(e)}")
                raise
                    
            # Delay before retry
            time.sleep(self.RETRY_DELAY * (2 ** retry_count))
            retry_count += 1
                
        # If we get here, all retries failed
        if last_exception:
            raise last_exception
        else:
            raise RuntimeError("Request failed after retries")
    
    def _check_rate_limit(self):
        """
        Track and manage API request frequency to avoid hitting rate limits
        
        Simple implementation - for production use, consider implementing
        a more sophisticated rate limiting system based on the specific
        Crypto.com rate limits for each endpoint
        """
        current_time = time.time()
        time_diff = current_time - self._last_request_time
        
        # Basic rate limiting - avoid making more than 5 requests per second
        if self._request_count > 0 and time_diff < 0.2:
            sleep_time = 0.2 - time_diff
            self.logger.debug(f"Rate limit: sleeping for {sleep_time:.2f} seconds")
            time.sleep(sleep_time)

    def get_candlestick_data(
        self,
        instrument_name: str,
        timeframe: Optional[str] = None,
        count: Optional[int] = None,
        start_ts: Optional[int] = None,
        end_ts: Optional[int] = None,
        request_id: Optional[int] = None
    ) -> pd.DataFrame:
        """
        Retrieve OHLCV (Open, High, Low, Close, Volume) data for a specific instrument and timeframe.
        
        Args:
            instrument_name: Trading pair name (e.g., "BTCUSD-PERP")
            timeframe: Time interval (e.g., "1m", "5m", "15m", "30m", "1h", "2h", "4h", "12h", "1D", "7D", "14D", "1M")
                    Legacy formats also supported (M1, M5, M15, M30, H1, H2, H4, H12, D1, 1d)
            count: Number of candles to retrieve (default 25)
            start_ts: Start timestamp in milliseconds (default is 1 day ago)
            end_ts: End timestamp in milliseconds (default is current time)
            request_id: Optional request ID for tracking API calls
            
        Returns:
            pandas.DataFrame: DataFrame containing OHLCV data with columns:
                - timestamp: Start time of the candle
                - open: Opening price
                - high: Highest price
                - low: Lowest price
                - close: Closing price
                - volume: Trading volume
                - datetime: Human-readable timestamp
        
        Raises:
            ValueError: If instrument_name is not provided or data processing fails
            RuntimeError: If API request fails
        """
        # Validate required parameters
        if not instrument_name:
            raise ValueError("instrument_name is required")
        
        # Build request parameters
        params: Dict[str, Any] = {"instrument_name": instrument_name}
        
        # Add optional parameters if provided
        if timeframe:
            params["timeframe"] = timeframe
        if count:
            params["count"] = count
        if start_ts:
            params["start_ts"] = start_ts
        if end_ts:
            params["end_ts"] = end_ts
            
        try:
            # Make the API request - this is a public endpoint, so use GET method without authentication
            response = self._make_request(
                "public/get-candlestick", 
                params, 
                request_id=request_id, 
                auth_required=False,
                http_method="GET"
            )
            
            # Extract the data from the response
            result = response.get("result", {})
            data = result.get("data", [])
            
            if not data:
                self.logger.info(f"No candlestick data returned for {instrument_name}")
                return pd.DataFrame()
                
            # Convert the data to a DataFrame
            df = pd.DataFrame(data)
            
            # Rename columns for clarity
            df.rename(columns={
                "t": "timestamp",
                "o": "open",
                "h": "high",
                "l": "low",
                "c": "close",
                "v": "volume"
            }, inplace=True)
            
            # Convert string values to appropriate types
            for col in ["open", "high", "low", "close", "volume"]:
                df[col] = pd.to_numeric(df[col])
                
            # Sort by timestamp in ascending order
            df.sort_values("timestamp", inplace=True)
            
            # Add a human-readable datetime column
            df["datetime"] = pd.to_datetime(df["timestamp"], unit="ms")
            
            return df
            
        except Exception as e:
            self.logger.error(f"Error retrieving or processing candlestick data: {str(e)}")
            if "response" in locals():
                self.logger.debug(f"Response content: {response}")
            raise ValueError(f"Failed to retrieve or process candlestick data: {str(e)}")
        
    def create_limit_order(
        self,
        instrument_name: str,
        side: str,
        price: Union[str, float],
        quantity: Union[str, float],
        client_oid: Optional[str] = None,
        post_only: bool = False,
        time_in_force: Optional[str] = None,
        ref_price: Optional[Union[str, float]] = None,
        ref_price_type: Optional[str] = None,
        spot_margin: Optional[str] = None,
        request_id: Optional[int] = None,
        **kwargs
    ) -> Dict[str, Any]:
        """
        Create a limit order with specified parameters
        
        Args:
            instrument_name: Trading pair name (e.g., "BTCUSD-PERP")
            side: Order side, "BUY" or "SELL"
            price: Order price
            quantity: Order quantity
            client_oid: Client Order ID (Optional, maximum 36 characters)
            post_only: If True, adds POST_ONLY to exec_inst
            time_in_force: Time in force, one of "GOOD_TILL_CANCEL", "IMMEDIATE_OR_CANCEL", "FILL_OR_KILL"
                        (When post_only is True, can only be "GOOD_TILL_CANCEL")
            ref_price: Trigger price for stop orders
            ref_price_type: Which price to use for ref_price: "MARK_PRICE" (default), "INDEX_PRICE", "LAST_PRICE"
            spot_margin: "SPOT" for non-margin order, "MARGIN" for margin order
            request_id: Optional request ID for tracking API calls
            **kwargs: Additional parameters to pass to the API
                - stp_scope: "M" (Matches Master or Sub a/c) or "S" (Matches Sub a/c only)
                - stp_inst: "M" (Cancel Maker), "T" (Cancel Taker), or "B" (Cancel Both)
                - stp_id: STP ID (0 to 32767)
                - fee_instrument_name: Specify the preferred fee token
            
        Returns:
            Dict containing order_id and client_oid
            
        Raises:
            ValueError: If required parameters are missing or invalid
            RuntimeError: If API request fails
        """
        # Validate required parameters
        if not instrument_name:
            raise ValueError("instrument_name is required")
        
        if side not in ["BUY", "SELL"]:
            raise ValueError("side must be either 'BUY' or 'SELL'")
        
        # Convert price and quantity to strings as required by the API
        price_str = str(price)
        quantity_str = str(quantity)
        
        # Build base request parameters
        params = {
            "instrument_name": instrument_name,
            "side": side,
            "type": "LIMIT",
            "price": price_str,
            "quantity": quantity_str
        }
        
        # Add client_oid if provided
        if client_oid:
            if len(client_oid) > 36:
                raise ValueError("client_oid must be 36 characters or less")
            params["client_oid"] = client_oid
        
        # Handle post_only flag
        if post_only:
            params["exec_inst"] = ["POST_ONLY"]
            # When post_only is True, time_in_force can only be GOOD_TILL_CANCEL
            if time_in_force and time_in_force != "GOOD_TILL_CANCEL":
                raise ValueError("When post_only is True, time_in_force can only be 'GOOD_TILL_CANCEL'")
        
        # Add time_in_force if provided
        if time_in_force:
            valid_tif = ["GOOD_TILL_CANCEL", "IMMEDIATE_OR_CANCEL", "FILL_OR_KILL"]
            if time_in_force not in valid_tif:
                raise ValueError(f"time_in_force must be one of {valid_tif}")
            params["time_in_force"] = time_in_force
        
        # Add optional stop loss/take profit parameters
        if ref_price is not None:
            params["ref_price"] = str(ref_price)
            
        if ref_price_type is not None:
            valid_ref_price_types = ["MARK_PRICE", "INDEX_PRICE", "LAST_PRICE"]
            if ref_price_type not in valid_ref_price_types:
                raise ValueError(f"ref_price_type must be one of {valid_ref_price_types}")
            params["ref_price_type"] = ref_price_type
            
        if spot_margin is not None:
            valid_spot_margin = ["SPOT", "MARGIN"]
            if spot_margin not in valid_spot_margin:
                raise ValueError(f"spot_margin must be one of {valid_spot_margin}")
            params["spot_margin"] = spot_margin
        
        # Add additional parameters from kwargs
        for key, value in kwargs.items():
            params[key] = value
        
        # Make the API request - this is a private endpoint requiring authentication
        try:
            response = self._make_request(
                "private/create-order",
                params,
                request_id=request_id,
                auth_required=True
            )
            
            # Extract and return the result
            result = response.get("result", {})
            return {
                "order_id": result.get("order_id"),
                "client_oid": result.get("client_oid")
            }
            
        except Exception as e:
            self.logger.error(f"Error creating limit order: {str(e)}")
            raise RuntimeError(f"Failed to create limit order: {str(e)}")

    def create_market_order(
        self,
        instrument_name: str,
        side: str,
        quantity: Union[str, float],
        notional: Optional[Union[str, float]] = None,
        client_oid: Optional[str] = None,
        spot_margin: Optional[str] = None,
        request_id: Optional[int] = None,
        **kwargs
    ) -> Dict[str, Any]:
        """
        Create a market order with specified parameters
        
        Args:
            instrument_name: Trading pair name (e.g., "BTCUSD-PERP")
            side: Order side, "BUY" or "SELL"
            quantity: Order quantity
            notional: Amount to spend (required for MARKET BUY orders)
            client_oid: Client Order ID (Optional, maximum 36 characters)
            spot_margin: "SPOT" for non-margin order, "MARGIN" for margin order
            request_id: Optional request ID for tracking API calls
            **kwargs: Additional parameters to pass to the API
                - stp_scope: "M" (Matches Master or Sub a/c) or "S" (Matches Sub a/c only)
                - stp_inst: "M" (Cancel Maker), "T" (Cancel Taker), or "B" (Cancel Both)
                - stp_id: STP ID (0 to 32767)
                - fee_instrument_name: Specify the preferred fee token
            
        Returns:
            Dict containing order_id and client_oid
            
        Raises:
            ValueError: If required parameters are missing or invalid
            RuntimeError: If API request fails
        """
        # Validate required parameters
        if not instrument_name:
            raise ValueError("instrument_name is required")
        
        if side not in ["BUY", "SELL"]:
            raise ValueError("side must be either 'BUY' or 'SELL'")
        
        # Convert quantity to string as required by the API
        quantity_str = str(quantity)
        
        # Build base request parameters
        params = {
            "instrument_name": instrument_name,
            "side": side,
            "type": "MARKET",
            "quantity": quantity_str
        }
        
        # Add notional if provided (required for MARKET BUY orders)
        if notional is not None:
            params["notional"] = str(notional)
        elif side == "BUY":
            self.logger.warning("notional parameter is typically required for MARKET BUY orders")
        
        # Add client_oid if provided
        if client_oid:
            if len(client_oid) > 36:
                raise ValueError("client_oid must be 36 characters or less")
            params["client_oid"] = client_oid
            
        if spot_margin is not None:
            valid_spot_margin = ["SPOT", "MARGIN"]
            if spot_margin not in valid_spot_margin:
                raise ValueError(f"spot_margin must be one of {valid_spot_margin}")
            params["spot_margin"] = spot_margin
        
        # Add additional parameters from kwargs
        for key, value in kwargs.items():
            params[key] = value
        
        # Make the API request - this is a private endpoint requiring authentication
        try:
            response = self._make_request(
                "private/create-order",
                params,
                request_id=request_id,
                auth_required=True
            )
            
            # Extract and return the result
            result = response.get("result", {})
            return {
                "order_id": result.get("order_id"),
                "client_oid": result.get("client_oid")
            }
            
        except Exception as e:
            self.logger.error(f"Error creating market order: {str(e)}")
            raise RuntimeError(f"Failed to create market order: {str(e)}")

    def create_oco_order(
        self,
        instrument_name: str,
        side: str,
        quantity: Union[str, float],
        take_profit_price: Union[str, float],
        stop_loss_price: Union[str, float],
        take_profit_trigger: Optional[Union[str, float]] = None,
        stop_loss_trigger: Optional[Union[str, float]] = None,
        client_oid: Optional[str] = None,
        spot_margin: Optional[str] = None,
        request_id: Optional[int] = None,
        **kwargs
    ) -> Dict[str, Any]:
        """
        Create an OCO (One Cancels Other) order with take-profit and stop-loss orders
        
        Args:
            instrument_name: Trading pair name (e.g., "BTCUSD-PERP")
            side: Order side, "BUY" or "SELL"
            quantity: Order quantity for both orders
            take_profit_price: Limit price for take-profit order
            stop_loss_price: Limit price for stop-loss order
            take_profit_trigger: Trigger price for take-profit (optional, defaults to take_profit_price)
            stop_loss_trigger: Trigger price for stop-loss (optional, defaults to stop_loss_price)
            client_oid: Client Order ID (Optional, maximum 36 characters)
            spot_margin: "SPOT" for non-margin order, "MARGIN" for margin order
            request_id: Optional request ID for tracking API calls
            **kwargs: Additional parameters to pass to the API
            
        Returns:
            Dict containing order_list_id and order details
            
        Raises:
            ValueError: If required parameters are missing or invalid
            RuntimeError: If API request fails
        """
        # Validate required parameters
        if not instrument_name:
            raise ValueError("instrument_name is required")
        
        if side not in ["BUY", "SELL"]:
            raise ValueError("side must be either 'BUY' or 'SELL'")
        
        # Convert values to strings as required by the API
        quantity_str = str(quantity)
        take_profit_price_str = str(take_profit_price)
        stop_loss_price_str = str(stop_loss_price)
        
        # Set default trigger prices if not provided
        if take_profit_trigger is None:
            take_profit_trigger = take_profit_price
        if stop_loss_trigger is None:
            stop_loss_trigger = stop_loss_price
            
        take_profit_trigger_str = str(take_profit_trigger)
        stop_loss_trigger_str = str(stop_loss_trigger)
        
        # Determine order types based on side
        if side == "BUY":
            # For BUY position: take-profit sells at higher price, stop-loss sells at lower price
            take_profit_side = "SELL"
            stop_loss_side = "SELL"
        else:
            # For SELL position: take-profit buys at lower price, stop-loss buys at higher price
            take_profit_side = "BUY"
            stop_loss_side = "BUY"
        
        # Build the order list
        order_list = [
            {
                "instrument_name": instrument_name,
                "side": take_profit_side,
                "type": "TAKE_PROFIT_LIMIT",
                "price": take_profit_price_str,
                "quantity": quantity_str,
                "trigger_price": take_profit_trigger_str
            },
            {
                "instrument_name": instrument_name,
                "side": stop_loss_side,
                "type": "STOP_LIMIT",
                "price": stop_loss_price_str,
                "quantity": quantity_str,
                "trigger_price": stop_loss_trigger_str
            }
        ]
        
        # Add client_oid to both orders if provided
        if client_oid:
            if len(client_oid) > 36:
                raise ValueError("client_oid must be 36 characters or less")
            order_list[0]["client_oid"] = f"{client_oid}_TP"
            order_list[1]["client_oid"] = f"{client_oid}_SL"
        
        # Add spot_margin to both orders if provided
        if spot_margin is not None:
            valid_spot_margin = ["SPOT", "MARGIN"]
            if spot_margin not in valid_spot_margin:
                raise ValueError(f"spot_margin must be one of {valid_spot_margin}")
            order_list[0]["spot_margin"] = spot_margin
            order_list[1]["spot_margin"] = spot_margin
        
        # Add additional parameters from kwargs to both orders
        for key, value in kwargs.items():
            order_list[0][key] = value
            order_list[1][key] = value
        
        # Build request parameters
        params = {
            "contingency_type": "OCO",
            "order_list": order_list
        }
        
        # Make the API request - this is a private endpoint requiring authentication
        try:
            response = self._make_request(
                "private/create-order-list",
                params,
                request_id=request_id,
                auth_required=True
            )
            
            # Extract and return the result
            result = response.get("result", {})
            return {
                "order_list_id": result.get("order_list_id"),
                "order_list": result.get("order_list", [])
            }
            
        except Exception as e:
            self.logger.error(f"Error creating OCO order: {str(e)}")
            raise RuntimeError(f"Failed to create OCO order: {str(e)}")
        
if __name__ == '__main__':
    import os
    from dotenv import load_dotenv
    load_dotenv()
    cdc_api_key = os.environ.get("CDCEX_API")
    cdc_secret_key = os.environ.get("CDCEX_SECRET")

    cdc = CryptoComAPI(cdc_api_key, cdc_secret_key, use_sandbox=False)
    # candles = cdc.get_candlestick_data('BTC_USD')
    # print(candles)
    cdc.create_limit_order('BTC_USD', 'BUY', '60000', '0.00004')