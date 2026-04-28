import hmac
import hashlib
import time
import copy
import json
import logging
from typing import Any, Dict, List, Optional, Union
from urllib.parse import urljoin

import requests


class CryptoComAPI:
    """REST wrapper for the Crypto.com Exchange v1 API.

    Scope: market orders + balance reads. The API key passed in identifies
    which account the instance acts on. For the chameleon + control
    sub-accounts, instantiate one CryptoComAPI per sub-account key (used for
    that sub-account's trading and its own balance). To list all sub-accounts
    or read every sub-account's balance in one call, instantiate a third time
    with the master account key and use get_accounts() /
    get_subaccount_balances().
    """

    BASE_URL = "https://api.crypto.com/exchange/v1/"
    MAX_NESTING_LEVEL = 3
    RETRY_DELAY = 0.5

    def __init__(
        self,
        api_key: str,
        secret_key: str,
        timeout: int = 30,
        max_retries: int = 3,
        logger: Optional[logging.Logger] = None,
    ):
        self.api_key = api_key
        self.secret_key = secret_key
        self.base_url = self.BASE_URL
        self.timeout = timeout
        self.max_retries = max_retries

        self.logger = logger if logger else logging.getLogger(__name__)
        if not self.logger.handlers:
            handler = logging.StreamHandler()
            handler.setFormatter(
                logging.Formatter("%(asctime)s - %(name)s - %(levelname)s - %(message)s")
            )
            self.logger.addHandler(handler)
            self.logger.setLevel(logging.INFO)

        self._last_request_time = 0.0
        self._request_count = 0

    # ------------------------------------------------------------------
    # Signing & transport
    # ------------------------------------------------------------------

    def _prepare_request_params(self, params: Dict[str, Any], level: int = 0) -> str:
        """Convert params into the deterministic string used in the signature payload.

        Sorts keys alphabetically, recurses into dicts/lists up to MAX_NESTING_LEVEL.
        Algorithm matches the official Crypto.com spec.
        """
        if level >= self.MAX_NESTING_LEVEL:
            return str(params)

        out = ""
        for key in sorted(params):
            out += key
            value = params[key]
            if value is None:
                out += "null"
            elif isinstance(value, list):
                for item in value:
                    if isinstance(item, dict):
                        out += self._prepare_request_params(item, level + 1)
                    else:
                        out += str(item)
            elif isinstance(value, dict):
                out += self._prepare_request_params(value, level + 1)
            else:
                out += str(value)
        return out

    def _generate_signature(
        self, method: str, request_id: int, params: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Build the signed request body for an authenticated POST."""
        nonce = int(time.time() * 1000)
        param_str = self._prepare_request_params(params)
        payload_str = method + str(request_id) + self.api_key + param_str + str(nonce)

        signature = hmac.new(
            self.secret_key.encode("utf-8"),
            msg=payload_str.encode("utf-8"),
            digestmod=hashlib.sha256,
        ).hexdigest()

        return {
            "id": request_id,
            "method": method,
            "api_key": self.api_key,
            "params": params,
            "nonce": nonce,
            "sig": signature,
        }

    def _check_rate_limit(self) -> None:
        """Coarse client-side throttle: cap at ~5 req/s."""
        if self._request_count == 0:
            return
        elapsed = time.time() - self._last_request_time
        if elapsed < 0.2:
            time.sleep(0.2 - elapsed)

    def _make_request(
        self,
        method: str,
        params: Optional[Dict[str, Any]] = None,
        request_id: Optional[int] = None,
        auth_required: bool = True,
        http_method: str = "POST",
    ) -> Dict[str, Any]:
        """Send a request to the API with retries on transient errors.

        Public endpoints use GET with query params; private endpoints use POST with a
        signed JSON body. 4xx responses (other than 429) are not retried.
        """
        if request_id is None:
            request_id = int(time.time() * 1000)

        self._check_rate_limit()

        url = urljoin(self.base_url, method)
        headers = {"Content-Type": "application/json"}

        if auth_required:
            request_data = self._generate_signature(method, request_id, params or {})
            log_data = copy.deepcopy(request_data)
            log_data["sig"] = "***"
            log_data["api_key"] = "***"
            self.logger.debug(f"POST {url} body={json.dumps(log_data, default=str)}")
        else:
            request_data = None
            self.logger.debug(f"{http_method} {url} params={params}")

        last_exception: Optional[Exception] = None
        for attempt in range(self.max_retries):
            try:
                if http_method.upper() == "GET":
                    response = requests.get(
                        url, params=params, headers=headers, timeout=self.timeout
                    )
                else:
                    response = requests.post(
                        url, json=request_data, headers=headers, timeout=self.timeout
                    )

                self._last_request_time = time.time()
                self._request_count += 1

                response.raise_for_status()
                result = response.json()

                if "code" in result and result["code"] != 0:
                    raise RuntimeError(
                        f"API Error {result.get('code')}: {result.get('message', 'Unknown error')}"
                    )

                return result

            except requests.exceptions.Timeout as e:
                last_exception = TimeoutError(f"Request timed out: {e}")
                self.logger.warning(
                    f"Timeout (attempt {attempt + 1}/{self.max_retries})"
                )

            except requests.exceptions.ConnectionError as e:
                last_exception = ConnectionError(f"Connection error: {e}")
                self.logger.warning(
                    f"Connection error (attempt {attempt + 1}/{self.max_retries}): {e}"
                )

            except requests.exceptions.HTTPError as e:
                status_code = e.response.status_code
                response_text = e.response.text
                self.logger.error(f"HTTP {status_code}: {response_text}")
                if status_code == 429:
                    last_exception = RuntimeError(f"Rate limit exceeded: {e}")
                elif 400 <= status_code < 500:
                    raise RuntimeError(f"HTTP {status_code}: {response_text}")
                else:
                    last_exception = RuntimeError(f"Server error: {e}")

            except json.JSONDecodeError as e:
                raise ValueError(f"Invalid JSON response: {e}")

            time.sleep(self.RETRY_DELAY * (2**attempt))

        assert last_exception is not None
        raise last_exception

    # ------------------------------------------------------------------
    # Public market data
    # ------------------------------------------------------------------

    def get_candlesticks(
        self,
        instrument_name: str,
        timeframe: Optional[str] = None,
        count: Optional[int] = None,
        start_ts: Optional[int] = None,
        end_ts: Optional[int] = None,
    ) -> List[Dict[str, Any]]:
        """OHLCV candles for an instrument.

        Returns the raw list of candle dicts (keys: t, o, h, l, c, v) sorted by t ascending.
        Callers can wrap in pandas if they need a DataFrame.
        """
        if not instrument_name:
            raise ValueError("instrument_name is required")

        params: Dict[str, Any] = {"instrument_name": instrument_name}
        if timeframe:
            params["timeframe"] = timeframe
        if count is not None:
            params["count"] = count
        if start_ts is not None:
            params["start_ts"] = start_ts
        if end_ts is not None:
            params["end_ts"] = end_ts

        response = self._make_request(
            "public/get-candlestick",
            params,
            auth_required=False,
            http_method="GET",
        )
        data = response.get("result", {}).get("data", []) or []
        return sorted(data, key=lambda c: c.get("t", 0))

    def get_instruments(self) -> List[Dict[str, Any]]:
        """All tradable instruments with metadata (tick sizes, min qty, etc.)."""
        response = self._make_request(
            "public/get-instruments",
            params=None,
            auth_required=False,
            http_method="GET",
        )
        return response.get("result", {}).get("data", []) or []

    def get_ticker(self, instrument_name: str) -> Dict[str, Any]:
        """Latest ticker for a single instrument."""
        if not instrument_name:
            raise ValueError("instrument_name is required")

        response = self._make_request(
            "public/get-tickers",
            params={"instrument_name": instrument_name},
            auth_required=False,
            http_method="GET",
        )
        data = response.get("result", {}).get("data", []) or []
        if not data:
            raise ValueError(f"No ticker returned for {instrument_name}")
        return data[0]

    # ------------------------------------------------------------------
    # Private account
    # ------------------------------------------------------------------

    def get_user_balance(self) -> Dict[str, Any]:
        """Wallet and available margin balances for the account."""
        response = self._make_request("private/user-balance", params={})
        return response.get("result", {})

    def get_subaccount_balances(self) -> List[Dict[str, Any]]:
        """Wallet/margin balances for every sub-account under this master key.

        Master-key endpoint. Returns a list of balance objects, one per
        sub-account; each entry has an `account` field (sub-account UUID)
        plus total_available_balance, total_cash_balance, position_balances,
        etc. Calling this with a sub-account key (rather than the master
        key) will not return data for sibling sub-accounts.
        """
        response = self._make_request("private/get-subaccount-balances", params={})
        return response.get("result", {}).get("data", []) or []

    def get_accounts(self) -> List[Dict[str, Any]]:
        """List sub-accounts (uuid + label) under this master key.

        Use to map human labels like 'chameleon' / 'control' to the UUIDs
        that appear in get_subaccount_balances() responses, so callers don't
        need to hardcode UUIDs.
        """
        response = self._make_request("private/get-accounts", params={})
        return response.get("result", {}).get("sub_account_list", []) or []

    # ------------------------------------------------------------------
    # Private trading
    # ------------------------------------------------------------------

    def create_market_order(
        self,
        instrument_name: str,
        side: str,
        client_oid: str,
        quantity: Optional[Union[str, float]] = None,
        notional: Optional[Union[str, float]] = None,
        spot_margin: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Place a market order.

        BUY orders should pass `notional` (quote-currency amount, e.g. USD).
        SELL orders should pass `quantity` (base-asset amount).

        `client_oid` is required: omitting it makes the API fall back to the request
        nonce, which can collide across orders. Idempotency for the scheduled job
        depends on a deterministic client_oid per run.

        Returns the raw `result` dict (typically {order_id, client_oid}). The fill
        is asynchronous — call `get_order_detail(order_id)` afterwards to read
        avg_price, cumulative_quantity, cumulative_fee, and status.
        """
        if not instrument_name:
            raise ValueError("instrument_name is required")
        if side not in ("BUY", "SELL"):
            raise ValueError("side must be 'BUY' or 'SELL'")
        if not client_oid:
            raise ValueError("client_oid is required for idempotency")
        if len(client_oid) > 36:
            raise ValueError("client_oid must be 36 characters or less")
        if side == "BUY" and notional is None and quantity is None:
            raise ValueError("BUY market order requires either notional or quantity")
        if side == "SELL" and quantity is None:
            raise ValueError("SELL market order requires quantity")

        params: Dict[str, Any] = {
            "instrument_name": instrument_name,
            "side": side,
            "type": "MARKET",
            "client_oid": client_oid,
        }
        if quantity is not None:
            params["quantity"] = str(quantity)
        if notional is not None:
            params["notional"] = str(notional)
        if spot_margin is not None:
            if spot_margin not in ("SPOT", "MARGIN"):
                raise ValueError("spot_margin must be 'SPOT' or 'MARGIN'")
            params["spot_margin"] = spot_margin

        response = self._make_request("private/create-order", params)
        return response.get("result", {})

    def get_order_detail(self, order_id: str) -> Dict[str, Any]:
        """Current status and fill details of a single order.

        Use this to learn the actual filled price, quantity, and fee after a
        market order has been placed.
        """
        if not order_id:
            raise ValueError("order_id is required")
        response = self._make_request(
            "private/get-order-detail", params={"order_id": str(order_id)}
        )
        return response.get("result", {})

    def get_trades(
        self,
        instrument_name: Optional[str] = None,
        start_ts: Optional[int] = None,
        end_ts: Optional[int] = None,
        limit: Optional[int] = None,
    ) -> List[Dict[str, Any]]:
        """Account trade/fill history.

        Preferred source for per-fill fee detail (fee currency + amount).
        """
        params: Dict[str, Any] = {}
        if instrument_name:
            params["instrument_name"] = instrument_name
        if start_ts is not None:
            params["start_ts"] = start_ts
        if end_ts is not None:
            params["end_ts"] = end_ts
        if limit is not None:
            params["limit"] = limit

        response = self._make_request("private/get-trades", params=params)
        return response.get("result", {}).get("data", []) or []

    def cancel_order(self, order_id: str) -> Dict[str, Any]:
        """Cancel an open order. Safety hatch — not used by the happy path."""
        if not order_id:
            raise ValueError("order_id is required")
        response = self._make_request(
            "private/cancel-order", params={"order_id": str(order_id)}
        )
        return response.get("result", {})


if __name__ == "__main__":
    import os
    from dotenv import load_dotenv

    load_dotenv()
    api_key = os.environ.get("CDCEX_API")
    secret_key = os.environ.get("CDCEX_SECRET")
    if not api_key or not secret_key:
        raise SystemExit("CDCEX_API and CDCEX_SECRET must be set in the environment")

    # Smoke test: prove auth + transport work without placing a trade.
    cdc = CryptoComAPI(api_key, secret_key)
    balance = cdc.get_user_balance()
    print(json.dumps(balance, indent=2, default=str))
