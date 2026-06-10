<!-- SEED: re-run /impeccable document once there's code to capture the actual tokens and components. -->
---
name: The Crypto Chameleon
description: A public, deadpan transparency dashboard pitting an algorithmic trading account against a dumb monthly DCA.
---

# Design System: The Crypto Chameleon

## 1. Overview

**Creative North Star: "The Lab Notebook, Bound in Leather"**

The system is a warm dark editorial surface: a deep, slightly brown near-black page that reads like the inside cover of a hardback field journal, not the cold slate of a SaaS dashboard. Bone-white text sits on it like ink that has settled. One restrained accent — the Chameleon hue — appears on roughly a tenth of the surface and never more: in the equity line, in a single underline, in the headline percentage. The Control account gets a quieter neutral so the two characters of the experiment are typographically equal but chromatically asymmetric, on purpose. The page is read top to bottom like a short essay with charts in it; it is not scanned like a dashboard.

The system explicitly rejects four lanes: neon-on-cold-black crypto chrome, rocket-emoji shilling, Bloomberg-terminal density, and navy-and-gold corporate fintech. Where those lanes shout, this whispers; where they crowd, this gives air; where they decorate, this annotates. Sterility is also a failure mode — the warmth of the background, the serif headline, and a few small considered idiosyncrasies (a footnote, a turn of phrase, a hand-set figure) are what keep the page from feeling machine-generated.

**Key Characteristics:**
- Warm dark surface, not cool. The background carries a small amount of brown chroma, never pure neutral.
- Serif display, sans body, tabular mono for every figure. Numbers always align column-to-column.
- One accent, used sparingly. The Chameleon color is rare on purpose.
- Generous whitespace. Single scrollable narrative, not a card grid.
- Motion is responsive, not choreographed. Transitions confirm interactions; nothing performs.

## 2. Colors

A warm dark palette of paper-stained ink, with a single accent reserved for the Chameleon account.

### Primary
- **Chameleon Accent** `[hue to be resolved during implementation — candidate: a warm green-gold around oklch(72% 0.14 130), to be CVD-verified]`: The single voice of the experiment. Used on the Chameleon equity line, the headline return percentage when positive, the underline beneath the Chameleon table title, and nothing else. Never on backgrounds, never on more than ~10% of any visible region.

### Neutral
- **Deep Ink** `[oklch ~18% with chroma ~0.01 toward brown, to be resolved]`: The page surface. Warm near-black; explicitly not slate-950, explicitly not pure neutral.
- **Settled Ink** `[oklch ~95% with chroma ~0.005, to be resolved]`: The body text color. Bone-white, never `#fff`.
- **Faded Ink** `[oklch ~70%, to be resolved]`: Secondary text, axis labels, footnotes, timestamps.
- **Rule Line** `[oklch ~30%, low chroma, to be resolved]`: Hairline dividers between sections, table row rules, the Control account's series in the equity chart.

### Named Rules

**The One Voice Rule.** The Chameleon Accent is used on no more than ~10% of any rendered region. Its rarity is the point. The instant it appears on a background fill, a button, or a second chart series, the rule has been broken.

**The No-Pure-Neutral Rule.** No `#000`, no `#fff`. Every neutral carries a small chroma toward the warm-brown hue family. Pure neutrals read as cold and corporate; they are forbidden.

**The Asymmetric Pair Rule.** Chameleon and Control are visually unequal on purpose. Chameleon gets color; Control gets a refined neutral. Never give Control its own accent — the experiment has one protagonist and one foil, not two equals.

## 3. Typography

**Display Font:** `[serif display family to be chosen at implementation — candidates: Source Serif 4, Newsreader, GT Sectra, Tiempos Headline]`
**Body Font:** `[neutral sans to be chosen at implementation — candidates: Inter, Söhne, Geist Sans]`
**Mono Font (figures):** `[tabular-numerals mono to be chosen at implementation — candidates: JetBrains Mono, IBM Plex Mono, Geist Mono]`

**Character:** The pairing reads as a long-form magazine article that happens to have live data in it. The serif sets the editorial tone of the page; the sans carries running text without drawing attention to itself; the mono exists so that every dollar amount, percentage, and BTC figure aligns vertically down a column with no jitter.

### Hierarchy
- **Display** (regular or medium, `clamp(2.5rem, 6vw, 4rem)`, line-height 1.05): Page title and the two headline return percentages at the top of each account tile.
- **Headline** (medium, `clamp(1.5rem, 3vw, 2rem)`, line-height 1.15): Section headers ("Chameleon", "Control", "Transaction log").
- **Title** (medium, 1.125rem, line-height 1.3): Card and table titles, the "Next run in 3d 14h" strip.
- **Body** (regular, 1rem, line-height 1.55, max 65–75ch): Disclaimers, footnotes, captions, any explanatory prose.
- **Label** (medium, 0.75rem, letter-spacing 0.06em, uppercase): Metric labels under each big figure ("PORTFOLIO IN USD", "CAPITAL INVESTED"), table column headers.
- **Mono Figure** (regular, inherits size from context, `font-variant-numeric: tabular-nums`): Every numeric value — prices, amounts, USD values, percentages, BTC figures.

### Named Rules

**The Tabular Figure Rule.** Every numeric value renders in the mono family with tabular-nums on. No proportional digits in any column where rows are compared vertically. A misaligned price column breaks the page.

**The One-Serif Rule.** The serif is used for display and headline only. Never set body copy in the serif, never set the serif at body weight. The contrast between serif headline and sans body is the typographic identity; muddying it collapses the system.

**The Caption-Not-Pitch Rule.** Body copy explains figures; it never sells them. If a paragraph would not look at home as a caption under a chart in a print magazine, it does not belong on this page.

## 4. Elevation

The system is flat by default. Depth is conveyed by hairline rules (`Rule Line` color, 1px), by generous whitespace, and by the warm-dark surface itself; not by shadows. No card surfaces float above the page.

The only acknowledged elevation is on focus and active states (see Components). Drop shadows on cards, on tiles, on the chart container, on tables, are forbidden.

### Named Rules

**The Hairline Rule.** Separation between sections, between rows, between the two account tiles, is always a 1px Rule Line, never a shadow and never a filled card background. If a hairline isn't enough separation, the spacing scale is wrong — fix the spacing, not the elevation.

**The Flat-Surface Rule.** No card has a different background fill from the page. The dashboard reads as one continuous surface with rules drawn on it. Tinted card backgrounds are a SaaS-template tell and are forbidden.

## 5. Components

*Components will be documented in detail on the next `/impeccable document` pass, once the SvelteKit components have real styles. The starter behaviors below are doctrine for how they should feel when built — not a specification of current code.*

### Headline Tile (Chameleon / Control)
The two top tiles read as the opening sentence of an essay. No card background, no border-radius pill; a hairline divides the pair. The percentage return is set in the Display serif, large; metric labels below are tracked-out uppercase Label type; figures are Mono. The Chameleon tile carries one stroke of the Chameleon Accent under its title; the Control tile does not.

### Equity Chart
Two line series, no fill. Chameleon line in the Chameleon Accent, Control line in a Rule Line neutral, weight 2px. Gridlines are barely-there in Faded Ink. Time-range and USD/BTC toggles render as tracked-out uppercase Label type with a 1px underline on the active state, never as filled pills.

### Transaction Table
A typographic table, not a data grid. No alternating row backgrounds, no card wrapper, no shadow. Columns separated only by space; rows separated by hairline Rule Lines. Numeric columns set in Mono with tabular-nums. The two tables sit side by side on desktop and stack on mobile, with the Chameleon table always above the Control table when stacked.

### Buttons & Toggles
There are essentially no traditional buttons on this dashboard. Toggles (time range, USD/BTC) render as small uppercase Label type with a 1px underline on the active state. No filled background, no border-radius. On hover, the inactive labels shift from Faded Ink to Settled Ink.

### Footer Disclaimer
Set in Body type at small size in Faded Ink, max-width 65ch. Plain, deadpan, never apologetic. A `Not financial advice.` line and a quiet link to the source data are the minimum.

## 6. Do's and Don'ts

### Do:
- **Do** keep the page surface warm and dark: a slightly brown near-black, never the cold slate-950 currently in `app.css`.
- **Do** reserve the Chameleon Accent for the Chameleon series only, on no more than ~10% of any visible region.
- **Do** set every numeric value in the Mono family with `font-variant-numeric: tabular-nums` so columns align.
- **Do** verify both account colors under deuteranopia and protanopia simulation before shipping. Pair every color cue with a label, weight, or position so the chart is legible without color.
- **Do** design for a 360px viewport first; most visitors arrive from a Telegram link on a phone.
- **Do** respect `prefers-reduced-motion`. Sparkline draw-ins and chart transitions degrade to instant renders.
- **Do** divide sections with 1px hairlines and generous whitespace, not with cards or shadows.

### Don't:
- **Don't** use `#000` or `#fff`. Every neutral carries a small warm chroma. Pure neutrals are corporate and cold.
- **Don't** ship neon-on-black crypto chrome, gradient hero numbers, "AI-powered" framing, or any CoinMarketCap / DEX-clone visual reflex. The first-order category trap.
- **Don't** use shilling or influencer aesthetics: no rocket emojis, no green-candle gain-porn, no "wen lambo" copy, no aspirational lifestyle imagery.
- **Don't** lean into Bloomberg-terminal density. No 14-column tables, no monospace-everything, no information firehose. This is an essay, not a trading desk.
- **Don't** use corporate fintech tropes — no navy and gold, no JPMorgan stock-photo professionalism, no compliance-page solemnity.
- **Don't** give the Control account its own accent color. Asymmetry is the point.
- **Don't** wrap sections in cards or floating containers. Flat surface, hairline rules.
- **Don't** use `border-left` or `border-right` greater than 1px as a colored accent stripe. Side-stripes are banned.
- **Don't** use `background-clip: text` gradient text. Single solid color only; emphasis via weight or size.
- **Don't** use glassmorphism, backdrop-blur cards, or any "frosted" surface as decoration.
- **Don't** restate the headline in the copy below it. Every word earns its place.
- **Don't** use em dashes in UI copy. Commas, colons, semicolons, periods, or parentheses only.
