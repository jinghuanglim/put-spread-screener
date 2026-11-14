<!-- JH — 14 Nov 2026 · Supersedes 2-1-14. Not financial advice. -->

# Put Credit Spread — Workflow 2-1-15

**Changes vs 2-1-14:**
- **Exit rule dropped (14 Nov):** hold to expiry. 12-yr test: exit cost ~10 pts/yr with no lower max drawdown. Only the expiry-Friday pin close remains.
- **Up to 2 open spreads per name** (different expiries).
- **One credit floor: 10%W for all names** (was volatile 12% / calm 10%).
- **Size: 5% risk** by NetLiq (was 7%).
- **All caps removed** (tech max 4 and cluster caps). JH decides concentration at ticket.

**Expected (independent backtest 2015 → Nov 2026, real IV ×0.93, up to 2 spreads per name, hold to expiry):** ~26% a year, max drawdown ~37%, worst 1-in-20 year ~−15%, ~114 trades/yr. Model on today's winners with no earnings gaps — treat as a best case. SPY same period: ~13%/yr incl. dividends, max DD 34%.

Evidence: `claude/loss-review-2026-11.md` (runs 1–4), `claude/floor-test-2026-11.md`.

---

## 1. RULES

| Item | Rule |
|---|---|
| Structure | Put credit spread only. No naked shorts, no stock positions. |
| Short strike | 0.15Δ (NVDA, TSM 0.20Δ). Nearest listed strike; 0.14–0.16 counts as 0.15. Never sweep up to clear the floor. |
| DTE | 18–21, prefer 18. Flag if none listed. |
| **Width** | **5% of spot, rounded UP to the next listed strike (≈ spot ÷ 20). Min $5. Spot < $100 → skip.** |
| **Credit floor** | **Worst case (short bid − long ask) ≥ 10%W, all names.** |
| Liquidity | OI ≥ 500 both legs, bid/ask ≤ 10% of mid |
| **Size** | **Qty = SIZE ÷ (width − credit), round down.** SIZE = NetLiq × 0.0005 (5% ÷ 100). Below 1 → skip. |
| **Exit** | **Hold to expiry.** No stop / exit rule. Only exception: expiry-Friday pin rule below. JH monitors intraday himself (no alerts). |
| Expiry | Short ITM or within 0.5% of spot on expiry Friday → close before the bell |
| Total exposure | Total max loss of open spreads: aim ≤ 50% of **cash** (IBKR total cash value), hard max 60%. Cash ≤ 0 → no room. No SPY hedge → half these limits. |
| Caps | **None.** Max 2 open spreads per name (different expiries); a name with 1 open spread still shows as a candidate, with 2 it doesn't. Concentration is JH's call at ticket. |
| Earnings | None on/before expiry |
| **Guardrails** | Cash < 0 → no new entries. NetLiq ≤ $300k → SIZE uses 3% (NetLiq × 0.0003). |
| Condor | Only if VIX ≥ 20 AND SPX −2%..+3% vs 20MA AND no binary macro event. Half size, call floor 7%W. |

**Assigned stock** isn't a position: sell it or document a plan within 2 sessions.

**Legacy stock** (NFLX, COIN, IBKR, SPCX) is outside the system. Report it, never add to it.

---

## 2. UNIVERSE (25) & IDs

| Volatile | ID | Calm | ID |
|---|---|---|---|
| NVDA | 4815747 | JNJ | 8719 |
| TSM | 6223250 | MCD | 9408 |
| AMD | 4391 | COST | 272997 |
| AVGO | 313130367 | V | 49462172 |
| PLTR | 444857009 | JPM | 1520593 |
| TSLA | 76792991 | AAPL | 265598 |
| DELL | 346218218 | HD | 7930 |
| CRWD | 370757467 | XOM | 895178251 |
| PANW | 110619459 | MSFT | 272093 |
| ANET | 740948854 | GOOGL | 208813719 |
| META | 107113386 | AMZN | 3691937 |
| CRM | 29624264 | LLY | 9160 |
| CAT | 5437 | | |

Tiers no longer change the floor. Kept for reference and the Gate 1a IV check.

**Other IDs:**
- **Regime:** VIX 13455763 (`IND`, `CBOE`)
- **Hedge:** SPY 756733
- **Legacy, not screened:** NFLX 15124833, COIN 481691285, IBKR 43645865, SPCX 890493863

This table beats any recalled ID. **Re-verify all IDs: due 17 Nov 2026.**

---

## 3. CAPS

None (removed 14 Nov 2026). Backtest: caps cut return without lowering max drawdown, except very tight ones (1 per cluster or tech max 2).

**Watch yourself:** the Oct 2026 loss came from 3 semis + 2 security open at once.

---

## 4. EARNINGS CACHE

**How to use it:**
- Search a name only when its date is within 10 trading days, blank, just reported, or older than 60 days.
- Use the IR press release as the source. If sources conflict and nothing is confirmed → block the name.

| Next report (est. unless noted) | Names |
|---|---|
| ~18 Nov | NVDA |
| mid–late Nov | PANW, DELL (24 Nov) |
| early Dec | CRM (2 Dec), CRWD |
| 9 Dec (confirmed, IR) | AVGO |
| Reported Oct–early Nov → search for next date | AAPL, AMD, AMZN, ANET, GOOGL, JNJ, JPM, META, MSFT, PLTR, TSLA, TSM, V |
| Blank → search | CAT, COST, HD, LLY, MCD, XOM |

---

## 5. "GO" SESSION — STEPS

Load all tools in one pass first. **Live prices only, no recalled figures.** If there's no live price → drop the row.

1. **Account:** get positions, balances and summary once each and reuse them. Record NetLiq, cash, SIZE, hedge status, and operative cap.
2. **Regime:** VIX via `get_price_history` (5-min, 2 bars). SPX stretch vs 20MA. An empty VIX read means condor NO-GO.
3. **Portfolio check** (every open spread and stock):
   - **Expiry this Friday:** short ITM or within 0.5% → **CLOSE (pin)**.
   - **Earnings** on or before expiry → **EARN**.
   - **News** (shares the step 6 search) → **NEWS** if material.
   - **Cushion** = (spot − short) ÷ spot.
4. **Gate 1a:** snapshot all 25 (`last`, `implied_vol_underlying`, `historical_vol`, `top_status`). Drop a name if IV is more than 15 points below what it needs (0.15Δ names → 27%; NVDA/TSM 0.20Δ → 18%). An empty IV read doesn't drop the name.
5. **Gate 1b, trend:** for survivors, pull 21 daily bars. Spot must be above SMA20 (prior 20 completed bars). A margin under 2% → `prov`.
6. **Gates 2–3:** earnings from the cache. Then **one** news search covering survivors **and** held names. A material negative catalyst vetoes the name.
7. **Held names:** keep them. If a candidate is already held, say so in its recommendation (existing expiry and qty).
8. **Sizing** (no credit pricing — JH checks credit at ticket):
   - Width = 5% of spot, rounded up to the next listed strike (one `get_option_data` call per candidate to confirm strike spacing, if unsure). Min $5.
   - Qty = SIZE ÷ (width − 0.10 × width), round down. Check the total exposure cap.
9. **Output** as the §6 visual. Nothing else.

**Call budget:** ~60–75. If a session goes past ~90 calls, stop and check what's running.

---

## 6. OUTPUT FORMAT (visual, fixed)

Render the whole result as **one inline visual** (Visualizer `show_widget`; load `read_me` mockup first). No text tables, no commentary before or after except one short line. If the visual tool isn't available, use the same sections as markdown tables.

**Must work on desktop and mobile:** grids use `repeat(auto-fit, minmax(...))` so they reflow; `box-sizing: border-box`; nothing clipped at the right edge. Compact rows (~5px padding, 14px text), light/dark safe CSS variables only.

**1. Regime** — 4 small metric boxes (4 across on desktop, 2×2 on mobile):
- Hedge (`Live` / `None`) · **Room to 60%** = 0.60 × cash − max loss of open spreads, shown as `$<x>k · ~<n> spreads` (n = room ÷ (NetLiq × 5%)) · Expiry (`4 Dec · 18 DTE`) · Data (`13 Nov close` or `Live`)
- Condor only if GO (otherwise omit).
- Do **not** show VIX, SPX vs 20MA, NetLiq, cash, SIZE, feed.

**2. Candidates** — every name that passed Gates 1–3, **held or not**, grouped by cluster (Semis, Security, Mega-cap, Software, High-beta, Networking, Healthcare, Financial, Energy, Industrial, Consumer). One card, a small cluster label above each group, one row per name:

| Name | Width | Qty | Recommendation |
|---|---|---|---|

- Qty = SIZE ÷ (width − 10%W credit), round down.
- **Top pick** tag (green) on up to *n* names (n from Room): prefer names not already held, then clusters with the fewest open names, then the strongest trend (but not > 8% stretched).
- Recommendation = judgment beyond the credit check (JH checks credit at ticket): trend strength (flag if < 2% above 20MA), concentration (how many names already open in the same cluster / tech), whether this name is already held (expiry, qty), news, events soon after expiry. Amber with warning icon if any concern; plain if clean.
- Do **not** show sell/buy strikes, credit, Δ, expiry, max loss, spot, IV, 20MA %, earnings date.
- If none → one line: `No candidates.`

**3. Portfolio** — header line: `<n> spreads · $<x>k at risk (<x>% of NetLiq)`. One card per expiry, nearest expiry first, cards side by side on desktop (`minmax(300px,1fr)`), stacked on mobile. Inside each card, sort **alphabetically**:

| Spread | Qty | Cushion | Action |
|---|---|---|---|

- Spread = `TICKER short/long` (no expiry, no ×qty). Qty in its own column (`5+5` for split longs).
- Action pill:
  - **Close** (red): expiry-Friday pin only (short ITM or within 0.5% on expiry day).
  - **Watch <short>** (amber, cushion also amber): cushion < 3%.
  - **Hold** (grey): everything else.
- Add `· Earn` / `· News` to the pill text if earnings before expiry or material news.

**Do not show:** an ACTIONS section (closes appear as red pills), caps, a SCREEN / skipped list, stock holdings, EXCEPTIONS.

---

## 7. STANDING NOTES

- **Expect drawdowns.** Backtest (2 per name, hold): a −10% year (2021), a flat year (2018), worst drop ~37% (2025 tariffs). COVID-type crashes hit ~−24%. Most of the drop comes in days; recovery takes months. Don't change rules mid-drawdown.
- **Floor and width are a pair.** Credit as %W falls as width widens. On narrow widths almost everything passes the floor.
- **No exit rule.** ~15% of trades breach the short; ~40% of those recover by expiry, ~24% go to full loss (= ~5% of NetLiq each). Exiting cost ~10 pts/yr and didn't lower max drawdown (only cushioned fast crashes like COVID).
- **Return ≈ drawdown.** In this model, ~20% a year needs ~25–30% drawdowns. Raising risk or lowering the floor further moves along that line, not off it.
- **Real IV premium is the biggest unknown.** ±10% IV swings return a lot. **Log entry IV and the realised move at expiry.**
- **Where the strategy earns:** high-IV rebounds after a selloff (2020, 2023). Calm bull markets → fewer trades. Sudden crashes hit hardest when holding to expiry.
- **Sector stacking caused the Oct 2026 loss:** 3 semis + 2 security, PANW oversized. No caps now, so check the book before adding a 3rd name from one sector.
- Backtests use modelled option prices; the live chain wins. Universe is survivorship-selected. No earnings gaps or 2008-type crash in the data.

**Rejected — don't re-propose:**
- take-profit early close
- $10 or $30 flat widths
- per-name or vol-scaled widths
- blanket 0.18/0.20Δ
- 0.12 / 0.08Δ
- DTE outside 18–21
- 200-day MA gate
- always-on condor
- loosening Gate 1
- floor 8%W or lower (more trades, ~2.5× drawdown, less return than 9–10%)
- exit at 2% above short (more whipsaw, no extra protection)
- exit rule at short strike (tested 2015–26: −10 pts/yr, same max DD) — dropped 14 Nov 2026

---

*File convention: highest suffix wins. Evidence: `claude/loss-review-2026-11.md`, `claude/floor-test-2026-11.md`. Scripts: `claude/loss_review_bt.py`, `claude/cap_sweep.py`, `claude/fetch_prices.py`.*
