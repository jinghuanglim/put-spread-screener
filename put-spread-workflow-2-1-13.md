<!-- JH — 17 Oct 2026 · Two-tier screen (volatile 12%W / calm 10%W). Caps made hard + tech cap 4. Universe 20→25. Supersedes 2-1-12. -->

# Put Credit Spread v4.0 — Core (2-1-13)

*Supersedes 2-1-12. **No change to DTE, width basis, per-name risk, total exposure cap, exit rule, gates 1b–3 or hedge rules.** Four changes: (1) the screen runs on **two tiers split by volatility** with different credit floors, (2) **cluster caps are now hard limits** and a new **tech cap (max 4)** is added, (3) the **universe changes 20 → 25**, (4) **calm-tier fallbacks are suspended** (the lower floor replaces them). Rationale archive remains 2-1-1. Not financial advice.*

---

## WHAT CHANGED AND WHY (2-1-13)

### Trigger — Oct 2026 tech selloff

Account fell ~12.6% (12→16 Oct). Every open spread was tech; semis held 3 vs cap 2, security 2–3 vs cap 1. Caps were advisory, so nothing stopped it. Separately, ~60% of the paper loss sat in non-system stock (NFLX, COIN) and several tickets broke the rules (see TICKET DISCIPLINE).

### 1. The 12%W floor is a volatility filter

At 0.15Δ / 18 DTE, 12%W needs ~60% IV. Only fast names clear it — in practice semis, security and AI-linked tech. Calm names (tech or not) almost never pass. **The floor, not the universe list, was choosing the sector.**

### 2. Two tiers, split by volatility — sector does not matter for the floor

| Tier | Floor | Rule |
|---|---|---|
| **Volatile** | **12%W** (unchanged) | Median 1-yr realised vol > 35% |
| **Calm** | **10%W** | Median 1-yr realised vol ≤ 35% |

Calm names at 10%W are still priced at **0.15Δ, 5% width**. Only the floor differs.

### 3. Caps become hard limits

- **Cluster caps enforced.** A capped cluster's names do not appear as candidates.
- **New: max 4 tech spreads open**, across both tiers (calm tech counts).
- 2-1-12 kept caps advisory because enforcement alone tested mixed. In 2-1-13 testing, **caps cut drawdowns and the calm tier won back the return caps gave up.** The combination is what earns adoption, not either part alone.

### 4. Evidence (tier_test.py, 17 Oct 2026)

Backtest, real prices 2014→16 Oct 2026, option prices modelled (Black-Scholes on realised vol, **no pricing edge**), 7% risk, 7 slots, trend gate, hold to expiry, mean of 5 entry orders.

| Window | Current rules (A) | 2-1-13 (D) |
|---|---|---|
| Full history CAGR | 9.7% | **11.3%** |
| Full history max DD | 25.7% | **21.6%** |
| 2025 tariff selloff: return / max DD | 8.5% / 25.7% | **11.7% / 19.0%** |
| Recent 2026 tech selloff: worst 20 days | −5.6% | **−3.0%** |
| 2022 bear: return | −10.2% | −11.1% (≈ same) |
| 2022 bear: max DD | 15.4% | **20.3% (worse)** |

**Read these correctly:**
- **Caps did the work in the tech selloff.** Calm non-tech names made 0% of trades in the recent window — when only tech falls, calm names stay calm and their premium stays under 10%W.
- **The calm tier adds return over time** (~15% of all trades are calm non-tech) and fills slots the caps leave empty.
- **Broad bear markets are worse** (more open positions). The SPY hedge and the 50% exposure cap are the defence there.
- Prior sleeve tests (lowvol_pcs_test.py) chose the floor and delta: **9.5–10%W best**; **0.15Δ beat 0.18/0.20** (0.20 lost 7.7% in 2022); **vol-scaled width lost** (twice the full-loss rate); survived fills at 80–85% of mid but trade count fell to ~2–3/yr.
- **No-edge MC:** calm 10%W and tech 12%W both came out ≈ flat. The test is fair, not tilted.

### 5. Under the rules, the model lost far less than the account

In the recent window the model's rule-following book took ~−5% and **no spread settled at a loss**. The account took −12.6%. The gap is ticket discipline, not the screen. See TICKET DISCIPLINE.

---

## UNIVERSE (25)

| Tier | Names |
|---|---|
| **Volatile (12%W)** — 13 | NVDA, TSM, AMD, AVGO, PLTR, TSLA, DELL, CRWD, PANW, ANET, META, CRM, **CAT** |
| **Calm (10%W)** — 12 | JNJ, **MCD**, **COST**, V, JPM, AAPL, **HD**, **XOM**, MSFT, GOOGL, AMZN, **LLY** |

**Bold** = new in 2-1-13. **META and CRM moved to volatile** (~41% median vol). **NFLX dropped** — width-excluded every session at ~$70 (5%W < $5).

**Tier check (median realised vol, 252 days to 16 Oct 2026):** JNJ 17.4 · MCD 17.9 · COST 19.2 · V 21.2 · JPM 22.5 · AAPL 23.5 · HD 24.9 · XOM 26.1 · MSFT 28.2 · GOOGL 29.4 · AMZN 30.2 · LLY 34.0 ‖ NVDA 37.1 · TSM 38.0 · CAT 38.3 · META 41.0 · CRM 41.3 · PANW 43.1 · TSLA 43.9 · AVGO 44.1 · CRWD 49.7 · ANET 52.9 · PLTR 55.5 · AMD 63.6 · DELL 65.5

**Monthly tier review.** Re-run the tier check (tier_test.py prints it). A name moves tier only if it sits on the other side of 35% at **two consecutive monthly reviews** — no flipping on one noisy month. **Never re-tier mid-month because a selloff spiked vol.** LLY (34.0) and NVDA (37.1) are the borderline names.

**Contract size.** COST (~$45–50 width) and LLY (~$40 width) run ~$3.6–4.5k max loss per contract. Fine at current cash (7% ≈ $21.9k). If IBKR cash falls below ~$100k, swap COST→PG and LLY→MRK (verify IDs and tier first).

**There is no screener input.** The screen runs off this list.

---

## CONTRACT IDS (authoritative — read here, never from recall)

| Ticker | ID | | Ticker | ID |
|---|---|---|---|---|
| AAPL | 265598 | | LLY | 9160 |
| AMD | 4391 | | MCD | 9408 |
| AMZN | 3691937 | | META | 107113386 |
| ANET | 740948854 | | MSFT | 272093 |
| AVGO | 313130367 | | NVDA | 4815747 |
| CAT | 5437 | | PANW | 110619459 |
| COST | 272997 | | PLTR | 444857009 |
| CRM | 29624264 | | TSLA | 76792991 |
| CRWD | 370757467 | | TSM | 6223250 |
| DELL | 346218218 | | V | 49462172 |
| GOOGL | 208813719 | | XOM | **895178251** |
| HD | 7930 | | | |
| JNJ | 8719 | | | |
| JPM | 1520593 | | | |

**Not screened, still required:**

| Purpose | Ticker | ID |
|---|---|---|
| Regime | VIX | 13455763 (`exchange=CBOE`, `security_type=IND`) |
| Tail hedge, Steps 6/6b | SPY | 756733 |

**New IDs verified 17 Oct 2026** via `search_contracts`: CAT, COST, HD, LLY, MCD, XOM — all NYSE/NASDAQ primary US listings with OPT. **XOM is listed as "EXXONMOBIL HOLDINGS CORP" under a new ID (895178251)** — appears to be a corporate restructure; 21 daily bars and live price confirmed. Do not use any older XOM ID.

**Retired from the screen (IDs kept for reference only):** NFLX 15124833 · ADBE 265768 · GS 4627828 · INTU 270662 · QCOM 273544 · TXN 13096 · UNH 13272 · QQQ 320227571 · IWM 9579970.

Full re-verify monthly + after any universe change. **Next audit due 17 Nov 2026** — 27 IDs (25 + VIX + SPY). The 6 Oct audit was missed; the 17 Oct verification covered new names only.

Query traps still live: `V` not "Visa Inc" · `CRM` returns CRML, CRMD, CRMT — take NYSE / SALESFORCE INC · `HD` returns hundreds of HDFC/HD Hyundai rows — take NYSE / HOME DEPOT INC · `XOM` returns XOM2/XOMA/leveraged ETPs — take NYSE / EXXONMOBIL HOLDINGS CORP.

**Precedence:** this table wins over any ID recalled in session or carried in a prior summary.

**Non-universe contract IDs seen in the book** (Step 6/6b only, not screened): COIN 481691285 · SPCX 890493863 · IBKR 43645865 · NFLX 15124833.

---

## EARNINGS CACHE (maintained — search only what is stale)

Verified 9–10 Sep 2026 unless noted. **Confirmed** = company IR or 8-K. **Est** = consistent pattern across sources, no IR release yet. **Blank** = never searched → search on first session.

| Ticker | Next report | Status | Ticker | Next report | Status |
|---|---|---|---|---|---|
| AAPL | late Oct 2026 | est | JNJ | mid Oct 2026 | est — **likely reported, refresh** |
| AMD | 3 Nov 2026 | est | JPM | mid Oct 2026 | est — **likely reported, refresh** |
| AMZN | late Oct 2026 | est | LLY | | **blank** |
| ANET | 3 Nov 2026 | est | MCD | | **blank** |
| AVGO | early Dec 2026 | est | META | 28 Oct 2026 | est |
| CAT | | **blank** | MSFT | late Oct 2026 | est |
| COST | | **blank** | NVDA | 18 Nov 2026 | est |
| CRM | 2 Dec 2026 | est | PANW | mid Nov 2026 | est |
| CRWD | early Dec 2026 | est | PLTR | early Nov 2026 | est |
| DELL | 24 Nov 2026 | est | TSLA | 28 Oct 2026 | est |
| GOOGL | late Oct 2026 | est | TSM | 15 Oct 2026 | est — **likely reported, refresh** |
| HD | | **blank** | V | late Oct 2026 | est |
| | | | XOM | | **blank** |

**Six blanks and three stale rows must be searched on the first 2-1-13 session.** Late Oct is dense: AAPL, AMZN, GOOGL, MSFT, META, TSLA, V cluster there — expect most of mega-cap to be blocked by Gate 2 for the next two weeks.

**Refresh rule:**
1. Name within **10 trading days** of its cached date → search, upgrade to confirmed, rewrite the row.
2. Name just reported → search once for the next date.
3. Blank or older than ~60 days → search.
4. Otherwise → **read the table, do not search.**

**A cached date never clears a name on its own inside the window.** If the cached date is within the expiry window, the name is blocked pending an IR-confirmed check.

---

## DELTA ANCHORS

| Stock | Tier | Δ | Fallback |
|---|---|---|---|
| NVDA, TSM | Volatile | **0.20** | TSM → 0.18 if tail discipline preferred |
| AMD, ANET, AVGO, CAT, CRM, CRWD, DELL, META, PANW, PLTR, TSLA | Volatile | 0.15 | **NONE** |
| All calm names | Calm | 0.15 | **NONE — suspended in 2-1-13** |

- **Calm-tier fallbacks are suspended.** The old 0.18/0.20 fallbacks for AAPL, AMZN, GOOGL, JPM, V existed to work around the 12%W floor. The 10%W floor now does that job. **Stacking both is double loosening and untested** — and the delta trial showed 0.18 and 0.20 worse than 0.15 at 10%W (0.20: −7.7% in 2022).
- Nearest listed strike counts (0.14–0.16 = 0.15). Hard cap 0.20Δ.
- **No chain sweeping upward until floor clears.** That's delta creep.
- **0.15 is settled downward** — dominant over 0.12 and 0.08 (10-year replay, full-universe MC, correlated MC). Calm-tier trial agrees: 0.12 at 10%W traded 0.35/yr.
- **0.15 is settled upward at the current width (2-1-9).** Do not re-propose blanket 0.18 at 5% width.

---

## STRATEGY

| Parameter | Setting |
|---|---|
| Width | ~5% of spot, listed strikes — **hard min $5, no maximum.** Not a fixed $10. Flat $30 max, per-name tiers and vol-scaled widths all rejected |
| Entry | Daily scan; enter any day gates pass AND capacity exists AND no cap is full |
| DTE | **18–21 hard range. Prefer 18.** Both 22–25 and 7–14 tested and rejected |
| Short Δ | Anchor table above |
| Credit floor | **Volatile 12%W · Calm 10%W** — worst-case (short at bid, long at ask). **JH verifies live at ticket** |
| Exit | **HOLD TO EXPIRY. No defensive close. No take-profit. No mid-trade orders of any kind** |
| Sizing | ~7% risk/name · 50% max total open exposure (max-loss basis, vs session-start IBKR cash) — **conditional on live tail hedge** |
| Calm-tier trial sizing | **~3.5% risk per calm spread for the first 10 calm fills** (or 6 weeks, whichever later), then 7% if the live credit check passes (PENDING) |
| Caps | **Hard.** 7 cluster caps + **max 4 tech spreads open** |
| Concurrency | ~6–7 typical; cash to T-bills / IBKR pays interest on idle USD |
| Tail hedge | SPY put spread long ~25% OTM / short ~40% OTM, 3-month, rolled quarterly, ~0.4–0.5%/yr |
| Hedge lapse | Cap reverts to **25%** |
| Condor overlay | GO: VIX ≥20 AND SPX stretch −2%..+3% vs 20-MA AND no binary macro in window. Half-size, call floor 7%W, no call step-up. State GO/NO-GO each session. **VIX unreadable = NO-GO.** |

**Daily cadence ≠ daily trades. Most days: zero entries.** The calm tier adds roughly 5–10 trades/yr in the backtest. It is an add-on, not a second book.

**DTE availability.** The 18–21 window frequently has no listed Friday in it. **State the DTE and flag it; do not silently price an out-of-range expiry.** Which to take is JH's call at Step 7.

**Width pre-filter:** spot under ~$100 → 5% width under $5 → name excluded unless JH opts in. No current universe name sits near this line (NFLX dropped).

**Structures defined in this system:** put credit spread (core) · iron condor via the conditional call overlay · SPY long put debit spread (tail hedge). **No debit/directional structure, naked short option or stock position is authorised.**

---

## TICKET DISCIPLINE (new in 2-1-13 — from the Oct 2026 loss review)

The screen is not where the Oct 2026 damage came from. These are ticket-level rules.

1. **Width = 5% of spot at listed strikes.** A $10 spread on a $340 name is ~3% wide — it hits full loss on a smaller move and makes the floor easy to "clear". If 5% isn't listed, take the nearest listed width **at or above** 5%.
2. **Never exceed 7% risk on one name.** No adding to a name already open (Oct: PANW doubled to 20 lots).
3. **One expiry per name.** No stacking a second expiry on a name already open (Oct: CRWD Oct 16 + Oct 30).
4. **No naked short puts.** Every short put has a long put below it (Oct: SPCX).
5. **Assigned stock is not a position.** Decide within 2 sessions: sell it, or document a plan. Covered calls on assigned stock are not part of this system (Oct: NFLX, COIN).
6. **Close shorts ITM or within the pin band before expiry Friday close.** Step 6b flags them; acting is mandatory, not optional (Oct: CRWD 230 put expired ITM).

---

## RULE 1 — LIVE PRICES ONLY

Every price — spot, IV, HV, VIX, SMA inputs — pulled live this session. No recall, no cached figures, no prior-session values, no price inferred from another price.

**No live price = no row.** Name dropped, not priced from an older figure.

**Rule 1 governs prices, not calendars.** The earnings cache is not an exception to it.

**Rule 1 does not govern tiers.** Tier membership is a monthly list, read from this file. Never re-tier from a live snapshot.

Delayed data doesn't abort scan — must be **declared** on regime line (`EST-DELAYED`), borderline rows provisional.

**Every Gate 1 spot comes from the snapshot** — the bar supplies SMA history only, never a current price. **Step 6b spots come from `get_price_snapshot`, never from the bar.**

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

**Neither price tool accepts more than one contract.** Verified 10 Sep 2026. Do not spend calls rediscovering this.

**VIX via `get_price_history` only** (snapshot returns `{}`). 15-min delayed — declare `EST-DELAYED`. Empty response = failed read = condor NO-GO.

**`get_option_data` and `get_option_parameters` are retired. Neither is called by the screen, ever.** Pricing is Step 7 and it belongs to JH.

Cross-check must be **web**, never IBKR checking IBKR.

**Tool loading.** Load the tools the source table names, in one pass, before Gate 1a.

### `top_status` — mandatory field, read before price

`REALTIME` → proceed, label `EST` · `DELAYED` → proceed, label `EST-DELAYED` · `FROZEN`/`FROZEN_DELAYED` → row provisional · `REJECT` → drop name.

Read on all 25 names at Gate 1a. Declare worst status seen on regime line.

---

## STEP 0 — PRE-FLIGHT

- **0a ID integrity** — spot-check survivor spot prices vs an independent web source. **Survivors only.**
- **0b Session state** — 10 PM SGT = ~30 min after US open, bar in progress. **20-SMA on the prior 20 completed bars; compare against the snapshot spot.** Trend margins under ~2% provisional, flagged.
- **0c Freshness** — `top_status` first, then snapshot ts vs `user_time_v0`, then `delayed` field.

---

## GATES (cost-ordered)

### Gate 1a — IV PRE-FILTER (cost filter, not a gate)

One `get_price_snapshot` per name, all 25.

**Drop the name before its history is pulled if live IV is more than 15 points below IV-needed at 0.15Δ (0.20Δ for NVDA/TSM) for the name's TIER floor and the target DTE.**

| Tier | IV-needed @ 18 DTE | Drop below (−15 pts) |
|---|---|---|
| Volatile 0.15Δ (12%W) | 60.3% | **45.3%** |
| Volatile 0.20Δ — NVDA, TSM (12%W) | 33.1% | **18.1%** |
| Calm 0.15Δ (10%W) | 42.4% | **27.4%** |

**Expect most calm names to drop here on normal days** (JNJ, MCD, COST, V, JPM, AAPL, HD, XOM run 17–26%). That is correct — they reach 10%W only when their own vol is elevated. This filter only saves history calls.

**On a failed or empty IV field:** do not drop. Pull the history and let Gate 1b decide. An absent read is not a low read.

### Gate 1b — TREND

Snapshot spot > 20-day SMA. **Absolute veto.** `get_price_history`, 21 bars, Gate 1a survivors only. SMA from the 20 completed bars.

**Load-bearing for the calm tier:** without the trend gate the calm-sleeve backtest drawdown went from ~29% to ~50%.

Loosening tested and rejected (0.5%/1.0% buffer, SMA10). Margins under ~2% flagged `prov`.

### Gate 2 — EARNINGS

None on/before expiry. Same-day reporter = auto-SKIP. Re-entry T+2 preferred; T+1 only at **floor + 3%W** (15%W volatile, 13%W calm) + clean transcript.

- **Read the earnings cache first.** Search only per the refresh rule.
- **IR press release only** when searching. Sources disagree with no IR confirmation → name blocked.
- Searches are **narrow and per-name**.
- **Macro density flag:** two or more macro events within 3 days of expiry → halve tranche size, declare on regime line.

### Gate 3 — NEWS

No material adverse catalyst (guidance cut, probe, downgrade cluster, sector contagion, litigation, M&A break). Veto regardless of premium.

- **One search, covering all survivors together.**
- Note the date on anything returned. Old analyst actions are not current catalysts.
- **Final automated veto in screen.**

Gate 1a/1b/2/3 failure = dropped silently. Every survivor shown, unless blocked by a full cap (see 5a).

**There is no Gate 4 or Gate 5 in the screen.** Credit and liquidity (OI ≥500, bid/ask ≤10% of mid) are checked by JH at ticket, Step 7. **Calm names pay small credits — a $0.05–0.10 bid/ask gap is a large share. If the book is wide, skip; do not lean on the mid.**

---

## SIZING & CAPS

Denominator: **IBKR cash at session start**, before any new tranche.

| | |
|---|---|
| Max total exposure | 50% (hedge live) / **25% (hedge absent)** |
| Per-name risk | ~7% (calm tier ~3.5% during trial) |
| Implied concurrency | ~7 names |
| **Tech spreads open** | **max 4** (hard) |

Max loss per spread = (width − credit) × 100 × contracts.

**Hedge gate binary.** Live unexpired SPY put spread in positions → `HEDGE: LIVE · CAP 50%`. Absent, expired, or rolled late → `HEDGE: NONE · CAP 25%`. No partial credit, no grace period.

If IBKR ceases to be minority of total capital → cap reverts to 15%.

### Cluster caps — HARD (eleven clusters)

| Cluster | Names | Max |
|---|---|---|
| Semis & hardware | NVDA, AMD, AVGO, TSM, DELL | 2 |
| Security | CRWD, PANW | 1 |
| Mega-cap platform | AAPL, MSFT, GOOGL, AMZN, META | 3 |
| Software | CRM | 1 |
| High-beta | PLTR, TSLA | 1 |
| Networking | ANET | 1 |
| Healthcare | JNJ, LLY | **2** (restored — two members again) |
| Financial | V, JPM | 2 |
| Energy | XOM | 1 |
| Industrial | CAT | 1 (restored) |
| Consumer | COST, HD, MCD | 2 |

**Tech set (for the max-4 cap):** NVDA, TSM, AMD, AVGO, DELL, CRWD, PANW, ANET, PLTR, TSLA, META, CRM, AAPL, MSFT, GOOGL, AMZN. **Calm tech counts.** Calm tech still falls with tech in a sector rout.

**ANET is now clustered** (own cluster). The long-pending ANET/NFLX cluster item is closed.

**Cluster caps count names because the risk is correlation, not size.**

### Step 5a — caps computed, not asserted

Every session, before the table, print:
1. Total open exposure % vs operative cap
2. Per-name exposure for any name above 5%, vs 7%
3. **Cluster counts, all eleven**, full clusters marked `FULL`
4. **Tech count n/4**, `FULL` if 4

**A full cap BLOCKS (2-1-13).** Names in a full cluster, or tech names when tech is 4/4, do not appear as table rows. They go on one line: `Blocked by cap: <names> (<cap>)`. JH does not enter them.

If Step 5a is not computed and printed, the session is incomplete and no entry should be made off it.

**Compute live every session. No carried figure appears here.**

---

## SESSION CALL BUDGET

| Block | Calls | Note |
|---|---|---|
| Tool load | ~1 | One pass |
| VIX | 1 | `get_price_history`, `step_count=2` |
| Positions | 1 | Serves 5a, 6, 6b, EXCEPTIONS |
| Balances | 1–2 | Retry once, then defer |
| **Gate 1a snapshots** | **25** | All names. Light payload. Irreducible |
| **Gate 1b histories** | **~5–9** | Gate 1a survivors only |
| Step 6b expiry spots | = Friday expiries, minus names already snapped | |
| Earnings searches | 0–2 typical | **First 2-1-13 session: ~9** (6 blanks + 3 stale) |
| News search | 1 | One search, all survivors |
| Trades (EXCEPTIONS) | 1 | |
| **Total, typical session** | **≈38–44** | Was ≈32–38 under 2-1-12 |

**If a session is tracking past ~50 calls, something is being run that this file does not ask for.** Stop and check.

---

## SESSION OUTPUT — TERSE SPEC

Order is fixed: **regime line → Step 5a → ONE table → Step 6 → Step 6b → EXCEPTIONS.** Nothing else.

**1. Regime line** — one line, pipe-separated:
`REGIME <date>` · VIX · SPX stretch vs 20-MA · macro in window · macro-density flag if fired · feed status · `HEDGE: LIVE · CAP 50%` or `HEDGE: NONE · CAP 25%` · condor GO/NO-GO · target expiry + DTE

**2. Step 5a caps** — bullets. Eleven cluster counts + tech n/4 + `Blocked by cap:` line.

**3. ONE table.** Header above it, every session, verbatim:
**"Gates 1–3 passed. Price each yourself; floor is 12%W (V) / 10%W (C) — yours to enforce."**

| Ticker | Tier | Δ | Spot | Width | IV | IV needed | IV/HV | Note |
|---|---|---|---|---|---|---|---|---|

- Tier = `V` or `C`. IV needed = for that name's tier floor.
- **No credit column. No strikes column. No %W column.** If those appear, chains were pulled and the session went out of spec.
- **Group rows by cluster**, count as `n/max` in the group header. Sort IV descending within group — **presentation order, not a ranking.**
- Note column: `inv` · `prov` · `no fallback` · blow-off stretch · FROZEN/DELAYED · `new` for CAT, COST, HD, LLY, MCD, XOM until each has traded once · `trial` on calm rows during trial sizing · `DTE n` if outside 18–21.
- **Dropped:** one line, grouped by gate. **Gate 1a drops listed as `IV` — cost drops, not vetoes.**
- Nothing passes → one line. Cash is a valid outcome.

**4. Step 6** — earnings re-check table.
**5. Step 6b** — expiry-week table.

**6. EXCEPTIONS line.** One line, from the trades and positions pulls already made.

Triggers:
- Fill below its **tier floor** — name it with actual %W
- DTE at entry outside 18–21
- Width at entry under 5% of spot (TICKET DISCIPLINE 1)
- Any name above 7% risk, or two expiries open on one name
- Any naked short option
- Any open position marked above 2.5× credit received
- First fill on CAT, COST, HD, LLY, MCD, XOM — state actual bid/ask and OI
- Stock position from assignment older than 2 sessions

Nothing fired → `EXCEPTIONS: none`.

**Prose is permitted only where a number would mislead without it.** One or two sentences, then stop.

### IV needed (5%-of-spot width) — reference only, never pass/fail

| Δ | 12%W @ 18 DTE | 12%W @ 21 DTE | 10%W @ 18 DTE | 10%W @ 21 DTE |
|---|---|---|---|---|
| 0.15 | **60.3%** | 55.9% | **42.4%** | 39.3% |
| 0.16 | 52.5% | 48.7% | 37.4% | 34.6% |
| 0.17 | 46.2% | 42.8% | 33.3% | 30.8% |
| 0.18 | 40.9% | 37.9% | 30.0% | 27.7% |
| 0.20 | **33.1%** | 30.6% | 24.9% | 23.0% |

10%W column computed 17 Oct 2026 with the same method (flat 0.90 haircut, no skew); it reproduces the 12%W column to within 0.1 pt.

Caveats, mandatory whenever shown: flat 0.90 haircut understates real bid/ask drag · snapshot IV blended across expiries, can diverge 9+ pts from traded expiry · not a gate.

---

## WORKFLOW (nightly ~10 PM SGT)

| Step | Who | What | Budget |
|---|---|---|---|
| 0 | Claude | Load tools · pre-flight | ~1 |
| 1 | Claude | Regime + condor GO/NO-GO · **assert hedge status → set operative cap** | ~3 |
| 2a | Claude | **Gate 1a — snapshots on all 25** (tier-specific IV cut) | **25** |
| 2b | Claude | **Gate 1b — trend histories on survivors** | **~5–9** |
| 3 | Claude | Gate 2 vs cache · Gate 3 one news search | 1–3 |
| 4 | Claude | Width pre-filter → ID sanity check on survivors | 0 |
| 5a | Claude | **Compute caps — HARD. Print blocked names** | 0 |
| 5 | Claude | Candidate table with Tier column — **no prices, no strikes** | 0 |
| 6 | Claude | Open-position earnings re-check | 0–2 |
| 6b | Claude | Expiry-week check | = Friday expiries not already snapped |
| 7 | **JH** | Price live: worst-case credit at anchor Δ, **tier floor (12%W / 10%W)**, 5% width, OI ≥500, bid/ask ≤10% of mid | — |
| 8 | Claude | **EXCEPTIONS line** | ~1 |

---

## STEP 6 — OPEN-POSITION EARNINGS RE-CHECK

1. Group legs by underlying + expiry from the positions pull.
2. Re-check earnings per pair — **cache first, search only if stale**.
3. Flag any report on or before expiry.
4. Short table; clear positions listed, hits flagged.
5. **Claude flags, JH decides.**

**Covers non-universe and retired names** (incl. NFLX, COIN, SPCX). **Cutting a name from the universe never cuts it from Steps 6 and 6b.** Report a clearance as narrow when the date falls within 7 days after expiry.

---

## STEP 6B — EXPIRY-WEEK CHECK (standing)

Every session, every open position expiring **this Friday**. Spots from `get_price_snapshot`.

| Ticker | Spread | Short | Spot | OTM/ITM by ($ and %) | Action |
|---|---|---|---|---|---|

- Sorted by distance ascending — tightest first.
- Action from EXPIRY & ASSIGNMENT. Pin-risk band ~0.5% either side.
- Non-universe positions italicised.
- One summary line: `n of m clean`.
- **Close cost** in $ for any row marked close; net roll-off restated.
- **Any row marked close must be closed before Friday's close (TICKET DISCIPLINE 6).** Thursday session: flag again in bold if still open.
- **Reuse Gate 1a spots** for universe names.
- Empty week → one line.

---

## EXPIRY & ASSIGNMENT

| State at expiry Friday | Action |
|---|---|
| Both legs OTM | Let expire |
| Short ITM, long OTM | **Close spread** |
| Both ITM | Both exercise, net = width; closing cleaner |
| Short ITM by pennies | **Pin risk — close** |
| **Short OTM by pennies** | **Pin risk — close** |

**Pin-risk band: short strike within ~0.5% of spot, either side.**

Early assignment on short puts possible when deep ITM. Ex-dividend early assignment is a short-call risk, not a short-put risk.

**Close-cost pricing is the one permitted exception to the no-snapshot-on-options rule** — 2 snapshots per spread, only for rows marked close.

---

## STANDING CONSTRAINTS

- Cash is a valid outcome. Gates are hard vetoes, not quotas.
- **Credit 12%W vs max loss 88%W → 7.3 full wins erased by one full loss. At 10%W: 9 wins.** The floor is a minimum-viability filter, not a safety margin.
- Clearing the floor proves nothing about EV.
- **Easy floor clearance is a warning, not an opportunity.**
- **The credit floor is a volatility filter (2-1-13).** A single floor across names of different vol silently picks a sector. Tier by vol; cap by correlation.
- **Caps, not calm names, are what cut sector-selloff losses (2-1-13).** In a tech-only selloff calm names stay calm and rarely clear 10%W. The calm tier pays over time; the caps protect in the moment.
- **Tech-or-not is irrelevant to the floor and essential to the caps (2-1-13).**
- **More open positions means more loss in a broad bear (2-1-13).** 2022 DD 20% vs 15%. Accepted, not solved.
- **The account lost more than the rules would have (2-1-13).** Oct 2026: model −5%, account −12.6%. Ticket discipline is a risk control, not a style preference.
- **Universe composition is a real lever; selection within it is not.**
- **Width must scale with spot, and 5% is the setting.** Vol-scaled width added to the rejected list (2-1-13).
- **The book runs at low fill and that is structural.**
- **At a fixed %W floor, every structural parameter is also an entry filter (2-1-10).** State expected trade count before running any structural test. *(2-1-13: calm tier ~5–10 trades/yr in backtest.)*
- **No position-level circuit breaker exists.** Do not improvise a stop.
- Universe is survivorship-selected; every per-trade mean is an upper bound.
- Stacking across adjacent expiries is the live exposure risk, not per-name size.
- **A convention is not a limit.** Only computed percentages against a stated denominator govern.
- **A backtest is not an MC.** 2-1-13's evidence is mostly backtest with modelled prices; the live credit check (PENDING) is what promotes it.
- **A model cannot see a spread.** Where the model and the chain disagree, the chain wins.
- **Model bias runs toward optimism.**
- **Correlation, not skew, is where up-delta proposals die (2-1-9).**
- **An MC whose baseline does not reproduce production is not evidence (2-1-9).** *(The 2-1-13 MC generator does not reproduce production — tech baseline ~1–3% CAGR vs ~16.6%. It was used only for relative comparison.)*
- **A screen that cannot finish is a screen that did not run (2-1-11).**
- **Where session behaviour and this file disagree, this file wins (2-1-11).**
- **Cost order must match actual cost, not assumed cost (2-1-12).**
- **Dropping a name from the screen does not drop it from the book (2-1-12).**

---

## PENDING

### Open against 2-1-13 itself

**1. Live credit check — calm tier (blocks full sizing).** For 6 weeks, whenever a calm name passes Gates 1–3, record at Step 7: actual worst-case credit %W at 0.15Δ / 5% width, bid/ask, OI. **Promote calm sizing to 7% only if** real credits reach 10%W on a meaningful share of passing names and books are tight. If real credits run well under the model, the calm tier stays at trial size or is dropped. Either way the caps stay.

**2. Calm-tier trade count.** Backtest says ~5–10/yr. Count live. If near zero over 3 months, the calm tier is idle — harmless, but revisit the floor (9.5%W was the best full-period result).

**3. 2022-type drawdown.** Two-tier is worse in a broad bear (20% vs 15% DD). Candidate fix to test: when SPX < its 50-day MA, calm-tier entries halt. Not adopted, not tested.

**4. Model limits on record.** Credits modelled (Black-Scholes, realised vol, no edge), no earnings gate in tests, survivorship-biased universe, tier_test single-path backtest. The VIX-scaled IV proxy overstated credits (~6.6% loss rate vs ~15% expected) and was abandoned for no-edge runs.

### Carried from 2-1-12

- **Rolling losers MC** — still the live structural test. Rebuild the MC universe to these 25 names, tiers and hard caps first.
- **Simulate the tail hedge.**
- **Exit rule MC.**
- **Verify CRM and DELL live** (first-ticket bid/ask and OI).
- **PANW universe decision** — negative mean %W over 10 years. More pressing now that security is a hard 1-cap.
- **September seasonality gate** — untested.
- **Earnings/news gate simulation** — still blocked on free data.
- **NVDA / TSM 0.20Δ dedicated MC before any size-up.**
- **QQQ 690/680 ×5 (21 Aug)** — reconcile against broker statement.
- **DTE availability friction** — keep counting.
- **2-1-12 universe-cut trade count** — partly superseded: CAT and LLY are back in at 10%W/12%W tiers.
- Contract ID re-verify due **17 Nov 2026** — 27 IDs.

### Rejected — do not re-propose

Take-profit early close · width change $10 vs $15 · $30 max width · per-name width tiers 7%/5% (2-1-10) · **vol-scaled width (0.4σ) (2-1-13)** · blanket 0.18Δ at 5% width (2-1-9) · 0.20Δ at 5% width · **0.18/0.20Δ in calm tier (2-1-13)** · **8%W calm floor (2-1-13)** · shorter DTE (7/10/14) · longer DTE (22–25) · 200-day MA regime gate · always-on condor · candidate-selection ranking · Gate 1 loosening (0.5%/1.0% buffer, SMA10) · delta 0.12 (declined) · delta 0.08 (rejected three times) · 9%W override for LLY/MSFT/V · batched multi-contract price calls (no such parameter exists — 2-1-12).

*Note: the 9%W per-name override for LLY/MSFT/V (rejected) is a different object from the 10%W calm tier. The override lowered the floor for named stocks inside a single-floor system with fallbacks still live; the tier lowers it by measured vol, suspends fallbacks, and is paired with hard caps.*

---

## FILE CONVENTION

This file: `put-spread-workflow-2-1-13.md` (project path `claude/`). Suffix increments on replacement. **Always read the highest suffix.** Rationale and evidence archive: `put-spread-workflow-2-1-1.md`. Test scripts: `lowvol_pcs_test.py`, `run_trials.py`, `tier_test.py` (JH's machine).

*(2-1-13 supersedes 2-1-12. Two-tier screen: volatile 12%W / calm 10%W by median 1-yr vol (35% line, monthly review, two-month confirm). Calm fallbacks suspended. Cluster caps hard + max 4 tech. Universe 20 → 25 (+CAT, COST, HD, LLY, MCD, XOM; −NFLX; META/CRM to volatile). New TICKET DISCIPLINE section from the Oct 2026 loss review. Calm tier at ~3.5% trial sizing until the live credit check passes. Evidence: backtest with modelled no-edge prices — full CAGR 9.7→11.3%, max DD 25.7→21.6%, recent worst-20d −5.6→−3.0%; 2022 DD worse 15.4→20.3%.)*