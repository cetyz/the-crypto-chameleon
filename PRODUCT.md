# Product

## Register

brand

## Users

A mixed general-web audience — friends, strangers who stumble in from a Telegram link, and the occasional crypto-curious onlooker. They arrive on a phone or laptop with no prior context, no account, and no intent to trade. The job to be done is simple: in the first ten seconds, decide whether this experiment is worth a second look. They want to see whether the algorithmic Chameleon account is actually beating a dumb monthly DCA, presented honestly enough that they trust the numbers.

## Product Purpose

The Crypto Chameleon is a public transparency dashboard that runs an ongoing experiment in the open: does analysis-driven trading beat brain-off dollar-cost averaging? Two real Crypto.com accounts trade on a weekly cron, every transaction lands in Supabase, every receipt is visible on a single page. The site exists to make the experiment legible to outsiders — not to sell a strategy, not to recruit followers, not to monetize attention. Success looks like a visitor leaving with a clear, unhyped sense of which account is ahead and by how much.

## Brand Personality

Curious, candid, deadpan. The voice is the voice of someone running a small experiment in their garage and writing down the results carefully because that is the honest thing to do. Dry, slightly amused, never breathless. Numbers speak first; copy stays out of their way. When the Chameleon is losing, the page says so plainly. The chameleon motif is present but understated — it is the name of the experiment, not a mascot, not a gradient lizard hero.

## Anti-references

- **Generic crypto / SaaS templates.** No neon-on-black, no gradient hero numbers, no "AI-powered" framing, no CoinMarketCap or DEX-clone chrome.
- **Shilling and influencer aesthetics.** No rocket emojis, no green-candle gain-porn, no "wen lambo" register, no aspirational lifestyle imagery.
- **Bloomberg-terminal density.** Not a pro trading desk. No 14-column tables, no monospace-everything, no information firehose.
- **Corporate fintech.** No navy + gold, no JPMorgan-style stock-photo professionalism, no compliance-page solemnity.

## Design Principles

1. **Receipts on the table.** Every claim the page makes is backed by a row in the transaction log a visitor can scroll to. Hide nothing, even when the Chameleon is losing — especially then.
2. **The data is the headline.** Numbers, sparklines, and the equity chart carry the page. Copy is captions, not pitches. If a label needs a paragraph to justify it, the label is wrong.
3. **Editorial over dashboard.** Closer to a Pudding.cool data story than to a Bloomberg terminal. Generous spacing, considered typography, a single scrollable narrative — not a grid of identical cards.
4. **One experiment, two characters.** Chameleon and Control are the only two entities on the page. Every visual decision reinforces the head-to-head; nothing should distract from the comparison.
5. **Deadpan, not dead.** Restraint is the default, but the page should still feel like a human made it. Small idiosyncrasies — a turn of phrase, a considered footnote, an unexpected micro-detail — are welcome. Sterile is a failure mode.

## Accessibility & Inclusion

- **Colorblind-safe palette.** The two account colors (Chameleon, Control) must be distinguishable under deuteranopia and protanopia. Never rely on hue alone — pair every color signal with a shape, weight, or label. Verify chart series with a CVD simulator before shipping.
- **Mobile-first.** Most visitors arrive from a Telegram link on a phone. Layouts, type, and tap targets must work on a 360px viewport before they work on desktop. Side-by-side tables stack vertically below the md breakpoint, as already planned.
- **Respect `prefers-reduced-motion`.** Sparkline draw-ins and chart transitions degrade to instant renders.
- **No formal WCAG target committed**, but treat AA contrast on text and chart annotations as the working baseline.
