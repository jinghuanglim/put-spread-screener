<!-- JH — 10 Sep 2026 · Universe cut 28→20. Gate order flipped: IV pre-filter before trend histories. Supersedes 2-1-11. -->
 
# Put Credit Spread v3.9 — Core (2-1-12)
 
*Supersedes 2-1-11. **No change to floor, DTE, deltas, width basis, sizing, caps, exit rule or gate logic.** Two changes: the **universe drops from 28 names + 3 index slots to 20 names**, and **Gate 1 is reordered** so the cheap IV read runs before the expensive history pull. Both are cost changes. Neither alters what a passing name looks like. Rationale archive remains 2-1-1. Not financial advice.*
 
---
 
## WHAT CHANGED AND WHY (2-1-12)
 
### 1. Universe cut 28 + 3 → 20
 
2-1-11 fixed *how* the screen runs. It did not question *what* it runs over. The IV-needed table already answered that and the answer was not read.
 
At 0.15Δ and 18 DTE the 12%W floor implies a **~60% IV name**. A name whose vol never approaches that, and which carries no delta fallback to lower the bar, is a call spent every night for an outcome that is fixed in advance.
 
**Cut (11):**
 
| Name | Typical IV | Bar it had to clear | Why cut |
|---|---|---|---|
| ADBE | ~28% | 60% — no fallback | Unreachable |
| CAT | ~25% | 60% — no fallback | Unreachable · $4,100 contracts |
| GS | ~24% | 60% — no fallback | Unreachable · $5,200 contracts |
| INTU | ~28% | 60% — no fallback | Unreachable |
| LLY | ~30% | 60% — no fallback | Crisis-only |
| QCOM | ~30% | 60% — no fallback | Crisis-only · closest to width pre-filter line |
| TXN | ~25% | 60% — no fallback | Unreachable |
| UNH | ~35% | 60% — no fallback | Crisis-only |
| SPY / QQQ / IWM | 15–20% | 60% flat, **no fallback ever** | Structurally unreachable |
 
**Kept despite a low anchor bar:** JNJ, MSFT, V, JPM, CRM, META, PANW, ANET, AAPL, GOOGL. JH's call. JNJ and MSFT remain SKIP-on-fail; V, JPM, AAPL, GOOGL keep their fallbacks; CRM, META, PANW, ANET have none. **These are retained knowingly, not because they clear the floor often.**
 
**Index slots are gone from the screen.** SPY is still pulled at Steps 6/6b for the tail hedge — that is a position check, not a candidate.
 
**The eight named cuts were carrying no fallback.** That is what made them dead weight rather than rare. A name at 30% IV with a 0.20Δ fallback needs 33% and is live; a name at 30% IV pinned at 0.15Δ needs 60% and is not.
 
### 2. Gate 1 reordered — IV read before trend histories
 
Gates are described as cost-ordered. They were not. `get_price_history` at 22 bars is the **most token-expensive per-name call in the session**, and it was running on every name before anything cheap had a chance to drop them.
 
A `get_price_snapshot` returning `last · top_status · implied_vol_underlying · historical_vol` is a few lines. A 22-bar history is 22 OHLCV rows.
 
**New order: snapshot everything, then pull history only on names whose IV is in range.**
 
| | 2-1-11 | 2-1-12 |
|---|---|---|
| First pass | 20 histories (heavy) | 20 snapshots (light) |
| Second pass | ~8 snapshots | ~5–8 histories (heavy) |
| Calls | ~28 | ~25 |
| Tokens on this block | baseline | **roughly −60%** |
 
**Three problems solve themselves as a side effect:**
 
- The **Gate 1 snapshot re-check rule** (2-1-11: pull a snapshot for any name within ~2% of SMA20) is **deleted**. Every name now has a snapshot before any bar is read. There is nothing to re-check.
- The **intraday drift problem is gone at Gate 1.** Every spot compared against SMA20 comes from the snapshot, never the in-progress bar. The 19 Aug GOOGL failure mode cannot recur here.
- **`top_status` is read on every name before any price is used**, rather than on survivors only. REJECT names drop before costing a history pull.
### 3. No batching exists — confirmed, do not look again
 
`get_price_history` and `get_price_snapshot` each take **one `contract_id`**, verified against the live tool schema 10 Sep 2026. There is no multi-contract parameter on either. **One name = one call, always.** Call count is floored by universe size; only token weight per call is controllable. This is why the universe cut and the reorder are the only two levers that exist.
 
### 4. Payload trims — free, no logic change
 
- Gate 1 history `step_count` **22 → 21**. Twenty completed bars plus the in-progress one is exactly what the SMA needs. The 22nd was never used.
- VIX history `step_count` **6 → 2**. One close is read. Five extra 5-min bars were discarded every session.
---
 
## UNIVERSE
 
**20 names:** AAPL, AMD, AMZN, ANET, AVGO, CRM, CRWD, DELL, GOOGL, JNJ, JPM, META, MSFT, NFLX, NVDA, PANW, PLTR, TSLA, TSM, V
 
**No index slots.** SPY, QQQ and IWM are not screened. SPY appears at Steps 6/6b only, as the tail hedge.
 
**There is no screener input.** The screen runs off this list.
 
**NFLX is width-excluded every session** (~$76–80 post-split, 5%W ≈ $4). It is retained in the list by JH decision and costs one snapshot per session for a guaranteed skip. Opt in explicitly at a wider width, or drop it.
 
---
 
## CONTRACT IDS (authoritative — read here, never from recall)
 
| Ticker | ID | | Ticker | ID |
|---|---|---|---|---|
| AAPL | 265598 | | META | 107113386 |
| AMD | 4391 | | MSFT | 272093 |
| AMZN | 3691937 | | NFLX | 15124833 |
| ANET | 740948854 | | NVDA | 4815747 |
| AVGO | 313130367 | | PANW | 110619459 |
| CRM | 29624264 | | PLTR | 444857009 |
| CRWD | 370757467 | | TSLA | 76792991 |
| DELL | 346218218 | | TSM | 6223250 |
| GOOGL | 208813719 | | V | 49462172 |
| JNJ | 8719 | | | |
| JPM | 1520593 | | | |
 
**Not screened, still required:**
 
| Purpose | Ticker | ID |
|---|---|---|
| Regime | VIX | 13455763 (`exchange=CBOE`, `security_type=IND`) |
| Tail hedge, Steps 6/6b | SPY | 756733 |
 
**Retired from the screen (IDs kept for reference only):** ADBE 265768 · CAT 5437 · GS 4627828 · INTU 270662 · LLY 9160 · QCOM 273544 · TXN 13096 · UNH 13272 · QQQ 320227571 · IWM 9579970.
 
All verified live 6 Sep 2026 via `search_contracts`. Full re-verify monthly + after any universe change. **Next audit due 6 Oct 2026** — now 22 IDs, not 31.
 
Query traps still live: `V` not "Visa Inc" — single-letter `V` returns ~2,599 rows · `CRM` returns CRML, CRMD, CRMT — take NYSE / SALESFORCE INC.
 
**Precedence:** this table wins over any ID recalled in session or carried in a prior summary. Session of 17 Aug found recalled IDs scrambled across TSM/TSLA/V/PLTR/PANW/CRWD while the table values all returned correct instruments.
 
**Non-universe contract IDs seen in the book** (Step 6/6b only, not screened): COIN 481691285 · SPCX 890493863 · IBKR 43645865.
 
---
 
## EARNINGS CACHE (maintained — search only what is stale)
 
Verified 9–10 Sep 2026 unless noted. **Confirmed** = company IR or 8-K. **Est** = consistent pattern across sources, no IR release yet.
 
| Ticker | Next report | Status | Ticker | Next report | Status |
|---|---|---|---|---|---|
| AAPL | late Oct 2026 | est | META | 28 Oct 2026 | est |
| AMD | 3 Nov 2026 | est | MSFT | late Oct 2026 | est |
| AMZN | late Oct 2026 | est | NFLX | mid Oct 2026 | est |
| ANET | 3 Nov 2026 | est | NVDA | 18 Nov 2026 | est |
| AVGO | early Dec 2026 | est | PANW | mid Nov 2026 | est |
| CRM | 2 Dec 2026 | est | PLTR | early Nov 2026 | est |
| CRWD | early Dec 2026 | est | TSLA | 28 Oct 2026 | est |
| DELL | 24 Nov 2026 | est | TSM | 15 Oct 2026 | est |
| GOOGL | late Oct 2026 | est | V | late Oct 2026 | est |
| JNJ | mid Oct 2026 | est | | | |
| JPM | mid Oct 2026 | est | | | |
 
**Last confirmed reports on file:** DELL 1 Sep 2026 (Q2 FY27, beat, guidance raised) · CRM 2 Sep 2026 · AVGO 3 Sep 2026.
 
**Refresh rule:**
1. Name within **10 trading days** of its cached date → search, upgrade to confirmed, rewrite the row.
2. Name just reported → search once for the next date.
3. Blank or older than ~60 days → search.
4. Otherwise → **read the table, do not search.**
**A cached date never clears a name on its own inside the window.** If the cached date is within the expiry window, the name is blocked pending an IR-confirmed check — the cache saves searches on names nowhere near their date, which is most of them, most nights.
 
**Mid-October is now much lighter.** GS, TXN and UNH left with the universe cut; only JNJ, JPM, NFLX and TSM cluster there.
 
---
 
## DELTA ANCHORS
 
| Stock | Δ | Fallback |
|---|---|---|
| NVDA, TSM | **0.20** | TSM → 0.18 if tail discipline preferred |
| AAPL, AMZN, GOOGL | 0.15 | 0.18 |
| JPM | 0.15 | 0.18 (0.20 max) |
| V | 0.15 | 0.20 |
| JNJ, MSFT | 0.15 | **SKIP** — never step up |
| CRWD, META | 0.15 | **NONE** |
| CRM, DELL | 0.15 | **NONE** |
| AMD, ANET, AVGO, NFLX, PANW, PLTR, TSLA | 0.15 | — |
 
- Fallback fires only when live worst-case credit at 0.15–0.16Δ fails the **12%W** floor in chain. **That determination is JH's, at Step 7.** The screen never fires a fallback.
- Nearest listed strike counts (0.14–0.16 = 0.15). Hard cap 0.20Δ.
- **No chain sweeping upward until floor clears.** That's delta creep.
- **0.15 is settled downward** — dominant over 0.12 and 0.08 across a 10-year replay, a full-universe MC across three drift regimes, and a correlated portfolio MC.
- **0.15 is settled upward at the current width (2-1-9).** 0.18 at 5%W passed 2 of 18 cells, both bull/low-correlation. At rho=0.6, worse on median in 8/9 and worse on CVaR-5% in 9/9, P95 drawdown roughly doubling. **Closed. Do not re-propose at 5% width.**
- **The conditional fallback table above is unaffected.** It was never the blanket-0.18 proposal; it fires per-name only when the floor fails, a different and much rarer object than trading every name at 0.18.
- **Fallback rates are higher than the wording implies.** A 10-year replay found GOOGL, V, JPM, AMZN and AAPL on the fallback delta 85–93% of the time under the old 11%W floor. At 12%W this is higher.
- **The cut removed eight no-fallback names and kept four (CRWD, META, CRM, DELL).** The surviving no-fallback names run 30–45% IV against a 60% bar. Expect them to clear rarely. They were kept deliberately.
---
 
## STRATEGY
 
| Parameter | Setting |
|---|---|
| Width | ~5% of spot, listed strikes — **hard min $5, no maximum.** Flat $30 max rejected; per-name tiers rejected (2-1-10) |
| Entry | Daily scan; enter any day gates pass AND capacity exists |
| DTE | **18–21 hard range. Prefer 18.** Both 22–25 and 7–14 tested and rejected |
| Short Δ | Anchor table above |
| Credit floor | **≥12% of width, worst-case (short at bid, long at ask). JH verifies live at ticket** |
| Exit | **HOLD TO EXPIRY. No defensive close. No take-profit. No mid-trade orders of any kind** |
| Sizing | ~7% risk/name · 50% max total open exposure (max-loss basis, vs session-start IBKR cash) — **conditional on live tail hedge** |
| Concurrency | ~6–7 typical; cash to T-bills / IBKR pays interest on idle USD |
| Tail hedge | SPY put spread long ~25% OTM / short ~40% OTM, 3-month, rolled quarterly, ~0.4–0.5%/yr |
| Hedge lapse | Cap reverts to **25%** |
| Condor overlay | GO: VIX ≥20 AND SPX stretch −2%..+3% vs 20-MA AND no binary macro in window. Half-size, call floor 7%W, no call step-up. State GO/NO-GO each session. **VIX unreadable = NO-GO.** |
 
**The condor overlay survives the index cut.** It is a call side sold against a put spread already on the book, not an index position. Nothing about it depended on SPY/QQQ/IWM being screened as candidates.
 
**Daily cadence ≠ daily trades. Most days: zero entries.** Modelled throughput ~38 trades/yr against ~142 slot-fills of capacity — **the book runs at roughly 25% fill and that is structural, not a scheduling failure.** Shorter DTE was tested as a fix and made it worse. Widening was tested as a fix (2-1-10) and made it much worse — fill fell to ~19 trades/yr.
 
**Slot competition does not tighten under a smaller universe.** Concurrency stays ~7 and fill was already ~25%. The binding constraint is the floor, not the number of names queued against it.
 
**DTE availability.** The 18–21 window frequently has no listed Friday in it. Standard weeklies commonly present 16 DTE and 23 DTE with nothing between. **State the DTE and flag it; do not silently price an out-of-range expiry as if it were in range.** Which of the two to take is JH's call at Step 7.
 
**Width pre-filter:** spot under ~$100 → 5% width under $5 → name excluded unless JH opts in. NFLX excluded every session. **QCOM was the other name near this line and is now out of the universe entirely.**
 
**Structures defined in this system:** put credit spread (core) · iron condor via the conditional call overlay · SPY long put debit spread (tail hedge). **No debit/directional structure is authorised.**
 
---
 
## RULE 1 — LIVE PRICES ONLY
 
Every price — spot, IV, HV, VIX, SMA inputs — pulled live this session. No recall, no cached figures, no prior-session values, no price inferred from another price.
 
**No live price = no row.** Name dropped, not priced from an older figure.
 
**Rule 1 governs prices, not calendars.** The earnings cache is not an exception to it.
 
Delayed data doesn't abort scan — must be **declared** on regime line (`EST-DELAYED`), borderline rows provisional.
 
**Intraday drift — resolved at Gate 1 by the reorder (2-1-12).** A spot from the in-progress daily bar and a spot from `get_price_snapshot` can differ materially within one session. 19 Aug: GOOGL read 343.90 off the bar (short leg ITM) and 345.86 off the snapshot 40 min later (OTM, pin risk). Under 2-1-12 **every Gate 1 spot comes from the snapshot** — the bar supplies SMA history only, never a current price. The 2-1-11 "snapshot only within ~2% of SMA20" rule is deleted; it is now unconditional and free.
 
**Step 6b spots come from `get_price_snapshot`, never from the bar.** Unchanged.
 
### Sources
 
| Need | Tool | Parameters |
|---|---|---|
| Spot · IV · HV · status (Gate 1a) | `get_price_snapshot` | `market_data_names=['last','implied_vol_underlying','historical_vol','top_status']` |
| Daily bars (Gate 1b SMA only) | `get_price_history` | `step=ONE_DAY · step_count=21 · outside_rth=True · security_type=STK` |
| **VIX** | **`get_price_history`** | **`contract_id=13455763 · security_type=IND · exchange=CBOE · step=FIVE_MINS · step_count=2 · outside_rth=False`** |
| Positions | `get_account_positions` | none — **pull once per session, reuse for 5a/6/6b/EXCEPTIONS** |
| Balances (denominator) | `get_account_balances` | none — live `cash_balance`. **Retry once; on second failure defer to end of session and retry once more** |
| Fills (for EXCEPTIONS line) | `get_account_trades` | `period=DAYS_7` |
| ID verify | `search_contracts` | string; retry once on transient error |
 
**Neither price tool accepts more than one contract.** Verified against schema 10 Sep 2026. Do not spend calls rediscovering this.
 
**VIX source fixed 24 Aug 2026.** `get_price_snapshot` returns `{}` for the VIX index on every attempt — 5 failures across 3 sessions. `get_price_history` on the same contract returns bars normally. Take the last bar's close. The response carries `delayed: 900`, so the read is **15 minutes delayed — declare `EST-DELAYED` whenever VIX is sourced this way.** Tolerable for a GO/NO-GO threshold test at 20; not tolerable for a strike decision. An empty history response is a failed read and forces NO-GO.
 
**`get_option_data` is retired. `get_option_parameters` is retired. Neither is called by the screen, ever, for any reason.** No chain pulls, no expiration-id resolution, no per-leg bid/ask snapshots, no Black-Scholes strike solving. Pricing is Step 7 and it belongs to JH. This is the single largest cost in a runaway session and the most common drift from spec.
 
Cross-check must be **web**, never IBKR checking IBKR.
 
**Tool loading.** Load the tools the source table names, in one pass, before Gate 1a. Do not discover them by trial.
 
### `top_status` — mandatory field, read before price
 
`REALTIME` → proceed, label `EST` · `DELAYED` → proceed, label `EST-DELAYED` · `FROZEN`/`FROZEN_DELAYED` → row provisional · `REJECT` → drop name.
 
**Now read on all 20 names at Gate 1a**, before any history pull. A REJECT drops the name at zero further cost.
 
Declare worst status seen on regime line.
 
---
 
## STEP 0 — PRE-FLIGHT
 
- **0a ID integrity** — spot-check candidate spot prices vs an independent web source. Wrong ID produces a coherent price series for the wrong company; nothing downstream catches it. **Survivors only** — a wrong ID on a name that failed a gate costs nothing.
- **0b Session state** — 10 PM SGT = ~30 min after US open, so bar in progress. **Compute 20-SMA on the prior 20 completed bars; compare against the snapshot spot, never the bar.** Trend margins under ~2% provisional, flagged.
- **0c Freshness** — `top_status` first, then snapshot ts vs `user_time_v0`, then `delayed` field.
---
 
## GATES (cost-ordered — reordered 2-1-12)
 
### Gate 1a — IV PRE-FILTER (new position, not a new test)
 
One `get_price_snapshot` per name, all 20, returning `last · implied_vol_underlying · historical_vol · top_status`.
 
**Drop the name before its history is pulled if live IV is more than 15 points below IV-needed at its anchor delta and the target DTE.**
 
**Buffer is 15 points and it is deliberately generous.** Snapshot IV is blended across expiries and can diverge 9+ points from the traded one. A tight cutoff would drop live names on a bad read. Fifteen points is wide enough that this filter almost never changes an outcome — it only stops history pulls on names that were never in range.
 
**This is a cost filter, not a gate.** It has no veto authority over a name that reaches Step 7. The IV-needed table remains reference, never pass/fail, exactly as before — what changed is that a name obviously far from the bar no longer earns a 21-bar pull.
 
**On a failed or empty IV field:** do not drop. Pull the history and let Gate 1b decide. An absent read is not a low read.
 
### Gate 1b — TREND
 
Snapshot spot > 20-day SMA. **Absolute veto.**
 
`get_price_history`, 21 bars, **on Gate 1a survivors only**. SMA computed from the 20 completed bars; the in-progress bar is discarded.
 
**Loosening tested and rejected:** a 0.5% or 1.0% buffer, and SMA10, each added only 3–7% more trades at slightly worse quality, concentrated in TSLA and AMD. SMA10 degraded NVDA materially.
 
Margins under ~2% flagged `prov`. **No re-check call** — the governing spot was already a snapshot.
 
### Gate 2 — EARNINGS
 
None on/before expiry. Same-day reporter = auto-SKIP. Re-entry T+2 preferred; T+1 only at **≥15%W** + clean transcript.
 
- **Read the earnings cache first.** Search only per the refresh rule.
- **IR press release only** when searching. Aggregators conflict routinely. Sources disagree with no IR confirmation → name blocked.
- Searches are **narrow and per-name**, not broad market queries.
- **Macro density flag:** two or more macro events within 3 days of expiry → halve tranche size, declare on regime line. **Retained without the index slots** — macro density still governs tranche sizing on single names.
- **CRM and DELL have thin earnings history on file** and Gate 2 was never modelled in any MC.
### Gate 3 — NEWS
 
No material adverse catalyst (guidance cut, probe, downgrade cluster, sector contagion, litigation, M&A break). Veto regardless of premium richness.
 
- **One search, covering all survivors together.** Not one per name.
- Note the date on anything returned. Analyst actions from prior quarters recur in results and are not current catalysts.
- IV above HV only counts as edge if no earnings in window.
- **Final automated veto in screen.**
Gate 1a/1b/2/3 failure = dropped silently. Every survivor shown.
 
**There is no Gate 4 or Gate 5 in the screen.** Credit and liquidity (OI ≥500, bid/ask ≤10% of mid) are checked by JH at ticket, Step 7. **Load-bearing** — 51 candidate names were rejected on liquidity judgement the model could not measure. If CRM or DELL prints a wide book, that is information, not noise, and with logging removed it must be noted manually.
 
---
 
## SIZING & CAPS
 
Denominator: **IBKR cash at session start**, before any new tranche.
 
| | |
|---|---|
| Max total exposure | 50% (hedge live) / **25% (hedge absent)** |
| Per-name risk | ~7% |
| Implied concurrency | ~7 names |
 
Max loss per spread = (width − credit) × 100 × contracts.
 
**Sizing MC-validated and unchanged.** 7 slots × 7% risk had the best CVaR-5% of nine configurations at crash-regime correlation. **Slot count is a non-lever** — trades/yr sat at 33–36 whether 5, 7 or 9 slots were available. Risk-per-slot is the real dial. Conditional on the 12%W floor; re-run if the floor drops.
 
**Hedge gate binary.** Confirm live unexpired SPY put spread in `get_account_positions` → `HEDGE: LIVE · CAP 50%`. Absent, expired, or rolled late → `HEDGE: NONE · CAP 25%`. No partial credit, no grace period.
 
If IBKR ceases to be minority of total capital → cap reverts to 15%.
 
### Cluster caps — seven clusters (was nine)
 
| Cluster | Names | Max |
|---|---|---|
| Semis & hardware | NVDA, AMD, AVGO, TSM, DELL | 2 |
| Security | CRWD, PANW | 1 |
| Mega-cap platform | AAPL, MSFT, GOOGL, AMZN, META | 3 |
| Software | CRM | **1** — sole member, cap is now the member |
| High-beta | PLTR, TSLA | 1 |
| Healthcare | JNJ | **1** — sole member |
| Financial | V, JPM | 2 |
 
**Industrial (CAT) and Index (SPY/QQQ/IWM) clusters are dissolved** — no members remain.
 
**Software and Healthcare caps fell from 2 to 1 mechanically, not by decision.** With one member each, the cluster cap and the per-name cap are the same object. If either cluster regains a second member, restore the cap to 2 and note it.
 
**Caps stay advisory.** Enforcement was simulated and came back mixed (~4 points better P95 drawdown, ~0.8 median points worse, CVaR-5% slightly worse) — not a clear enough result for a risk control.
 
**Cluster caps count names because the risk is correlation, not size.** A cluster at its structural ceiling cannot register a worse count while actual concentration doubles.
 
**ANET and NFLX remain deliberately unclustered.** Still pending — and now the only two unclustered names in a 20-name universe, which makes the pending item more visible, not less.
 
### Step 5a — caps computed, not asserted
 
Every session, before table, print:
1. Total open exposure % vs operative cap
2. Per-name exposure for any name above 5%, vs 7%
3. **Cluster counts, all seven**, breaches marked
Computed from the single `get_account_positions` pull. No extra calls.
 
**A breach annotates rows, it does not suppress them (advisory).** Rows for breached names carry a `CAP` flag in the Note column naming the binding cap. JH decides whether to enter.
 
If Step 5a is not computed and printed, the session is incomplete and no entry should be made off it.
 
**Compute live every session. No carried figure appears here.**
 
**Denominator is IBKR cash, deliberately.** Capital held outside IBKR does not enlarge it. The only rule reading on outside capital moves the cap *down*.
 
---
 
## SESSION CALL BUDGET
 
| Block | Calls | Note |
|---|---|---|
| Tool load | ~1 | One pass, off the source table |
| VIX | 1 | `get_price_history`, `step_count=2` |
| Positions | 1 | Serves 5a, 6, 6b, EXCEPTIONS — **pull once, reuse** |
| Balances | 1–2 | Retry once, then defer to end of session |
| **Gate 1a snapshots** | **20** | All names. Light payload. Irreducible — no batching exists |
| **Gate 1b histories** | **~5–8** | Gate 1a survivors only. Heavy payload |
| Borderline re-checks | **0** | **Deleted — snapshot already governs** |
| Step 6b expiry spots | = Friday expiries, minus survivors already snapped | |
| Earnings searches | 0–2 typical | Cache first |
| News search | 1 | One search, all survivors |
| Trades (EXCEPTIONS) | 1 | |
| **Total, typical session** | **≈32–38** | Was ≈45–55 under 2-1-11 |
 
**If a session is tracking past ~45 calls, something is being run that this file does not ask for.** Stop and check against the workflow table before continuing.
 
---
 
## SESSION OUTPUT — TERSE SPEC
 
Order is fixed: **regime line → Step 5a → ONE table → Step 6 → Step 6b → EXCEPTIONS.** Nothing else.
 
**1. Regime line** — one line, pipe-separated:
`REGIME <date>` · VIX · SPX stretch vs 20-MA · macro in window · macro-density flag if fired · feed status · `HEDGE: LIVE · CAP 50%` or `HEDGE: NONE · CAP 25%` · condor GO/NO-GO · target expiry + DTE
 
**2. Step 5a caps** — bullets, not prose. Seven cluster counts.
 
**3. ONE table.** Header above it, every session, verbatim:
**"Gates 1–3 passed. Price each yourself; the 12%W floor is yours to enforce."**
 
| Ticker | Δ | Spot | Width | IV | IV needed | IV/HV | Note |
|---|---|---|---|---|---|---|---|
 
**No credit column. No strikes column. No %W column.** If those appear, chains were pulled and the session went out of spec.
 
- Every Gate 1a–3 survivor appears, subject only to width pre-filter.
- **Group rows by cluster**, count as `n/max` in the group header. Sort IV descending *within* group — **presentation order, not a ranking. MC-confirmed: no selection policy beat random.**
- Note column, abbreviated: `inv` · `prov` · `CAP` + binding cap · `no fallback` · blow-off stretch · FROZEN/DELAYED · `new` for CRM and DELL until each has traded once · `DTE n` where the target expiry falls outside 18–21.
- **Dropped:** one line, grouped by gate. Named, not explained. **Gate 1a drops are listed as `IV` — they are cost drops, not vetoes**, and must not be reported as if the name failed a test.
- Nothing passes → one line. Cash is a valid outcome.
**4. Step 6** — earnings re-check table.
**5. Step 6b** — expiry-week table.
 
**6. EXCEPTIONS line.** One line. Computed from the `get_account_trades` and `get_account_positions` pulls already made — no file, no append, no re-read.
 
Triggers:
- Sub-floor fill below 12%W — name it with its actual %W
- DTE at entry outside 18–21
- Any open position marked above 2.5× credit received
- First fill on CRM or DELL — state actual bid/ask and OI
Nothing fired → `EXCEPTIONS: none`.
 
**Prose is permitted only where a number would mislead without it.** One or two sentences, then stop.
 
**IV needed for 12%W** (5%-of-spot width) — reference only, never pass/fail:
 
| Δ | IV @ 18 DTE | IV @ 21 DTE |
|---|---|---|
| 0.15 | **60.3%** | 55.9% |
| 0.16 | **52.5%** | 48.7% |
| 0.17 | **46.2%** | 42.8% |
| 0.18 | **40.9%** | 37.9% |
| 0.20 | **33.1%** | 30.6% |
 
Caveats, mandatory whenever shown: applies a flat 0.90 haircut, which understates real bid/ask drag · snapshot IV blended across expiries, can diverge 9+ pts from traded expiry · not a gate.
 
**This table now does two jobs.** It tells JH which survivors are worth pricing first, at zero marginal cost — and, minus the 15-point buffer, it is the Gate 1a cost filter. **The second use does not promote it to a gate.** A name inside the buffer still passes to Step 7 untouched by it.
 
**This table also explains 2-1-12's universe cut.** Eight names were pinned at 0.15Δ with no fallback against a 60.3% bar while running 24–35% vol. That is not a rare setup, it is an unreachable one.
 
---
 
## WORKFLOW (nightly ~10 PM SGT)
 
| Step | Who | What | Budget |
|---|---|---|---|
| 0 | Claude | Load tools · pre-flight: session state · freshness | ~1 |
| 1 | Claude | Regime + condor GO/NO-GO · **assert hedge status → set operative cap** | ~3 |
| 2a | Claude | **Gate 1a — snapshots on all 20: spot, IV, HV, `top_status`** | **20** |
| 2b | Claude | **Gate 1b — trend histories on Gate 1a survivors only** | **~5–8** |
| 3 | Claude | Gate 2 vs earnings cache (search only if stale) · Gate 3 one news search | 1–3 |
| 4 | Claude | Width pre-filter → ID sanity check on survivors | **0 — IV/HV already held from 2a** |
| 5a | Claude | Compute and print caps block — advisory, seven clusters | 0 (reuses positions) |
| 5 | Claude | Candidate table — **no prices, no strikes** | 0 |
| 6 | Claude | Open-position earnings re-check (cache first) | 0–2 |
| 6b | Claude | Expiry-week check | = Friday expiries not already snapped |
| 7 | **JH** | Price each live in mobile: worst-case credit at anchor Δ, **12%W floor**, OI ≥500, bid/ask ≤10% of mid | — |
| 8 | Claude | **EXCEPTIONS line** — one line, no files | ~1 |
 
**Step 4 is now free.** Under 2-1-11 it pulled IV/HV snapshots on survivors. Gate 1a already holds them. Step 4 is a width check and an ID sanity check against web, nothing more.
 
---
 
## STEP 6 — OPEN-POSITION EARNINGS RE-CHECK
 
Gate 2 clears a name against the calendar as it stands on entry day. Companies announce 2–4 weeks ahead, so a date can land inside the window after entry.
 
1. Group legs by underlying + expiry from the positions pull already made.
2. Re-check earnings date per pair — **cache first, search only if stale**.
3. Flag any report on or before expiry.
4. Short table; clear positions listed, hits flagged.
5. **Claude flags, JH decides.** No automatic action.
**Covers non-universe holdings, and now covers the eleven cut names too.** A name dropped from the screen is not dropped from the book. Anything open on ADBE, CAT, GS, INTU, LLY, QCOM, TXN, UNH, SPY, QQQ or IWM is still checked here until it expires. **Cutting a name from the universe never cuts it from Steps 6 and 6b.**
 
**Report a clearance as narrow when the date falls within 7 days after expiry.**
 
---
 
## STEP 6B — EXPIRY-WEEK CHECK (standing)
 
Every session, every open position expiring **this Friday**. Universe, cut names and non-universe alike. Spots from `get_price_snapshot`, never from the in-progress bar.
 
| Ticker | Spread | Short | Spot | OTM/ITM by ($ and %) | Action |
|---|---|---|---|---|---|
 
- Sorted by distance ascending — tightest first.
- Action drawn from the EXPIRY & ASSIGNMENT table. Pin-risk band ~0.5% either side.
- Non-universe and cut-universe positions italicised, noted covered / cash-secured where applicable.
- One summary line: `n of m clean`.
- **Close cost** stated in $ for any row marked close, and net roll-off restated.
- **Early assignment line:** state whether any short is deep ITM, and flag ex-div proximity **where a short call exists**.
- **Reuse Gate 1a spots.** Every one of the 20 names now carries a fresh snapshot from Step 2a, so an expiring universe position needs no second call. Only cut-universe and non-universe expiries cost anything here.
- Empty week → one line.
---
 
## EXPIRY & ASSIGNMENT
 
| State at expiry Friday | Action |
|---|---|
| Both legs OTM | Let expire |
| Short ITM, long OTM | **Close spread** |
| Both ITM | Both exercise, net = width; closing cleaner |
| Short ITM by pennies | **Pin risk — close** |
| **Short OTM by pennies** | **Pin risk — close.** Sitting on the strike is the risk, not the side of it |
 
Early assignment possible any time short leg deep ITM, most often around ex-dividend on JNJ, JPM and V among remaining names. **Ex-dividend early assignment is a short-call risk. It does not apply to the short puts in this book** — note it when a covered call is in the account, not on the core structure.
 
**Pin-risk band: short strike within ~0.5% of spot, either side.**
 
**Close-cost pricing is the one permitted exception to the no-snapshot-on-options rule** — a row marked close needs a dollar figure, which is 2 snapshots on that spread's legs. Only for rows actually marked close, and only the legs of those rows.
 
---
 
## STANDING CONSTRAINTS
 
- Cash is a valid outcome. Gates are hard vetoes, not quotas.
- **Credit 12%W vs max loss 88%W → 7.3 full wins erased by one full loss.** 12% is a minimum-viability price filter, not a safety margin.
- Clearing the floor proves nothing about EV.
- **Easy floor clearance is a warning, not an opportunity.** The names that cleared 12%W most often (COIN 43.7/yr, APP 35.3/yr, NET 12.1/yr) were high-vol names that lost money.
- **Universe composition is a real lever; selection within it is not.** 2-1-12 pulls that lever for cost, not for edge — **and that distinction must be preserved.** The cut names were removed because they never cleared the floor, not because a model said dropping them improves returns. No such model was run.
- **Name-level diversification is bounded by the floor.** 12% at 0.15Δ implies a ~60% IV name. Utilities are structurally unreachable — NEE, SO, DUK, AEP, D, EXC, SRE, XEL, ED and PEG all clear it under ~0.3 times a year. **The eleven names cut in 2-1-12 were closer to that group than to the tradeable core.** Only real controls: sizing, tail hedge, cash.
- **Width must scale with spot, and 5% is the setting.** Fixed $10, fixed $15, a $30 maximum, and per-name 7%/5% tiers were each tested and each was worse. Confirmed four separate ways.
- **The book runs at ~25% fill and that is structural.**
- **At a fixed %W floor, every structural parameter is also an entry filter (2-1-10).** Delta up loosens it. Width up tightens it. State expected trade count before running any structural test.
- **A universe cut is not exempt from that rule, and 2-1-12 does not fully satisfy it.** See PENDING — the expected trade-count effect is argued, not measured.
- **No position-level circuit breaker exists.** Positions will sit at −300% of credit with no action available. Do not improvise a stop.
- Universe is survivorship-selected; every per-trade mean is an upper bound.
- Stacking across adjacent expiries is the live exposure risk, not per-name size.
- **A convention is not a limit.** Only computed percentages against a stated denominator govern.
- **A backtest is not an MC.** The 9%W override for LLY/MSFT/V passed a 10-year replay convincingly and was destroyed by MC (CVaR-5% −2.55 → −48.69).
- **A model cannot see a spread.** The 60-name expansion beat the 9-name expansion on every modelled metric and was rejected anyway. Where the model and the chain disagree, the chain wins.
- **Model bias runs toward optimism.**
- **An operationally impossible improvement is not an improvement.** 0.20Δ/10% width is the best-evidenced setting found and is not adopted.
- **A composite result may not survive decomposition (2-1-10).**
- **Correlation, not skew, is where up-delta proposals die (2-1-9).** Any structural proposal must be swept on rho; a result holding only at rho=0.3 is not a result.
- **An MC whose baseline does not reproduce production is not evidence (2-1-9).** Print trades/yr and median CAGR for the current setting first and compare to ~38 and ~16.6%.
- **A generator without drift is a bear-market generator (2-1-9).**
- **A path-maximum is not a per-contract size (2-1-10).**
- **A screen that cannot finish is a screen that did not run (2-1-11).**
- **Where session behaviour and this file disagree, this file wins (2-1-11).**
- **Cost order must match actual cost, not assumed cost (2-1-12).** Gates were labelled cost-ordered for four versions while the single heaviest per-name call ran first, on every name, unconditionally. **Check the payload, not the label.**
- **Dropping a name from the screen does not drop it from the book (2-1-12).** Steps 6 and 6b read positions, not the universe.
---
 
## PENDING
 
### Open against 2-1-12 itself — trade-count effect unmeasured
 
The doc's own rule is that any structural change states its expected trade count first. **This one does not, and that is a known gap, not an oversight to be discovered later.**
 
The argument for a near-zero effect: the eleven cut names ran 15–35% IV against a 60.3% bar with no fallback, so they should have been clearing the floor a fraction of a time per year each. If so, removing them costs almost nothing.
 
**That is an argument from the IV-needed table, not a measurement.** Nobody counted how often those names actually cleared 12%W in the chain.
 
**Cheap way to close it:** on the next few sessions, note whether any cut name would have appeared as a Gate 1–3 survivor. If the count is near zero over a month, the cut is confirmed and this item closes. If cut names were surviving regularly, revisit — especially LLY, UNH and QCOM, the three closest to the line.
 
**Do not treat the cut as validated until that count exists.**
 
### Next test — rolling losers
 
**Still the live one.** Every premium-side lever that does not require a sizing change is closed. What remains untested is the loss side, and it is the larger number: the book pays 12%W and risks 88%W, so **one full loss erases 7.3 full wins.**
 
- **Rule to test:** at expiry, when the short leg is ITM, roll the spread out to the next 18–21 DTE cycle at the same delta anchor rather than realising the full −88%W. Compare against hold-to-expiry.
- **Variants in one run:** roll only when the name still passes Gate 1 · roll at most once per position · roll for a credit only, never a debit.
- **Why it might work:** it is the only idea on file that changes the loss distribution rather than the win rate.
- **Why it might not:** rolling a loser adds size to a losing name exactly when correlation is rising. Expect it to look good at rho=0.3 and be decided at rho=0.6.
- **Must report:** trades/yr both arms · P95 drawdown · CVaR-5% · roll frequency · worst chain length.
- **Adoption bar:** better on median AND not worse on CVaR-5%, all three skews, both rho regimes, rho=0.6 decisive.
- **Reuse:** `mc_width_tiers.py` has the corrected generator, drift sweep, jump compensation, IV premium and baseline check.
- **Rebuild the universe list in the MC to the 20 names before running**, or the baseline will not reproduce production.
- **Shares most of its build with the exit-rule MC — do both in one script.**
### Everything else
 
- **Simulate the tail hedge.** Feasible now. Still the only untested lever aimed at correlated bad years. *(Hedge itself is live — SPY 575/460 Dec 2026 ×3 — so this is a modelling item.)*
- **Exit rule MC.** Hold-to-expiry vs the 2.5× close was validated only on the live whipsaw ledger (140 whipsaws vs 60 saves). Build alongside rolling losers.
- **Verify CRM and DELL live.** Note actual bid/ask and OI on the first ticket of each. **Seven of the nine 2-1-7 additions were cut before they ever traded** — the expansion is now effectively a two-name expansion and should be judged as one.
- **PANW universe decision.** Negative mean %W across the 10-year replay (−0.19%W at 0.15Δ over 1,526 trades, lowest win rate). ANET near-zero (+0.78%W). Neither is a delta problem. Decide: keep, halve, or drop. **More pressing at 20 names than at 28.**
- **September seasonality gate** — the one month whose negative edge survived robustness testing. Never tested as a rule. Cheap.
- **Earnings/news gate simulation still blocked.** No free source for 10 years of earnings dates. **Now only 20 tickers, which makes a free-tier API key more likely to suffice.** Would settle the AMD question (−0.30%W over 146 trades) and let the cache self-maintain.
- **Cluster assignment for ANET and NFLX.** Now the only unclustered names.
- **NVDA / TSM 0.20Δ dedicated MC before any size-up.** Stands.
- **NFLX** — still width-excluded, still listed, costs one snapshot per session. Opt in at a wider width or drop.
- **QQQ 690/680 ×5 (21 Aug)** — recorded at 26.9%W, roughly double any other fill. Reconcile against the broker statement. **QQQ is no longer screened; this open item is unaffected.**
- **DTE availability is a standing friction.** 9 Sep offered 16 DTE and 23 DTE with nothing in the 18–21 window. Needs counting across sessions before it becomes a proposal.
- Contract ID re-verify due **6 Oct 2026** — 22 IDs.
### Rejected — do not re-propose
 
Take-profit early close · width change $10 vs $15 · $30 max width · per-name width tiers 7%/5% (2-1-10) · blanket 0.18Δ at 5% width (2-1-9) · 0.20Δ at 5% width · shorter DTE (7/10/14) · longer DTE (22–25) · 200-day MA regime gate · always-on condor · candidate-selection ranking · Gate 1 loosening (0.5%/1.0% buffer, SMA10) · delta 0.12 (declined) · delta 0.08 (rejected three times) · 9%W override for LLY/MSFT/V · **batched multi-contract price calls (no such parameter exists — 2-1-12)**.
 
---
 
## FILE CONVENTION
 
This file: `put-spread-workflow-2-1-12.md`. Suffix increments on replacement. **Always read the highest suffix.** Rationale and evidence archive: `put-spread-workflow-2-1-1.md`.
 
*(2-1-12 supersedes 2-1-11. No change to floor, DTE, deltas, width, sizing, caps, exit rule or gate logic. Universe cut 28 + 3 index slots → 20 names, on the ground that eleven names were pinned at 0.15Δ with no fallback against a 60.3% IV bar. Gate 1 split into 1a (snapshot: spot, IV, HV, status — all names) and 1b (history: SMA — survivors only), reversing an order that ran the heaviest per-name call first. Borderline snapshot re-check deleted as redundant. History step_count 22→21, VIX step_count 6→2. Cluster caps 9→7. Call budget ≈45–55 → ≈32–38. Open gap on record: the trade-count effect of the cut is argued from the IV-needed table, not measured.)*
 