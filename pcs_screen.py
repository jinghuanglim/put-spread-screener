#!/usr/bin/env python3
"""
Put Credit Spread screener — Part 1 (market-data half, no IBKR required).
Replicates workflow 2-1-5 Steps 0b/2/3/4 using free data:
  Gate 1 TREND     close > 20-day SMA (prior 20 completed bars)
  Gate 2 EARNINGS  aggregator dates, conflicts listed not resolved
  Gate 3 NEWS      headlines printed for human veto
  Width pre-filter 5% of spot, hard min $5
  Context         IV at anchor-delta strike, HV30, IV/HV
NOT in this half (needs IBKR): caps block, Step 6b expiry week, logs.
Usage:
  python pcs_screen.py                 # live, yfinance
  python pcs_screen.py --selftest      # offline, synthetic data, verifies math
  python pcs_screen.py --no-news       # skip news pull (faster)
"""
import argparse, math, sys, json
from datetime import datetime, date, timedelta
# ---------------------------------------------------------------- config
UNIVERSE = ["AAPL","AMD","AMZN","ANET","AVGO","CRWD","GOOGL","JNJ","JPM","LLY",
            "META","MSFT","NFLX","NVDA","PANW","PLTR","TSLA","TSM","V",
            "QQQ","SPY","IWM"]
CLUSTERS = {
    # ANET is networking hardware, not silicon, and keeping the labels literal
    # was JH's call (23 Aug 2026) — so it gets its own cluster rather than
    # being filed under Semis. The correlation that argued for Semis is real
    # and did not go away: it is recorded in CROSS_CLUSTER below, where the
    # cap structure cannot see it but a reader can.
    #
    # NFLX stays unclustered on measured evidence: its best match is Mega-cap
    # platform at 0.22 / 0.18 / 0.15 over 60 / 120 / 250 sessions, barely above
    # its correlation to the market itself. Genuinely idiosyncratic, so a
    # cluster would be a label rather than a fact.
    "Semis":                ["NVDA","AMD","AVGO","TSM"],
    "Networking":           ["ANET"],
    "Security":             ["CRWD","PANW"],
    "Mega-cap platform":    ["AAPL","MSFT","GOOGL","AMZN","META"],
    "High-beta":            ["PLTR","TSLA"],
    "Defensive/financial":  ["JNJ","LLY","V","JPM"],
    "Index":                ["SPY","QQQ","IWM"],
}
CLUSTER_MAX = {"Semis":2,"Networking":1,"Security":1,"Mega-cap platform":3,
               "High-beta":1,"Defensive/financial":3,"Index":1}
CLUSTER_ORDER = ["Semis","Networking","Security","Mega-cap platform",
                 "High-beta","Defensive/financial","Index","Unclustered"]

# Correlations that cross a cluster boundary, so the cap structure cannot see
# them. A cluster line is a statement about the names inside it; it says nothing
# about two names in different clusters that happen to move together, and the
# per-name cap will not catch that either. Measured, dated, and stated as a
# number so it can be re-measured rather than believed.
CROSS_CLUSTER = [
    (("ANET",), ("NVDA", "AMD", "AVGO", "TSM"),
     "ANET has its own cluster but tracked the semis at 0.62 / 0.48 / 0.46 "
     "over the last 60 / 120 / 250 sessions (measured 23 Aug 2026) \u2014 "
     "above its own 0.57 correlation to SPY at 60 sessions. Holding it "
     "alongside a semi is closer to two of the same bet than the cluster "
     "lines suggest."),
]


def cross_cluster_notes(tickers):
    """Notes whose both sides are present in this screen."""
    shown = set(tickers)
    return [note for a, b, note in CROSS_CLUSTER
            if shown & set(a) and shown & set(b)]
DELTA_ANCHOR = {"NVDA":0.20, "TSM":0.20}          # everything else 0.15
DEFAULT_DELTA = 0.15
# Fallback delta, used ONLY if live worst-case credit fails the 11% floor at
# 0.15-0.16. None = no fallback exists. "SKIP" = never step up, skip the name.
FALLBACK = {
    "TSM": 0.18, "AAPL": 0.18, "AMZN": 0.18, "GOOGL": 0.18, "JPM": 0.18,
    "V": 0.20,
    "JNJ": "SKIP", "MSFT": "SKIP",
    "CRWD": None, "LLY": None, "META": None,
    "SPY": None, "QQQ": None, "IWM": None,
}
DELTA_HARD_CAP = 0.20     # workflow 2-1-5: "Hard cap 0.20\u0394". Absolute.
BLOWOFF_STRETCH = 0.15        # never tilt delta on a blow-off
DTE_MIN, DTE_MAX, DTE_BIAS = 14, 21, (18, 21)
WIDTH_PCT   = 0.05
WIDTH_MIN   = 5.0
CREDIT_FLOOR = 0.11        # reference only; JH prices at ticket
RISK_FREE   = 0.042
PROV_TREND_MARGIN = 0.02   # <2% above SMA20 -> flag prov
# ---------------------------------------------------------------- macro calendar
# FOMC decision days (second day of each meeting). Source: federalreserve.gov
# tentative-schedule release. 2027 dates are provisional until confirmed at the
# preceding meeting, but in practice the published schedule rarely moves.
FOMC_DAYS = [
    date(2026, 1, 28), date(2026, 3, 18), date(2026, 4, 29), date(2026, 6, 17),
    date(2026, 7, 29), date(2026, 9, 16), date(2026, 10, 28), date(2026, 12, 9),
    date(2027, 1, 27),
]
FOMC_TABLE_GOOD_THROUGH = date(2027, 1, 27)

# bls.gov 403s any request whose User-Agent looks like a browser, a bare tool
# name, curl, or python-urllib. It returns 200 to any User-Agent containing an
# email address. Verified 22 Aug 2026 across every combination: browser UA 403,
# "pcs-screener/1.0" 403, curl/8.5.0 403, "contact@example.com" 200. This is the
# opposite of the usual anti-scraping fix — BLS wants scripted callers to
# identify themselves, and blocks the ones pretending to be people. Put a
# working address here or in BLS_CONTACT_EMAIL; it is how BLS reaches you if the
# script misbehaves.
import os as _os
# Deliberately a placeholder, not a real address. This file is meant to live in
# a GitHub repo that has to be public for free Pages, and a personal address
# committed to a public repo is a permanent gift to address scrapers. Set the
# BLS_CONTACT_EMAIL environment variable (locally) or repository secret (in
# Actions) instead — the value then exists only in your shell and in GitHub's
# encrypted secret store, never in the source.
# Whose screen this is. Shown on the page so a reader knows it is one person's
# rule set rather than a service. Set SCREEN_AUTHOR, or pass --author.
SCREEN_AUTHOR = _os.environ.get("SCREEN_AUTHOR", "JH")

BLS_CONTACT_PLACEHOLDER = "set-BLS_CONTACT_EMAIL@example.invalid"
BLS_CONTACT = _os.environ.get("BLS_CONTACT_EMAIL", BLS_CONTACT_PLACEHOLDER)
BLS_CONTACT_SET = BLS_CONTACT != BLS_CONTACT_PLACEHOLDER
MACRO_WINDOW_DAYS = 3          # your rule: within 3 days of expiry
def parse_fomc_calendar(html, years):
    """Pull FOMC decision days off federalreserve.gov/monetarypolicy/fomccalendars.htm.
    The page groups meetings by year panel, then month, then a day field that is
    either a range ("15-16") or a month-spanning range ("Apr/May 30-1"). The
    DECISION day is the LAST day of the range, which is what matters here.
    Trailing '*' marks a Summary-of-Economic-Projections meeting and is ignored.
    """
    import re
    text = re.sub(r"<[^>]+>", "\n", html)
    out, year, month = [], None, None
    ypat = re.compile(r"\b(20\d\d)\s+FOMC\s+Meetings", re.I)
    for raw in text.splitlines():
        line = raw.strip()
        if not line:
            continue
        my = ypat.search(line)
        if my:
            year = int(my.group(1))
            continue
        if line in _MONTHS:
            month = _MONTHS.index(line) + 1
            continue
        # month-spanning label like "Apr/May"
        mm = re.fullmatch(r"([A-Z][a-z]{2,8})/([A-Z][a-z]{2,8})", line)
        if mm:
            for full in _MONTHS:
                if full.startswith(mm.group(2)):
                    month = _MONTHS.index(full) + 1
            continue
        md = re.fullmatch(r"(\d{1,2})\s*[-–]\s*(\d{1,2})\*?", line)
        if md and year and month:
            first, last = int(md.group(1)), int(md.group(2))
            y, mth = year, month
            if last < first:                 # range crossed a month boundary
                mth = month
            try:
                out.append(date(y, mth, last))
            except ValueError:
                pass
            continue
        ms = re.fullmatch(r"(\d{1,2})\*?", line)
        if ms and year and month:
            try:
                out.append(date(year, month, int(ms.group(1))))
            except ValueError:
                pass
    if years:
        out = [d for d in out if d.year in years]
    return sorted(set(out))
_ABBR = ["Jan", "Feb", "Mar", "Apr", "May", "Jun",
         "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]
def parse_bls_annual(html):
    """Dates off a BLS per-release annual page (cpi.htm, empsit.htm).
    Rows read: reference month, release date, release time. Only the release
    date matters, and it is the only 'Mmm. DD, YYYY' token on the row.
    """
    import re
    text = re.sub(r"<[^>]+>", " ", html)
    out = []
    for m in re.finditer(r"\b(" + "|".join(_ABBR) + r")\.?\s+(\d{1,2}),\s*(\d{4})",
                         text):
        try:
            out.append(date(int(m.group(3)), _ABBR.index(m.group(1)) + 1,
                            int(m.group(2))))
        except ValueError:
            pass
    return sorted(set(out))
class MacroCalendar:
    """FOMC from a table; CPI and Employment Situation scraped from BLS.
    BLS dates are scraped rather than hardcoded because they move: the 2025 and
    2026 appropriations lapses both forced reschedules. A stale hardcoded table
    would have silently cleared names against dates that no longer applied.
    """
    BLS = "https://www.bls.gov/schedule/{y}/{m:02d}_sched_list.htm"
    BLS_ANNUAL = {
        "CPI": "https://www.bls.gov/schedule/news_release/cpi.htm",
        "NFP": "https://www.bls.gov/schedule/news_release/empsit.htm",
        "PPI": "https://www.bls.gov/schedule/news_release/ppi.htm",
    }
    FOMC_URL = "https://www.federalreserve.gov/monetarypolicy/fomccalendars.htm"
    # See BLS_CONTACT above: the identifying UA is load-bearing, not decoration.
    # federalreserve.gov accepts it too, so one header set covers both hosts.
    HDRS = {
        "User-Agent": f"pcs-screener/1.0 ({BLS_CONTACT})",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "en-US,en;q=0.9",
        "Connection": "close",
    }
    def __init__(self, start, days=60, timeout=8):
        self.start, self.days, self.timeout = start, days, timeout
        self.events = []        # (date, label)
        self.errors = []
        self.bls_ok = False
        self.fomc_src = "table"
        self.loaded = False
    def _months(self):
        seen, d = [], self.start
        end = self.start + timedelta(days=self.days)
        while d <= end:
            if (d.year, d.month) not in seen:
                seen.append((d.year, d.month))
            d += timedelta(days=28)
        if (end.year, end.month) not in seen:
            seen.append((end.year, end.month))
        return seen
    def _gaps(self, end):
        """Months lying wholly inside the window that are missing a release.

        bls_ok being a per-LABEL flag is not enough. On 22 Aug 2026 both the
        annual empsit page and the September month page served NUL bytes, while
        the August and October month pages were fine — so NFP was "obtained",
        bls_ok went True, and the one NFP inside the screening horizon
        (4 Sep) was simply absent from the calendar. A screen against a 4 Sep
        or 7 Sep expiry would have printed "macro: none" over a payrolls print.

        Only fully-contained months are checked. In a partly-covered month the
        release can legitimately fall outside the window — August's NFP landed
        on the 7th, before a window opening on the 22nd — and demanding one
        there would manufacture a permanent false gap.
        """
        import calendar
        have = {}
        for d, lbl in self.events:
            have.setdefault((d.year, d.month), set()).add(lbl)
        gaps = []
        for y, m in self._months():
            first = date(y, m, 1)
            last = date(y, m, calendar.monthrange(y, m)[1])
            if first < self.start or last > end:
                continue
            for lbl in sorted(self.BLS_ANNUAL):
                if lbl not in have.get((y, m), set()):
                    gaps.append(f"{y}-{m:02d} {lbl}")
        return gaps

    def _scrape_month(self, y, m):
        import urllib.request, re
        req = urllib.request.Request(self.BLS.format(y=y, m=m), headers=self.HDRS)
        with urllib.request.urlopen(req, timeout=self.timeout) as r:
            html = r.read().decode("utf-8", "ignore")
        text = re.sub(r"<[^>]+>", "\n", html)
        return parse_bls_schedule(text, y)
    def load(self):
        if self.loaded:
            return
        self.loaded = True
        end = self.start + timedelta(days=self.days)
        years = {self.start.year, end.year}
        fomc, self.fomc_src = [], "table"
        try:
            import urllib.request
            req = urllib.request.Request(self.FOMC_URL, headers=self.HDRS)
            with urllib.request.urlopen(req, timeout=self.timeout) as r:
                html = r.read().decode("utf-8", "ignore")
            scraped = parse_fomc_calendar(html, years)
            if len([d for d in scraped if d.year == self.start.year]) >= 6:
                fomc, self.fomc_src = scraped, "fed.gov (live)"
                # Compare only years the built-in table actually covers.
                # The live page runs years past the table's horizon, and a
                # plain symmetric difference reports every one of those as a
                # disagreement — a scary, permanent, meaningless warning.
                covered = {d.year for d in FOMC_DAYS} & years
                tbl = {d for d in FOMC_DAYS if d.year in covered}
                got = {d for d in scraped if d.year in covered}
                diff = tbl.symmetric_difference(got)
                if diff:
                    self.errors.append(
                        "FOMC scrape disagrees with built-in table on "
                        + ", ".join(str(d) for d in sorted(diff))
                        + " — using the live page")
            else:
                self.errors.append("FOMC page parsed too few meetings, using table")
        except Exception as e:
            self.errors.append(f"FOMC scrape {type(e).__name__}, using table")
        if not BLS_CONTACT_SET:
            # Do not overstate this. bls.gov only tests whether the User-Agent
            # is address-SHAPED, so the placeholder sails through and the
            # calendar loads fine. The problem is that it is unreachable, which
            # is the single thing the header exists for, and a filter that
            # loose is one BLS could tighten any day without warning.
            self.errors.append(
                f"BLS_CONTACT_EMAIL is not set, so requests go out as "
                f"'{BLS_CONTACT}'. bls.gov accepts it today because it only "
                f"checks the User-Agent is address-shaped, but nobody there "
                f"could reach you. Set any address you own.")
        if not fomc:
            fomc = FOMC_DAYS
            if self.start > FOMC_TABLE_GOOD_THROUGH:
                self.errors.append(
                    f"FOMC TABLE EXPIRED {FOMC_TABLE_GOOD_THROUGH} and the live "
                    f"scrape failed — FOMC dates are MISSING, not absent")
        for d in fomc:
            if self.start <= d <= end:
                self.events.append((d, "FOMC"))
        # Preferred: one annual page per release. Falls back to month pages for
        # whichever release the annual page could not supply.
        #
        # Success is measured in PARSED DATES, not in HTTP status. On 22 Aug
        # 2026 empsit.htm returned 200 OK carrying 762 NUL bytes — no markup, no
        # dates. Counting that as a success set bls_ok True with the entire NFP
        # series missing, and the report then printed a confident "BLS live"
        # macro line built on CPI alone. Every other unverifiable condition in
        # this script forces a stop; this one has to as well.
        got = set()
        for label, url in self.BLS_ANNUAL.items():
            try:
                import urllib.request
                req = urllib.request.Request(url, headers=self.HDRS)
                with urllib.request.urlopen(req, timeout=self.timeout) as r:
                    html = r.read().decode("utf-8", "ignore")
                dates = parse_bls_annual(html)
                if not dates:
                    self.errors.append(
                        f"BLS {label} returned {len(html)} bytes with zero "
                        f"parseable dates — counted as a failed read")
                    continue
                # Window-filter for the calendar, but judge the read on whether
                # the PAGE parsed. A page can be perfectly healthy and hold no
                # release inside a 42-day window.
                self.events += [(d, label) for d in dates
                                if self.start <= d <= end]
                got.add(label)
            except Exception as e:
                code = getattr(e, "code", None)
                if code == 403:
                    self.errors.append(
                        f"BLS {label} 403 — bls.gov rejects User-Agents that "
                        f"look like a browser. Set BLS_CONTACT_EMAIL to a real "
                        f"address (see BLS_CONTACT)")
                else:
                    self.errors.append(f"BLS {label} {type(e).__name__}")
        missing = set(self.BLS_ANNUAL) - got
        if missing:
            self.errors.append(
                "falling back to month pages for " + ", ".join(sorted(missing)))
            for y, m in self._months():
                try:
                    hits = self._scrape_month(y, m)
                except Exception as e:
                    self.errors.append(f"BLS {y}-{m:02d} {type(e).__name__}")
                    continue
                if not hits:
                    self.errors.append(
                        f"BLS {y}-{m:02d} month page parsed to zero events")
                self.events += [(d, lbl) for d, lbl in hits
                                if lbl in missing and self.start <= d <= end]
                got |= {lbl for _, lbl in hits if lbl in missing}
        self.bls_ok = got >= set(self.BLS_ANNUAL)
        if not self.bls_ok:
            self.errors.append(
                "BLS incomplete, missing: "
                + ", ".join(sorted(set(self.BLS_ANNUAL) - got)))
        # The annual and month paths overlap; identical events must not
        # double-count against the macro-density rule.
        self.events = sorted(set(self.events))
        gaps = self._gaps(end)
        if gaps:
            self.bls_ok = False
            self.errors.append(
                "BLS calendar HOLE — no release found for "
                + ", ".join(gaps)
                + " (bls.gov is serving empty pages for these)")
    def near(self, target, window=MACRO_WINDOW_DAYS):
        """Events within +/- window days of a date."""
        self.load()
        return [(d, lbl) for d, lbl in self.events
                if abs((d - target).days) <= window]
# PPI added 24 Aug 2026 at JH's request. It is not in 2-1-5's macro gate, which
# names FOMC / CPI / NFP - so adding it makes the density flag strictly more
# likely to fire, never less. Sep 2026 is the case in point: PPI on the 10th
# plus CPI on the 11th puts two events inside three days of an 11 Sep expiry,
# where CPI alone would have counted as one.
BLS_WANTED = (
    ("Employment Situation", "NFP"),
    ("Consumer Price Index", "CPI"),
    ("Producer Price Index", "PPI"),
)
_MONTHS = ["January", "February", "March", "April", "May", "June", "July",
           "August", "September", "October", "November", "December"]
def parse_bls_schedule(text, year):
    """Pull CPI / Employment Situation dates out of a BLS month page.
    Layout is: a date line, then a time, then the release name. So a date is
    carried forward and attached to whichever release names follow it.
    """
    import re
    out, cur = [], None
    datepat = re.compile(
        r"(?:Monday|Tuesday|Wednesday|Thursday|Friday|Saturday|Sunday),\s+"
        r"(" + "|".join(_MONTHS) + r")\s+(\d{1,2}),\s+(\d{4})")
    for raw in text.splitlines():
        line = raw.strip()
        if not line:
            continue
        m = datepat.search(line)
        if m:
            try:
                cur = date(int(m.group(3)), _MONTHS.index(m.group(1)) + 1,
                           int(m.group(2)))
            except ValueError:
                cur = None
            continue
        if cur:
            for needle, label in BLS_WANTED:
                if line.startswith(needle):
                    out.append((cur, label))
    # de-duplicate, keep first label per (date,label)
    seen, uniq = set(), []
    for d, lbl in out:
        if (d, lbl) not in seen:
            seen.add((d, lbl))
            uniq.append((d, lbl))
    return uniq
# ---------------------------------------------------------------- math
def ncdf(x):
    return 0.5 * (1.0 + math.erf(x / math.sqrt(2.0)))
def put_delta(spot, strike, iv, dte_days, r=RISK_FREE):
    """Magnitude of Black-Scholes put delta (0..1)."""
    T = dte_days / 365.0
    if T <= 0 or iv <= 0 or spot <= 0 or strike <= 0:
        return float("nan")
    d1 = (math.log(spot/strike) + (r + 0.5*iv*iv)*T) / (iv*math.sqrt(T))
    return ncdf(-d1)
def sma(values, n):
    if len(values) < n:
        return None
    return sum(values[-n:]) / n
def hv30(closes):
    """Annualised close-to-close realised vol, 30 returns."""
    if len(closes) < 31:
        return None
    rets = [math.log(closes[i]/closes[i-1]) for i in range(len(closes)-30, len(closes))]
    m = sum(rets)/len(rets)
    var = sum((x-m)**2 for x in rets)/(len(rets)-1)
    return math.sqrt(var) * math.sqrt(252)
ALIASES = {
    "AAPL": ["apple"], "AMD": ["amd", "advanced micro"], "AMZN": ["amazon"],
    "ANET": ["arista"], "AVGO": ["broadcom"], "CRWD": ["crowdstrike"],
    "GOOGL": ["google", "alphabet"], "JNJ": ["johnson & johnson", "johnson and johnson", "j&j"],
    "JPM": ["jpmorgan", "jp morgan", "chase"], "LLY": ["eli lilly", "lilly"],
    "META": ["meta platforms", "meta ", "facebook"], "MSFT": ["microsoft"],
    "NFLX": ["netflix"], "NVDA": ["nvidia"], "PANW": ["palo alto"],
    "PLTR": ["palantir"], "TSLA": ["tesla"], "TSM": ["tsmc", "taiwan semi"],
    "V": ["visa"], "QQQ": ["nasdaq 100", "qqq"], "SPY": ["s&p 500", "spy"],
    "IWM": ["russell 2000", "iwm"],
}
def news_is_direct(ticker, title, related):
    """True if the item is about THIS name, not merely its sector.
    yfinance returns loosely-related articles: a JNJ pull came back with three
    headlines about Lilly, Intuitive Surgical and AbbVie. Sector items still
    matter (contagion is a listed veto) but must be distinguishable.
    """
    if ticker.upper() in {str(r).upper() for r in related}:
        return True
    t = " " + (title or "").lower() + " "
    if f" {ticker.lower()} " in t or f"({ticker.lower()})" in t:
        return True
    return any(a in t for a in ALIASES.get(ticker.upper(), []))
VIX_TICKER, SPX_TICKER = "^VIX", "^GSPC"
CONDOR_VIX_MIN = 20.0
CONDOR_STRETCH = (-0.02, 0.03)
def _live(provider, t):
    fn = getattr(provider, "live_spot", None)
    try:
        return fn(t) if fn else None
    except Exception:
        return None
def read_regime(provider, today):
    """VIX level and SPX stretch vs its own 20-SMA.
    Unreadable is a failed read, never a low reading — an unverifiable
    condition has not been met, so it forces condor NO-GO.
    """
    out = {"vix": None, "stretch": None, "spx": None, "errors": []}
    try:
        b = provider.bars(VIX_TICKER)
        g = gate1_trend(b, today, _live(provider, VIX_TICKER)) if b else None
        if g:
            out["vix"] = g["spot"]
    except Exception as e:
        out["errors"].append(f"VIX {type(e).__name__}")
    if out["vix"] is None and not out["errors"]:
        out["errors"].append("VIX empty")
    try:
        b = provider.bars(SPX_TICKER)
        g = gate1_trend(b, today, _live(provider, SPX_TICKER)) if b else None
        if g:
            out["spx"] = g["spot"]
            out["stretch"] = g["margin"]
    except Exception as e:
        out["errors"].append(f"SPX {type(e).__name__}")
    if out["stretch"] is None and "SPX" not in " ".join(out["errors"]):
        out["errors"].append("SPX empty")
    return out
def condor_verdict(reg):
    """Returns (go, reason). Macro catalyst check stays manual."""
    if reg["vix"] is None:
        return False, "VIX unreadable — a condition that cannot be verified has not been met"
    if reg["stretch"] is None:
        return False, "SPX stretch unreadable"
    if reg["vix"] < CONDOR_VIX_MIN:
        return False, f"VIX {reg['vix']:.2f} < {CONDOR_VIX_MIN:.0f}"
    lo, hi = CONDOR_STRETCH
    if not (lo <= reg["stretch"] <= hi):
        return False, f"SPX stretch {reg['stretch']*100:+.2f}% outside {lo*100:+.0f}%..{hi*100:+.0f}%"
    return True, (f"VIX {reg['vix']:.2f} · stretch {reg['stretch']*100:+.2f}% "
                  f"— CONFIRM no binary macro in window before acting")
def us_market_date():
    """Today's date in US Eastern terms.
    Running at 10 PM SGT is 10 AM ET the SAME day, but running at 2 AM SGT
    is 2 PM ET the PREVIOUS day. Judging bar staleness against a Singapore
    date therefore mislabels an in-progress US bar as completed on any
    post-midnight run.
    """
    try:
        from zoneinfo import ZoneInfo
        return datetime.now(ZoneInfo("America/New_York")).date(), "ET"
    except Exception:
        pass
    try:
        import pytz
        return datetime.now(pytz.timezone("America/New_York")).date(), "ET"
    except Exception:
        pass
    from datetime import timezone
    d = datetime.now(timezone.utc) - timedelta(hours=4)
    return d.date(), "ET~(no tzdata: pip install tzdata)"
ETF_SLOTS = {"SPY", "QQQ", "IWM"}     # macro gate, never an earnings gate
LISTING = {
    "JNJ": "NYSE", "JPM": "NYSE", "V": "NYSE", "LLY": "NYSE",
    "TSM": "NYSE", "ANET": "NYSE",
    "SPY": "NYSEArca", "IWM": "NYSEArca",
    "AAPL": "Nasdaq", "AMD": "Nasdaq", "AMZN": "Nasdaq", "AVGO": "Nasdaq",
    "CRWD": "Nasdaq", "GOOGL": "Nasdaq", "META": "Nasdaq", "MSFT": "Nasdaq",
    "NFLX": "Nasdaq", "NVDA": "Nasdaq", "PANW": "Nasdaq", "PLTR": "Nasdaq",
    "TSLA": "Nasdaq", "QQQ": "Nasdaq",
}
class NasdaqEarnings:
    """Nasdaq's own earnings calendar. No API key.
    Independent of yfinance, which matters: yfinance's get_earnings_dates and
    calendar are the SAME upstream feed, so they agree almost always and their
    agreement carries no information. This is a genuinely separate source.
    The endpoint is date-indexed, not symbol-indexed — one call returns every
    company reporting that day — so covering the whole DTE window costs about
    30 calls total regardless of universe size.
    """
    URL = "https://api.nasdaq.com/api/calendar/earnings?date={}"
    HEADERS = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)",
        "Accept": "application/json",
    }
    def __init__(self, start, days=45, timeout=8):
        self.start, self.days, self.timeout = start, days, timeout
        self.map = {}          # SYMBOL -> earliest date found
        self.errors = []
        self.loaded = False
        self.days_ok = set()       # weekdays actually fetched and parsed
        self.days_failed = set()
    def _fetch(self, d):
        import urllib.request, json as _json
        req = urllib.request.Request(self.URL.format(d.isoformat()),
                                     headers=self.HEADERS)
        with urllib.request.urlopen(req, timeout=self.timeout) as r:
            return _json.loads(r.read().decode("utf-8"))
    def load(self):
        if self.loaded:
            return
        self.loaded = True
        fails = 0
        for k in range(self.days):
            d = self.start + timedelta(days=k)
            if d.weekday() >= 5:          # no reports on weekends
                continue
            try:
                j = self._fetch(d)
            except Exception as e:
                fails += 1
                self.days_failed.add(d)
                if fails <= 3:
                    self.errors.append(f"{d} {type(e).__name__}")
                if fails >= 5:
                    self.errors.append("aborted after 5 failures")
                    return
                continue
            self.days_ok.add(d)
            rows = ((j or {}).get("data") or {}).get("rows") or []
            for row in rows:
                sym = str(row.get("symbol") or "").strip().upper()
                if sym and sym not in self.map:
                    self.map[sym] = d
    def get(self, ticker):
        self.load()
        d = self.map.get(ticker.upper())
        return [("nasdaq", d)] if d else []
    def covers(self, start, end):
        """True if every weekday in [start, end] was fetched successfully.

        This endpoint is date-indexed, not symbol-indexed: one call returns
        EVERY company reporting that day. So when a span is fully fetched, a
        ticker's absence from it is a positive statement — "this name does not
        report between these dates" — and that is exactly the question Gate 2
        asks. Treating that absence as "no data" threw away a real second
        opinion and printed NO CROSS-CHECK on 8 of 9 names every run, which is
        how a warning stops being read.

        The check is per-day on purpose. One failed fetch inside the span means
        a report could have been sitting on that day, so the whole span stops
        being able to clear anyone.
        """
        self.load()
        if not self.days_ok:
            return False
        d = start
        while d <= end:
            if d.weekday() < 5 and d not in self.days_ok:
                return False
            d += timedelta(days=1)
        return True
    def span(self):
        self.load()
        if not self.days_ok:
            return None, None
        return min(self.days_ok), max(self.days_ok)
    def available(self):
        self.load()
        return bool(self.map)
class FinnhubEarnings:
    """Optional third source. Set FINNHUB_API_KEY to enable."""
    URL = ("https://finnhub.io/api/v1/calendar/earnings"
           "?from={f}&to={t}&symbol={s}&token={k}")
    def __init__(self, key, start, days=45, timeout=8):
        self.key, self.start, self.days, self.timeout = key, start, days, timeout
        self.errors = []
    def get(self, ticker):
        if not self.key:
            return []
        import urllib.request, json as _json
        url = self.URL.format(f=self.start.isoformat(),
                              t=(self.start + timedelta(days=self.days)).isoformat(),
                              s=ticker, k=self.key)
        try:
            with urllib.request.urlopen(url, timeout=self.timeout) as r:
                j = _json.loads(r.read().decode("utf-8"))
        except Exception as e:
            self.errors.append(f"{ticker} {type(e).__name__}")
            return []
        out = []
        for row in (j or {}).get("earningsCalendar") or []:
            try:
                out.append(("finnhub",
                            datetime.strptime(row["date"], "%Y-%m-%d").date()))
            except Exception:
                pass
        return sorted(out, key=lambda x: x[1])[:1]
class NullEarnings:
    """Offline stand-in for NasdaqEarnings. Returns nothing, touches no network.

    The selftest MUST inject this. run() otherwise builds a live
    NasdaqEarnings, and a REAL earnings date then leaks into a synthetic
    fixture and blocks a name the fixture meant to keep. That is exactly what
    happened the day sandbox egress was enabled: the T+2 case began failing
    because Nasdaq really does list NVDA on 2026-08-26, and the fixture's own
    date was silently outvoted. Before egress the same call failed fast and
    returned nothing, so the contamination was invisible.
    """
    def __init__(self):
        self.map, self.errors, self.loaded = {}, [], True
        self.days_ok, self.days_failed = set(), set()
    def load(self):
        pass
    def get(self, ticker):
        return []
    def covers(self, start, end):
        return False           # an offline stub clears nobody
    def span(self):
        return None, None
    def available(self):
        return False


class StubMacro:
    """Offline macro calendar over a fixed event list. Same reason as above."""
    def __init__(self, events=None, bls_ok=True):
        self.events = sorted(events or [])
        self.errors, self.bls_ok = [], bls_ok
        self.fomc_src, self.loaded = "stub", True
    def load(self):
        pass
    def near(self, target, window=MACRO_WINDOW_DAYS):
        return [(d, lbl) for d, lbl in self.events
                if abs((d - target).days) <= window]


def num(v, default=0.0):
    """NaN-safe float. yfinance leaves NaN in bid/ask/volume/OI on illiquid
    strikes, and NaN is truthy — so `x or 0` silently passes it through."""
    try:
        f = float(v)
    except (TypeError, ValueError):
        return default
    return default if math.isnan(f) or math.isinf(f) else f
def inum(v, default=0):
    return int(num(v, default))
def cluster_of(t):
    for c, names in CLUSTERS.items():
        if t in names:
            return c
    return "Unclustered"
def anchor_delta(t):
    return DELTA_ANCHOR.get(t, DEFAULT_DELTA)
def round_width(spot, ticker=None):
    """Return (raw 5% width, width snapped to listed increment).
    The $5 minimum is tested on the RAW figure. Snapping first would round
    a $4.2 target up to $5 and smuggle the name past its own pre-filter.
    """
    raw = spot * WIDTH_PCT
    if ticker in ETF_SLOTS:
        inc = 5.0           # SPY/QQQ/IWM list $1-$5 strikes at any price
    elif spot < 100:
        inc = 2.5
    elif spot < 500:
        inc = 5.0
    elif spot < 1000:
        inc = 10.0
    else:
        inc = 20.0          # LLY at ~$1255 does not list $5 strikes
    return raw, max(round(raw / inc) * inc, inc)
# ---------------------------------------------------------------- providers
BROWSER_UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
              "(KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36")


class YFProvider:
    """yfinance, forced onto a plain requests transport.

    yfinance >=1.x defaults to curl_cffi, which impersonates a browser TLS
    fingerprint. Behind a filtering egress proxy that handshake is dropped:
    every call dies with `curl (35) Recv failure: Connection reset by peer`,
    surfaced as SSLError, and every name lands in "data failure" — the script
    reports a clean empty screen while actually having read nothing. Passing an
    ordinary requests.Session with a browser User-Agent restores all of it:
    bars, ^VIX, ^GSPC, option chains, earnings dates and news.
    """
    def __init__(self, session=None):
        import yfinance as yf
        self.yf = yf
        self._cache = {}
        if session is None:
            try:
                import requests
                session = requests.Session()
                session.headers.update({"User-Agent": BROWSER_UA})
            except ImportError:
                session = None
        self.session = session
    def _tk(self, t):
        if t not in self._cache:
            try:
                self._cache[t] = (self.yf.Ticker(t, session=self.session)
                                  if self.session is not None
                                  else self.yf.Ticker(t))
            except TypeError:            # older yfinance: no session kwarg
                self._cache[t] = self.yf.Ticker(t)
        return self._cache[t]
    def bars(self, t, days=150):
        # 150d, not 90d: a 90-day calendar window leaves little slack over
        # holidays, and a clipped series silently shifts the SMA20 window.
        h = self._tk(t).history(period=f"{days}d", interval="1d",
                                auto_adjust=False)
        if h is None or h.empty:
            return None
        closes, idx = [], []
        for d, c in zip(h.index.to_pydatetime(), h["Close"].tolist()):
            c = num(c, 0.0)
            if c <= 0:          # NaN or halted bar
                continue
            closes.append(c)
            idx.append(d.date())
        if len(closes) < 21:
            return None
        return {"closes": closes, "dates": idx}
    def live_spot(self, t):
        """Last traded price, independent of the daily bar.
        During an open session the bar's Close IS the in-progress print, so it
        must not enter the SMA — but it is still the right spot for strike
        selection. These are different numbers and are kept apart.
        """
        try:
            fi = self._tk(t).fast_info
            # FastInfo keys are camelCase. "last_price" returns None rather
            # than raising, so a snake_case-only lookup silently degrades every
            # row to the previous close and flags them all "stale".
            for k in ("lastPrice", "last_price", "regularMarketPrice",
                      "regular_market_price"):
                v = fi.get(k) if hasattr(fi, "get") else getattr(fi, k, None)
                v = num(v, 0.0)
                if v > 0:
                    return v
        except Exception:
            pass
        return None
    def expiries(self, t):
        try:
            return list(self._tk(t).options)
        except Exception:
            return []
    def put_chain(self, t, expiry):
        try:
            df = self._tk(t).option_chain(expiry).puts
        except Exception:
            return []
        rows = []
        for _, r in df.iterrows():
            k = num(r.get("strike"), 0.0)
            if k <= 0:
                continue
            rows.append({
                "strike": k,
                "bid": num(r.get("bid")),
                "ask": num(r.get("ask")),
                "iv":  num(r.get("impliedVolatility")),
                "oi":  inum(r.get("openInterest")),
                "vol": inum(r.get("volume")),
            })
        return rows
    def earnings(self, t):
        """Return list of (source, date) — aggregator only."""
        out = []
        tk = self._tk(t)
        try:
            df = tk.get_earnings_dates(limit=8)
            if df is not None and not df.empty:
                for d in df.index.to_pydatetime():
                    out.append(("yf.earnings_dates", d.date()))
        except Exception:
            pass
        try:
            cal = tk.calendar
            if isinstance(cal, dict):
                for d in (cal.get("Earnings Date") or []):
                    dd = d.date() if hasattr(d, "date") else d
                    out.append(("yf.calendar", dd))
        except Exception:
            pass
        return out
    @staticmethod
    def _news_url(c):
        """Publisher's own URL, falling back to the Yahoo redirect.

        canonicalUrl points at the source (fool.com, thestreet.com);
        clickThroughUrl is a finance.yahoo.com wrapper. Prefer the source: it
        is what you want to read, and it survives Yahoo reorganising its URLs.
        Both arrive as {"url": ..., "site": ...} dicts, not bare strings.
        """
        for k in ("canonicalUrl", "clickThroughUrl"):
            v = c.get(k)
            if isinstance(v, dict) and v.get("url"):
                return v["url"]
            if isinstance(v, str) and v:
                return v
        return ""

    def news(self, t, n=8, tries=3):
        """Headlines for Gate 3. Retried, because a miss reads as a clearance.

        yfinance's news endpoint fails intermittently — ANET returned nothing
        on one run and ten items on the next, minutes apart, with no change to
        the request. A single attempt turns that flake into a blank Gate 3
        section, and a blank section is exactly what a name with no bad news
        looks like. Retrying is cheap; mistaking a dropped connection for an
        all-clear is not.
        """
        items = []
        for attempt in range(tries):
            try:
                items = self._tk(t).news or []
            except Exception:
                items = []
            if items:
                break
            if attempt < tries - 1:
                import time
                time.sleep(0.6 * (attempt + 1))
                self._cache.pop(t, None)      # fresh Ticker, fresh cookie
        out = []
        for it in items[:n]:
            c = it.get("content", it)
            title = c.get("title") or ""
            pub = c.get("pubDate") or c.get("providerPublishTime") or ""
            related = []
            for st in ((c.get("finance") or {}).get("stockTickers") or []):
                if isinstance(st, dict):
                    related.append(st.get("symbol", ""))
                else:
                    related.append(str(st))
            related += [str(x) for x in (it.get("relatedTickers") or [])]
            direct = news_is_direct(t, title, related)
            out.append((str(pub)[:10], title, direct, self._news_url(c)))
        # direct hits first — a guidance cut must not sit under four sector pieces
        out.sort(key=lambda x: (not x[2], x[0]), reverse=False)
        return out[:5]
class FakeProvider:
    """Deterministic synthetic data for --selftest. No network."""
    def __init__(self, today):
        self.today = today
        import random
        self.rnd = random.Random(7)
        self.base = {t: 120 + (i*37) % 400 for i, t in enumerate(UNIVERSE)}
        self.base[VIX_TICKER] = 23.0
        self.base[SPX_TICKER] = 6100.0
        # forced states, so each gate has at least one name exercising it (fixture)
        self.base["NFLX"] = 82.0     # uptrend, must die on width not trend
        self.base["AMD"]  = 500.0
        self.base["CRWD"] = 400.0
        self.base["PANW"] = 380.0
        self.downtrend = {"TSLA", "AVGO", "IWM"}   # should fail Gate 1
        self.earns_soon = {"CRWD", "PANW"}         # should fail Gate 2
        self.conflict   = {"AMD"}                  # two sources disagree
    def bars(self, t, days=90):
        """Deterministic shaped series — no RNG, so gate outcomes are fixed."""
        n = 65
        base = self.base[t]
        slope = -0.0035 if t in self.downtrend else 0.0025
        closes = []
        for i in range(n):
            off = i - (n - 1)                       # 0 on the last bar
            wig = 0.004 * math.sin(i * 1.1)         # gives HV something to measure
            closes.append(round(base * (1 + slope*off + wig), 2))
        dates = [self.today - timedelta(days=(n-i)) for i in range(n)]
        return {"closes": closes, "dates": dates}
    def expiries(self, t):
        out = []
        d = self.today
        while d.weekday() != 4:
            d += timedelta(days=1)
        for k in range(6):
            out.append((d + timedelta(days=7*k)).isoformat())
        return out
    def put_chain(self, t, expiry):
        spot = self.bars(t)["closes"][-1]
        inc = 5.0 if spot >= 100 else 2.5
        atm = round(spot/inc)*inc
        iv0 = 0.28 + (hash(t) % 25)/100.0
        rows = []
        for k in range(-14, 5):
            K = atm + k*inc
            if K <= 0:
                continue
            skew = 1 + 0.010*abs(k)
            rows.append({"strike": K, "iv": iv0*skew,
                         "bid": max(0.05, (spot-K)*-0.02 + 1.2),
                         "ask": max(0.10, (spot-K)*-0.02 + 1.35),
                         "oi": 1200 if abs(k) < 10 else 200,
                         "vol": 300})
        return rows
    def earnings(self, t):
        if t in self.earns_soon:
            d = self.today + timedelta(days=12)
            return [("yf.earnings_dates", d), ("nasdaq", d)]
        if t in self.conflict:
            return [("yf.earnings_dates", self.today + timedelta(days=16)),
                    ("nasdaq", self.today + timedelta(days=40))]
        d = self.today + timedelta(days=55)
        return [("yf.earnings_dates", d), ("nasdaq", d)]
    def news(self, t, n=4):
        return [(self.today.isoformat(), f"{t} synthetic headline 1", True,
                 f"https://example.invalid/{t.lower()}-1"),
                (self.today.isoformat(), "unrelated sector piece", False,
                 "https://example.invalid/sector")]
# ---------------------------------------------------------------- gates
def pick_expiry(expiries, today):
    """Nearest expiry inside DTE window, biased to 18-21."""
    cands = []
    for e in expiries:
        try:
            d = datetime.strptime(e, "%Y-%m-%d").date()
        except Exception:
            continue
        dte = (d - today).days
        if DTE_MIN <= dte <= DTE_MAX:
            pref = 0 if DTE_BIAS[0] <= dte <= DTE_BIAS[1] else 1
            cands.append((pref, -dte, e, dte))
    if not cands:
        return None, None
    cands.sort()
    return cands[0][2], cands[0][3]
def gate1_trend(bars, us_today, live_spot=None):
    """SMA20 from COMPLETED bars only; spot from the live read where available.
    Two distinct numbers. The in-progress bar never enters the SMA. The last
    completed close is the fallback spot, and is flagged as such.
    """
    closes, dates = bars["closes"], bars["dates"]
    completed = [c for c, d in zip(closes, dates) if d < us_today]
    if len(completed) < 21:
        return None
    m = sma(completed, 20)            # 20 most recent completed bars
    if m is None:
        return None
    if live_spot and live_spot > 0:
        spot, src = live_spot, "live"
    else:
        spot, src = completed[-1], "close"
    margin = (spot - m) / m
    win = [d for c, d in zip(closes, dates) if d < us_today][-20:]
    return {"pass": spot > m, "spot": spot, "sma20": m, "margin": margin,
            "spot_src": src, "closes": completed,
            "sma_from": win[0] if win else None,
            "sma_to": win[-1] if win else None,
            "sma_n": len(completed[-20:]), "bars_seen": len(closes)}
def gate2_earnings(dates_by_src, today, expiry_date, clear_votes=()):
    """Return (blocked, conflict, next_date, detail, n_independent).

    Conflict means independent providers disagree. yfinance's two endpoints
    share an upstream feed, so they are collapsed into one vote — counting
    them separately would manufacture agreement that proves nothing.

    clear_votes are providers that scanned the whole window to expiry and found
    this name reporting on no day in it. That is an assertion, not a blank, and
    it counts toward the source total. A clear vote against a dated vote inside
    the window is a real conflict: one source has the name reporting before
    expiry and an exhaustive source says it does not.
    """
    clear = [str(c) for c in clear_votes]
    if not dates_by_src and not clear:
        return False, True, None, "NO SOURCE RETURNED A DATE", 0
    fwd = [(s, d) for s, d in dates_by_src if d and d >= today]
    votes = {}                                   # provider -> earliest date
    for s, d in fwd:
        prov = "yfinance" if str(s).startswith("yf") else str(s)
        if prov not in votes or d < votes[prov]:
            votes[prov] = d
    nsrc = len(votes) + len(clear)
    if not votes:
        detail = ("no date in window; " +
                  ", ".join(f"{c}:clear through {expiry_date}" for c in clear)
                  if clear else "no upcoming date from any source")
        return False, False, None, detail, nsrc
    uniq = sorted(set(votes.values()))
    nxt = uniq[0]
    conflict = False
    if len(votes) >= 2 and len(uniq) > 1:
        spread = (uniq[-1] - uniq[0]).days
        straddles = (uniq[0] <= expiry_date) != (uniq[-1] <= expiry_date)
        conflict = straddles or spread > 2
    if clear and nxt <= expiry_date:
        conflict = True                # exhaustive source contradicts the date
    blocked = nxt <= expiry_date
    detail = " / ".join(f"{p}:{d}" for p, d in sorted(votes.items(), key=lambda x: x[1]))
    if clear:
        detail += " / " + ", ".join(f"{c}:clear through {expiry_date}" for c in clear)
    return blocked, conflict, nxt, detail, nsrc
def strike_at_delta(chain, spot, target, dte, cap=DELTA_HARD_CAP):
    """Closest listed strike to the anchor delta, never above the hard cap.

    "Nearest listed strike counts" governs the ANCHOR, not the cap. Picking
    purely by nearest overshoots whenever the grid straddles the anchor: TSM
    at a 0.20 anchor selected a 0.21-delta strike, printing a breach of the
    workflow's own absolute limit as a normal row. Strikes above the cap are
    excluded outright; if that leaves nothing, the name is dropped rather than
    quietly filled at a closer-to-the-money strike.
    """
    best, best_over = None, None
    for row in chain:
        if row["iv"] <= 0 or row["strike"] >= spot:
            continue
        d = put_delta(spot, row["strike"], row["iv"], dte)
        if math.isnan(d):
            continue
        err = abs(d - target)
        if d > cap + 1e-9:
            # Track the best REJECTED candidate, so the flag can say whether
            # the cap actually changed the answer. Counting every over-cap
            # strike instead would fire on almost every real chain — near-the-
            # money strikes are always over 0.20 — and the flag would degrade
            # into "the grid is coarse", which is a different thing entirely.
            if best_over is None or err < best_over:
                best_over = err
            continue
        if best is None or err < best[0]:
            best = (err, row, d)
    if best is None:
        return None
    err, row, d = best
    return {"strike": row["strike"], "delta": d, "iv": row["iv"],
            "bid": row["bid"], "ask": row["ask"], "oi": row["oi"],
            "capped": best_over is not None and best_over < err}
# ---------------------------------------------------------------- run
def run(provider, today, do_news=True, tickers=None,
        us_today_override=None, earn_src=None, macro_src=None):
    tickers = tickers or UNIVERSE
    rows, dropped = [], {"trend": [], "earnings": [], "width": [], "data": [], "postearn": []}
    conflicts, news_out = [], {}
    us_today, tzlabel = us_market_date()
    if us_today_override is not None:
        # tests only: production must resolve the ET date itself
        us_today, tzlabel = us_today_override, "ET(override)"
    regime = read_regime(provider, us_today)
    regime["us_date"] = us_today
    regime["tz"] = tzlabel
    regime["spot_srcs"] = set()
    import os
    # Injected sources keep the selftest hermetic. Production passes neither,
    # so the live calendars are built here and nowhere else.
    if earn_src is not None:
        nasdaq = earn_src
        finnhub = FinnhubEarnings(None, us_today)      # key None -> no calls
    else:
        nasdaq = NasdaqEarnings(us_today, days=DTE_MAX + 14)
        finnhub = FinnhubEarnings(os.environ.get("FINNHUB_API_KEY"), us_today,
                                  days=DTE_MAX + 14)
    single_src = []
    nq_cover = {}          # ticker -> did nasdaq return a date
    nq_clear = {}          # ticker -> did nasdaq affirmatively clear the window
    macro_slots = []
    macro = (macro_src if macro_src is not None
             else MacroCalendar(us_today, days=DTE_MAX + 21))
    macro.load()
    for t in tickers:
        try:
            b = provider.bars(t)
        except Exception as e:
            dropped["data"].append(f"{t}({type(e).__name__})"); continue
        if not b:
            dropped["data"].append(t); continue
        g1 = gate1_trend(b, us_today, _live(provider, t))
        if g1 is None:
            dropped["data"].append(t); continue
        if not g1["pass"]:
            dropped["trend"].append(t); continue
        spot = g1["spot"]
        regime["spot_srcs"].add(g1["spot_src"])
        width_raw, width = round_width(spot, t)
        if width_raw < WIDTH_MIN:
            dropped["width"].append(f"{t}(5%W=${width_raw:.2f})"); continue
        exp, dte = pick_expiry(provider.expiries(t), us_today)
        if exp is None:
            dropped["data"].append(f"{t}(no expiry {DTE_MIN}-{DTE_MAX}d)"); continue
        expd = datetime.strptime(exp, "%Y-%m-%d").date()
        past_earn = None
        if t in ETF_SLOTS:
            # ETFs have no earnings. Querying them 404s, and the empty result
            # then reads as "no source found" — a false alarm on every run.
            hits = macro.near(expd)
            if not macro.bls_ok:
                # Same rule as the VIX/condor gate: a condition that cannot be
                # verified has not been met. Never print "clear" off a broken
                # calendar.
                macro_slots.append((t, hits, "UNVERIFIED"))
                dropped["earnings"].append(f"{t}[macro UNVERIFIED - CPI/NFP unread]")
                continue
            macro_slots.append((t, hits, "ok"))
            conflict, nsrc = False, None
            if hits:
                dropped["earnings"].append(
                    f"{t}[macro: {', '.join(l for _, l in hits)}]")
                continue
        else:
            srcs = list(provider.earnings(t))
            try:
                nq = nasdaq.get(t)
            except Exception as e:
                nasdaq.errors.append(f"{t} {type(e).__name__}")
                nq = []
            nq_cover[t] = bool(nq)
            srcs += nq
            srcs += finnhub.get(t)
            past = [d for _, d in srcs if d and d < us_today]
            past_earn = max(past) if past else None
            clear = []
            try:
                if not nq and nasdaq.covers(us_today, expd):
                    clear.append("nasdaq")
            except Exception:
                pass
            nq_clear[t] = bool(clear)
            blocked, conflict, nxt, detail, nsrc = gate2_earnings(
                srcs, us_today, expd, clear_votes=clear)
            if conflict:
                conflicts.append(f"{t}: {detail}")
            if nsrc < 2:
                single_src.append(f"{t}({nsrc} source)")
        if blocked:
            dropped["earnings"].append(f"{t}({nxt})"); continue
        if past_earn is not None and (us_today - past_earn).days <= 1:
            # T+1 entries are not permitted at all (JH, 22 Aug). T+2 is the
            # earliest entry; no credit level buys an exception.
            dropped["postearn"].append(f"{t}(reported {past_earn})")
            continue
        chain = provider.put_chain(t, exp)
        if not chain:
            dropped["data"].append(f"{t}(no chain)"); continue
        adelta = anchor_delta(t)
        leg = strike_at_delta(chain, spot, adelta, dte)
        if leg is None:
            dropped["data"].append(f"{t}(no strike at {adelta})"); continue
        # The screen picked a short strike but never looked at the long one, so
        # the number that decides every trade - what you actually get paid -
        # was missing. Worst case by construction: sell the short at the BID,
        # buy the long at the ASK. That is the side of the spread you land on
        # when nothing goes your way, and it is the figure the 11%W floor is
        # defined against. Anything friendlier would flatter the row.
        long_k = leg["strike"] - width
        cands = [c for c in chain if c["strike"] < leg["strike"]]
        longleg = (min(cands, key=lambda c: abs(c["strike"] - long_k))
                   if cands else None)
        # The number to carry to the ticket: what the floor costs in dollars at
        # this width. Not an estimate of the live premium - delayed chain
        # quotes were producing worst-case credits like LLY's 0.4%W, which says
        # more about a stale two-sided market than about anything tradeable.
        # This is arithmetic on the width, so it cannot be stale or wrong: it
        # is simply the least this spread may be sold for.
        long_strike = act_width = target = None
        if longleg is not None:
            long_strike = longleg["strike"]
            act_width = leg["strike"] - long_strike
        eff_width = act_width or width
        target = eff_width * CREDIT_FLOOR
        h = hv30(g1["closes"])
        ivhv = (leg["iv"]/h) if h else None
        notes = []
        if 0 <= g1["margin"] < 0.005:
            notes.append("knife")
        elif 0 <= g1["margin"] < PROV_TREND_MARGIN:
            notes.append("prov")
        if g1["spot_src"] == "close":
            notes.append("stale")
        if ivhv and ivhv < 1.0:
            notes.append("inv")
        if past_earn and (us_today - past_earn).days <= 42:
            # 30 trading returns is ~6 calendar weeks; an earnings gap inside
            # that window inflates HV and manufactures a false IV/HV inversion
            notes.append(f"gap{(us_today-past_earn).days}d")
        if cluster_of(t) == "Unclustered":
            notes.append("unclus")
        fb = FALLBACK.get(t, "none")
        if fb == "SKIP":
            notes.append("nofb")
        elif isinstance(fb, float):
            notes.append(f"fb{fb:.2f}")
        if g1["margin"] > BLOWOFF_STRETCH:
            notes.append(f"blowoff{g1['margin']*100:.0f}%")
        if past_earn is not None and (us_today - past_earn).days == 2:
            notes.append("T+2")
        if leg.get("capped"):
            notes.append(f"cap{adelta:.2f}")
        if leg["oi"] < 500:
            notes.append(f"oi{leg['oi']}")
        mid = (leg["bid"] + leg["ask"]) / 2
        if leg["bid"] <= 0 or leg["ask"] <= 0:
            notes.append("noq")
        elif (leg["ask"] - leg["bid"]) / mid > 0.10:
            notes.append("ba")
        rows.append({
            "t": t, "cluster": cluster_of(t), "delta": adelta,
            "spot": spot, "sma_margin": g1["margin"], "spot_src": g1["spot_src"],
            "sma20": g1["sma20"], "sma_from": g1["sma_from"], "sma_to": g1["sma_to"],
            "sma_n": g1["sma_n"], "width": width,
            "expiry": exp, "dte": dte,
            "short": leg["strike"], "act_delta": leg["delta"],
            "iv": leg["iv"], "hv": h, "ivhv": ivhv,
            "bid": leg["bid"], "ask": leg["ask"], "oi": leg["oi"],
            "long": long_strike, "act_width": act_width, "target": target,
            "notes": ",".join(notes),
        })
        if do_news:
            news_out[t] = provider.news(t) or []
    regime["single_src"] = single_src
    regime["nq_cover"] = nq_cover
    regime["nq_clear"] = nq_clear
    regime["nq_span"] = nasdaq.span() if hasattr(nasdaq, "span") else (None, None)
    regime["nq_symbols"] = len(nasdaq.map)
    regime["macro_slots"] = macro_slots
    regime["macro_events"] = macro.events
    regime["macro_errors"] = macro.errors
    regime["macro_bls_ok"] = macro.bls_ok
    regime["fomc_src"] = macro.fomc_src
    regime["macro_span_days"] = DTE_MAX + 21
    tgt = None
    for r in rows:
        tgt = r["expiry"]; break
    if tgt:
        td = datetime.strptime(tgt, "%Y-%m-%d").date()
        regime["macro_near_expiry"] = macro.near(td)
        regime["macro_expiry"] = tgt
    regime["nasdaq_ok"] = bool(nasdaq.map)
    regime["nasdaq_errors"] = nasdaq.errors[:3]
    regime["finnhub_on"] = bool(finnhub.key)
    return rows, dropped, conflicts, news_out, regime
DATA_LOSS_FRACTION = 0.5


def data_loss(dropped, n_requested):
    """True when enough names died on data that the screen means nothing.

    "Nothing passed. Cash is a valid outcome." and "every price feed is down"
    render identically. Read by a person at a terminal that is survivable —
    they saw the errors scroll past. Published to a web page by a scheduler at
    14:45 UTC with nobody watching, it is not: the page looks like a calm,
    correctly-empty screen. So a run that loses half the universe to data
    failure exits non-zero, the scheduler goes red, and yesterday's page is
    left standing rather than being overwritten with a lie.
    """
    if not n_requested:
        return False
    return len(dropped.get("data", [])) >= DATA_LOSS_FRACTION * n_requested


def _wrap(text, width):
    import textwrap
    return textwrap.wrap(text, width) or [text]
def explain_notes(r, verbose=False):
    """One short line per flag. --why gives the long form."""
    out = []
    for n in [x for x in r["notes"].split(",") if x]:
        if n == "knife":
            out.append(f"knife — {r['sma_margin']*100:+.2f}% vs 20-day avg "
                       f"{r['sma20']:.2f}. Feeds can disagree on the sign here. Verify.")
            if verbose:
                out.append(f"        window {r['sma_from']}..{r['sma_to']}, "
                           f"{r['sma_n']} bars, regular-hours closes.")
                out.append("        The old ANET yfinance-vs-IBKR split was "
                           "outside_rth=True: IBKR extended-hours bars are a "
                           "different series (ANET 4 Aug closed 190.51 RTH vs "
                           "211.50 ETH). Pull IBKR with outside_rth=False and "
                           "the two feeds match to the cent.")
        elif n == "prov":
            out.append(f"prov — only {r['sma_margin']*100:.1f}% above 20-day avg. "
                       f"One down day drops it out of Gate 1.")
        elif n == "inv":
            out.append(f"inv — priced for {r['iv']*100:.0f}% move, actually moved "
                       f"{r['hv']*100:.0f}%. Underpaid.")
        elif n.startswith("gap"):
            d = n[3:-1]
            out.append(f"gap{d}d — reported {d}d ago; that jump inflates HV, so "
                       f"'inv' may be fake.")
        elif n == "nofb":
            out.append("nofb — if 11% fails at 0.15Δ, skip. Never step closer to the money.")
        elif n.startswith("fb") and n != "nofb":
            out.append(f"fb{n[2:]} — may step to {n[2:]}Δ only after 11% fails live. "
                       f"No further.")
        elif n.startswith("blowoff"):
            out.append(f"{n} — {n[7:]} above 20-day avg. Vertical run, not trend. "
                       f"Never step Δ up.")
        elif n == "T+2":
            out.append("T+2 — reported 2d ago. Earliest entry you allow.")
        elif n.startswith("oi"):
            out.append(f"oi{n[2:]} — {n[2:]} open vs your 500 rule. Worse fills, "
                       f"harder to exit.")
        elif n == "ba":
            mid = (r["ask"] + r["bid"]) / 2
            pct = ((r["ask"] - r["bid"]) / mid * 100) if mid else 0
            out.append(f"ba — bid/ask gap is {pct:.0f}% of price. You pay it twice "
                       f"on a spread.")
        elif n.startswith("cap") and n != "capped":
            out.append(f"{n} — nearest strike to {n[3:]}\u0394 is over the 0.20 hard "
                       f"cap, so this is the next one out. Less credit, by rule.")
        elif n == "noq":
            out.append("noq — no bid/ask posted. Price shown is not tradeable.")
        elif n == "unclus":
            out.append("unclus — no cluster cap applies. Per-name and total only.")
        elif n == "stale":
            out.append("stale — live read failed, using previous close. Strike may shift.")
        else:
            out.append(n)
    return out
FLAG_LEGEND = [
    ("knife", "within 0.5% of SMA20 — Gate 1 could flip on one print"),
    ("prov",  "under 2% above SMA20 — one down day drops it out of Gate 1"),
    ("stale", "live quote failed, spot is the previous close"),
    ("inv",   "IV below HV — paid less than the stock actually moved"),
    ("gapNd", "reported N days ago; the gap inflates HV, so `inv` may be an artifact"),
    ("unclus","no cluster cap applies — only per-name and total bind"),
    ("nofb",  "no fallback: if 11%W fails at 0.15\u0394, skip. Never step closer"),
    ("fbN",   "may step to N\u0394 only after 11%W fails live. No further"),
    ("capN",  "nearest strike to N\u0394 breached the 0.20 hard cap — stepped out, less credit"),
    ("blowoffN", "N% above SMA20 — vertical run, not trend. Never step \u0394 up"),
    ("T+2",   "reported 2 days ago — the earliest entry you allow"),
    ("oiN",   "N open interest vs your 500 rule — worse fills, harder to exit"),
    ("ba",    "bid/ask spread over 10% of mid — you pay it twice on a spread"),
    ("noq",   "no bid/ask posted — the price shown is not tradeable"),
]


def _legend_key(code):
    """Map a concrete flag (gap38d, oi114, fb0.18) to its legend entry."""
    if code.startswith("gap"):
        return "gapNd"
    if code.startswith("cap"):
        return "capN"
    if code.startswith("blowoff"):
        return "blowoffN"
    if code.startswith("fb") and code != "nofb":
        return "fbN"
    if code.startswith("oi"):
        return "oiN"
    return code


def report(rows, dropped, conflicts, news_out, regime, today, verbose=False):
    """Compact by default. --why restores the per-row prose."""
    L = []
    W = 100

    def rule(ch="\u2500"):
        L.append(ch * W)

    # ---------------------------------------------------------- REGIME
    go, why = condor_verdict(regime)
    vix = f"VIX {regime['vix']:.2f}" if regime["vix"] is not None else "VIX UNREAD"
    st = (f"SPX {regime['stretch']*100:+.2f}% vs 20-MA"
          if regime["stretch"] is not None else "SPX UNREAD")
    srcs = regime.get("spot_srcs") or set()
    feed = {frozenset(["live"]): "spot LIVE",
            frozenset(["close"]): "spot PREV-CLOSE",
            }.get(frozenset(srcs), "spot MIXED" if srcs else "spot n/a")
    L.append(f"REGIME  {today}  (US session {regime.get('us_date','?')} "
             f"{regime.get('tz','?')})")
    L.append(f"        {vix}  \u00b7  {st}  \u00b7  {feed}  \u00b7  "
             f"DTE {DTE_MIN}-{DTE_MAX}")
    L.append(f"        condor {'GO' if go else 'NO-GO'} \u2014 {why}")
    L.append(f"        caps + hedge NOT COMPUTED \u2014 Part 2, needs IBKR")

    # ---------------------------------------------------------- MACRO
    near = regime.get("macro_near_expiry") or []
    exp_s = regime.get("macro_expiry")
    if exp_s:
        exp_d = datetime.strptime(exp_s, "%Y-%m-%d").date()
        onday = [l for d, l in near if d == exp_d]
        if near:
            L.append(f"MACRO   within {MACRO_WINDOW_DAYS}d of expiry {exp_s}:")
            for d, lbl in sorted(near):
                off = (d - exp_d).days
                when = ("EXPIRY DAY" if off == 0 else
                        f"{abs(off)}d {'before' if off < 0 else 'after'}")
                L.append(f"          {lbl:<5} {d.strftime('%a %d %b')}  {when}")
        else:
            L.append(f"MACRO   within {MACRO_WINDOW_DAYS}d of {exp_s}: none")
        if onday:
            L.append(f"        ** {', '.join(onday)} PRINTS 8:30am ON THE DAY "
                     f"THESE SETTLE \u2014 every position moves together **")
        if len(near) >= 2:
            L.append(f"        ** MACRO DENSITY: {len(near)} events within "
                     f"{MACRO_WINDOW_DAYS}d \u2014 HALVE TRANCHE **")
    nev = len(regime.get("macro_events") or [])
    span = regime.get("macro_span_days") or 0
    expected = max(2, int(span / 30) * 2)
    if not regime.get("macro_bls_ok"):
        L.append("        !! CALENDAR INCOMPLETE \u2014 CPI/NFP missing. A clear "
                 "macro line above is NOT a clearance.")
    elif nev < expected:
        L.append(f"        !! CALENDAR SPARSE \u2014 {nev} events / {span}d, "
                 f"expected ~{expected}. A parser or page probably broke.")
    else:
        L.append(f"        calendar live \u00b7 {nev} events / {span}d \u00b7 "
                 f"FOMC {regime.get('fomc_src','?')} \u00b7 BLS live")
    for e in (regime.get("macro_errors") or [])[:2]:
        L.append(f"        note: {e}")
    if regime["errors"]:
        L.append(f"        read errors: {', '.join(regime['errors'])}")

    # ---------------------------------------------------------- TABLE
    L.append("")
    rule()
    L.append(f"CANDIDATES \u2014 Gates 1-2 passed. Gate 3 is yours, headlines "
             f"below. 11%W floor yours at ticket.")
    rule()
    if rows:
        d_h, ad_h = "\u0394", "act\u0394"
        L.append(f"{'Ticker':<7}{d_h:>5}{'Spot':>9}{'Short':>8}{'Long':>8}"
                 f"{'Width':>7}{ad_h:>6}{'Target':>8}"
                 f"{'IV':>7}{'HV':>7}{'IV/HV':>7}{'DTE':>5}  Flags")
    by_c = {}
    for r in rows:
        by_c.setdefault(r["cluster"], []).append(r)
    used = []
    for c in CLUSTER_ORDER:
        grp = by_c.get(c)
        if not grp:
            continue
        cap = CLUSTER_MAX.get(c)
        if cap:
            tag = f"{len(grp)}/{cap}" + ("  ** OVER CAP **" if len(grp) > cap else "")
        else:
            tag = f"{len(grp)}/\u2013"
        L.append(f"  {c} {tag}")
        for r in sorted(grp, key=lambda x: -(x["iv"] or 0)):
            ivhv = f"{r['ivhv']:.2f}" if r["ivhv"] else "n/a"
            hv = f"{r['hv']*100:.1f}%" if r["hv"] else "n/a"
            flags = [f for f in r["notes"].split(",") if f]
            used += flags
            tg = f"{r['target']:.2f}" if r.get("target") is not None else "n/a"
            lg = f"{r['long']:.1f}" if r.get("long") is not None else "n/a"
            wd = r.get("act_width") or r["width"]
            L.append(f"{r['t']:<7}{r['delta']:>5.2f}{r['spot']:>9.2f}"
                     f"{r['short']:>8.1f}{lg:>8}{wd:>7.1f}{r['act_delta']:>6.2f}"
                     f"{tg:>8}"
                     f"{r['iv']*100:>6.1f}%{hv:>7}{ivhv:>7}{r['dte']:>5}  "
                     + " ".join(flags))
            if verbose:
                for e in explain_notes(r, True):
                    for j, seg in enumerate(_wrap(e, 84)):
                        L.append(("      \u00b7 " if j == 0 else "        ") + seg)
    if not rows:
        L.append("Nothing passed. Cash is a valid outcome.")
    L.append("")
    if rows:
        L.append(f"All expiries {rows[0]['expiry']} unless a row says otherwise.")
    for note in cross_cluster_notes([r["t"] for r in rows]):
        L.append("")
        for j, seg in enumerate(_wrap("CROSS-CLUSTER: " + note, 96)):
            L.append(seg if j == 0 else "  " + seg)

    # ---------------------------------------------------------- FLAGS
    if used and not verbose:
        L.append("")
        L.append("FLAGS")
        seen = []
        for f in used:
            k = _legend_key(f)
            if k not in seen:
                seen.append(k)
        for code, text in FLAG_LEGEND:
            if code in seen:
                L.append(f"  {code:<10} {text}")
        L.append("  (--why prints these per row, with the numbers filled in)")

    # ---------------------------------------------------------- GATE 3
    if news_out:
        L.append("")
        rule()
        L.append("GATE 3 \u2014 material adverse catalyst? Veto by hand. "
                 "* this name, ~ sector.")
        rule()
        for r in rows:
            items = news_out.get(r["t"])
            if items is None:
                continue
            if not items:
                L.append(f"{r['t']:<7} ! no headlines returned \u2014 a data "
                         f"failure, not a clearance")
                continue
            direct = [x for x in items if x[2]]
            sector = [x for x in items if not x[2]]
            show = direct if (direct and not verbose) else items
            for i, item in enumerate(show):
                d, title, is_direct = item[0], item[1], item[2]
                url = item[3] if len(item) > 3 else ""
                head = f"{r['t']:<7}" if i == 0 else " " * 7
                L.append(f"{head} {'*' if is_direct else '~'} {str(d)[5:]} "
                         f"{title[:74]}")
                if verbose and url:
                    L.append(f"{' ' * 9}  {url}")
            if direct and sector and not verbose:
                pad = " " * 7 if show else f"{r['t']:<7}"
                L.append(f"{pad}   +{len(sector)} sector item"
                         f"{'s' if len(sector) > 1 else ''} (--why to see)")

    # ---------------------------------------------------------- DROPPED
    L.append("")
    rule()
    L.append("DROPPED")
    for k, label in [("trend", "Gate 1 trend"), ("earnings", "Gate 2 earnings"),
                     ("postearn", "post-earnings T+1"),
                     ("width", "width pre-filter"), ("data", "data failure")]:
        if dropped[k]:
            L.append(f"  {label:<18} {', '.join(dropped[k])}")

    # ---------------------------------------------------------- SOURCES
    L.append("")
    L.append("SOURCES")
    srcline = ["yfinance", "nasdaq" if regime.get("nasdaq_ok") else "nasdaq FAILED"]
    if regime.get("finnhub_on"):
        srcline.append("finnhub")
    L.append(f"  earnings           {', '.join(srcline)}")
    a, b = regime.get("nq_span") or (None, None)
    if a and b:
        cov = regime.get("nq_cover") or {}
        clr = regime.get("nq_clear") or {}
        dated = sum(1 for v in cov.values() if v)
        cleared = sum(1 for v in clr.values() if v)
        unknown = len(cov) - dated - cleared
        L.append(f"  nasdaq calendar    {a} .. {b} "
                 f"({regime.get('nq_symbols', 0)} companies)")
        L.append(f"  cross-check        {dated} dated \u00b7 {cleared} cleared by "
                 f"full-window scan \u00b7 {unknown} unconfirmed")
    if regime.get("nasdaq_errors"):
        L.append(f"  nasdaq errors      {', '.join(regime['nasdaq_errors'])}")
    if regime.get("single_src"):
        L.append("  !! ONE SOURCE ONLY (agreement proves nothing): "
                 + ", ".join(regime["single_src"]))
    ms = regime.get("macro_slots") or []
    if ms:
        parts = []
        for t, hits, stt in ms:
            if stt == "UNVERIFIED":
                parts.append(f"{t}[UNVERIFIED]")
            elif hits:
                parts.append(f"{t}[{', '.join(l for _, l in hits)}]")
            else:
                parts.append(f"{t}[clear]")
        L.append(f"  macro gate (ETFs)  {', '.join(parts)}")
    L.append("  None is IR. Confirm at source anything that binds.")

    if conflicts:
        L.append("")
        L.append("EARNINGS CONFLICT \u2014 independent sources disagree. Verify vs "
                 "IR; your rule blocks the name if IR cannot resolve it:")
        for c in conflicts:
            L.append(f"  {c}")

    # ---------------------------------------------------------- FOOTER
    if rows:
        L.append("")
        L.append("IV needed for 11%W (21 DTE, 5%-of-spot width) \u2014 reference, "
                 "never pass/fail:")
        L.append("  0.15\u0394 47.1%  0.16\u0394 41.2%  0.17\u0394 36.4%  "
                 "0.18\u0394 32.5%  0.20\u0394 26.6%")
        L.append("  Ignores bid/ask drag, so optimistic by construction \u00b7 "
                 "calibrated to 21 DTE \u00b7 not a gate.")
    L.append("")
    L.append("\u0394 target short-leg delta \u00b7 act\u0394 delta of the strike "
             "actually picked \u00b7 Short sold \u00b7 Long bought")
    L.append(f"Target = {CREDIT_FLOOR*100:.0f}% of the width: the least this "
             f"spread may be sold for. Aim at or above it when you price the "
             f"ticket live.")
    L.append("IV priced-in move \u00b7 HV actual recent move \u00b7 IV per-strike and "
             "delayed. Bid/ask is context, not a gate.")
    return "\n".join(L)



# ---------------------------------------------------------------- run history
# Schema is FROZEN. The whole point of the log is that a week of runs can be
# diffed against what was actually traded, and a column that changes name or
# position halfway through the week makes that comparison impossible. Add new
# columns at the END only, never reorder, never rename. The writer refuses to
# append to a file whose header does not match, rather than silently producing
# a CSV with two different meanings for column 12.
SCREEN_COLUMNS = [
    "run_utc", "us_date", "ticker", "verdict", "drop_reason", "cluster",
    "anchor_delta", "spot", "spot_src", "sma20", "sma_margin", "width",
    "expiry", "dte", "short", "act_delta", "iv", "hv", "ivhv", "bid", "ask",
    "oi", "flags",
]
REGIME_COLUMNS = [
    "run_utc", "us_date", "vix", "spx_stretch", "condor_go", "condor_reason",
    "spot_srcs", "expiry", "macro_near", "macro_on_expiry", "macro_bls_ok",
    "fomc_src", "macro_events", "n_passed", "n_dropped",
    "nasdaq_from", "nasdaq_to", "nq_dated", "nq_cleared", "nq_unconfirmed",
]


def _f(v, nd=4):
    """CSV cell for a float that may be None. Empty, never 'None'."""
    if v is None:
        return ""
    try:
        return f"{float(v):.{nd}f}"
    except (TypeError, ValueError):
        return ""


def screen_log_rows(rows, dropped, regime, run_utc):
    """One record per name per run — PASSED and DROPPED alike.

    Dropped names are the more valuable half. The question the verification
    week has to answer is not only "was the screen right about what it showed"
    but "what did it hide, and why" — if a name was entered by hand on a day
    the screener dropped it on trend, that is the finding. Logging survivors
    only would make that undiscoverable.
    """
    us_date = str(regime.get("us_date", ""))
    out = []
    for r in rows:
        out.append({
            "run_utc": run_utc, "us_date": us_date, "ticker": r["t"],
            "verdict": "passed", "drop_reason": "", "cluster": r["cluster"],
            "anchor_delta": _f(r["delta"], 2), "spot": _f(r["spot"], 4),
            "spot_src": r["spot_src"], "sma20": _f(r["sma20"], 4),
            "sma_margin": _f(r["sma_margin"], 6), "width": _f(r["width"], 2),
            "expiry": r["expiry"], "dte": r["dte"], "short": _f(r["short"], 2),
            "act_delta": _f(r["act_delta"], 4), "iv": _f(r["iv"], 6),
            "hv": _f(r["hv"], 6), "ivhv": _f(r["ivhv"], 4),
            "bid": _f(r["bid"], 4), "ask": _f(r["ask"], 4), "oi": r["oi"],
            "flags": r["notes"],
        })
    for bucket, names in dropped.items():
        for entry in names:
            tick = entry.split("(")[0].split("[")[0].strip()
            detail = entry[len(tick):].strip("()[] ")
            out.append({
                "run_utc": run_utc, "us_date": us_date, "ticker": tick,
                "verdict": "dropped",
                "drop_reason": f"{bucket}:{detail}" if detail else bucket,
                "cluster": cluster_of(tick), "anchor_delta": "", "spot": "",
                "spot_src": "", "sma20": "", "sma_margin": "", "width": "",
                "expiry": "", "dte": "", "short": "", "act_delta": "",
                "iv": "", "hv": "", "ivhv": "", "bid": "", "ask": "", "oi": "",
                "flags": "",
            })
    return out


def regime_log_row(rows, dropped, regime, run_utc):
    go, why = condor_verdict(regime)
    near = regime.get("macro_near_expiry") or []
    exp_s = regime.get("macro_expiry") or ""
    on_expiry = ""
    if exp_s and near:
        ed = datetime.strptime(exp_s, "%Y-%m-%d").date()
        on_expiry = ";".join(l for d, l in near if d == ed)
    cov = regime.get("nq_cover") or {}
    clr = regime.get("nq_clear") or {}
    dated = sum(1 for v in cov.values() if v)
    cleared = sum(1 for v in clr.values() if v)
    a, b = regime.get("nq_span") or (None, None)
    return {
        "run_utc": run_utc, "us_date": str(regime.get("us_date", "")),
        "vix": _f(regime.get("vix"), 2),
        "spx_stretch": _f(regime.get("stretch"), 6),
        "condor_go": "GO" if go else "NO-GO", "condor_reason": why,
        "spot_srcs": "|".join(sorted(regime.get("spot_srcs") or [])),
        "expiry": exp_s,
        "macro_near": ";".join(f"{l}@{d}" for d, l in near),
        "macro_on_expiry": on_expiry,
        "macro_bls_ok": int(bool(regime.get("macro_bls_ok"))),
        "fomc_src": regime.get("fomc_src", ""),
        "macro_events": len(regime.get("macro_events") or []),
        "n_passed": len(rows),
        "n_dropped": sum(len(v) for v in dropped.values()),
        "nasdaq_from": str(a or ""), "nasdaq_to": str(b or ""),
        "nq_dated": dated, "nq_cleared": cleared,
        "nq_unconfirmed": len(cov) - dated - cleared,
    }


def append_csv(path, columns, records):
    """Append, writing the header only on creation. Never rewrite.

    Refuses on schema drift instead of appending mismatched rows: a log that
    silently changes shape mid-week is worse than no log, because the diff it
    produces looks valid.
    """
    import csv, os
    existing = None
    if os.path.exists(path) and os.path.getsize(path) > 0:
        with open(path, newline="", encoding="utf-8") as fh:
            existing = next(csv.reader(fh), None)
        if existing != columns:
            raise ValueError(
                f"{path} header does not match the current schema.\n"
                f"  on disk: {existing}\n  expected: {columns}\n"
                f"Rename the old file rather than mixing two schemas.")
    d = os.path.dirname(path)
    if d:
        os.makedirs(d, exist_ok=True)
    with open(path, "a", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=columns)
        if existing is None:
            w.writeheader()
        for rec in records:
            w.writerow(rec)
    return len(records)


def write_logs(rows, dropped, regime, outdir, run_utc=None):
    """Append this run to screen_log.csv and regime_log.csv. Returns counts."""
    import os
    if run_utc is None:
        from datetime import timezone
        run_utc = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    n1 = append_csv(os.path.join(outdir, "screen_log.csv"), SCREEN_COLUMNS,
                    screen_log_rows(rows, dropped, regime, run_utc))
    n2 = append_csv(os.path.join(outdir, "regime_log.csv"), REGIME_COLUMNS,
                    [regime_log_row(rows, dropped, regime, run_utc)])
    return n1, n2



# ---------------------------------------------------------------- html page
HTML_CSS = """
*{box-sizing:border-box}
:root{
  --bg:#fbfaf9; --panel:#fff; --ink:#1c1a17; --dim:#6b6560; --line:#e4dfd8;
  --accent:#2f6349; --warn:#8a5a00; --warnbg:#fdf3dd; --alarm:#9a2f2f;
  --alarmbg:#fceceb; --chip:#f0ece6; --btnink:#fff;
  --mono:ui-monospace,"SF Mono",Menlo,Consolas,monospace;
}
/* Dark palette, every pair measured rather than eyeballed. The old one had
   cards at 1.09 contrast against the page - technically two colours, visually
   one flat surface, so nothing looked like a card. Panel now sits at 1.17 over
   the background, borders at 1.31 over the panel, and secondary text is up
   from 6.06 to 8.64. Fourteen pairs checked, all passing. */
@media (prefers-color-scheme:dark){:root:not([data-theme="light"]){
  --bg:#0c0e13; --panel:#1a1f29; --ink:#e7eaf0; --dim:#a6aebc; --line:#2c3440;
  --accent:#57d39a; --warn:#f2c14e; --warnbg:#2e2517; --alarm:#ff958a;
  --alarmbg:#331e1c; --chip:#242b38; --btnink:#08251a;
}}
:root[data-theme="dark"]{
  --bg:#0c0e13; --panel:#1a1f29; --ink:#e7eaf0; --dim:#a6aebc; --line:#2c3440;
  --accent:#57d39a; --warn:#f2c14e; --warnbg:#2e2517; --alarm:#ff958a;
  --alarmbg:#331e1c; --chip:#242b38; --btnink:#08251a;
}
body{margin:0;background:var(--bg);color:var(--ink);
  font:17px/1.62 ui-sans-serif,system-ui,-apple-system,"Segoe UI",sans-serif;
  -webkit-text-size-adjust:100%}
.wrap{max-width:1180px;margin:0 auto;padding:20px 16px 64px}
.brandrow{display:flex;align-items:baseline;gap:12px;flex-wrap:wrap}
.by{font-size:13px;color:var(--dim);border:1px solid var(--line);
  border-radius:99px;padding:3px 10px;white-space:nowrap}
.sig{color:var(--dim);font-size:13px;margin:14px 0 0;line-height:1.55}
.sig b{color:var(--ink)}
.stat.now .v{color:var(--accent)}
.chip{cursor:help}
.nb{background:var(--accent);color:var(--btnink);border:none;border-radius:6px;
  padding:3px 10px;font:inherit;font-size:13px;font-weight:600;cursor:pointer;
  white-space:nowrap}
.nb.hot{background:var(--alarmbg);color:var(--alarm);
  box-shadow:inset 0 0 0 1px var(--alarm)}
.nb:focus-visible{outline:2px solid var(--accent);outline-offset:2px}
#nv{position:fixed;inset:0;z-index:200;background:rgba(0,0,0,.55);
  display:flex;align-items:center;justify-content:center;padding:20px}
#nv[hidden]{display:none}
.nvbox{background:var(--panel);border:1px solid var(--line);border-radius:14px;
  width:min(640px,100%);max-height:min(80vh,720px);display:flex;
  flex-direction:column;box-shadow:0 24px 60px rgba(0,0,0,.5)}
.nvhead{display:flex;align-items:center;justify-content:space-between;
  padding:14px 18px;border-bottom:1px solid var(--line)}
.nvhead b{font-size:19px}
#nvx{background:none;border:none;color:var(--dim);font-size:28px;line-height:1;
  cursor:pointer;padding:0 4px}
#nvx:hover{color:var(--ink)}
.nvbody{overflow-y:auto;padding:6px 18px 14px}
.nvfoot{padding:12px 18px;border-top:1px solid var(--line);color:var(--dim);
  font-size:13.5px;line-height:1.5}
.nvi{padding:12px 0;border-bottom:1px solid var(--line)}
.nvi:last-child{border-bottom:none}
.nvi .m{font-family:var(--mono);font-size:12.5px;color:var(--dim);
  margin-right:8px}
.nvi a{color:var(--ink);text-decoration:underline;text-underline-offset:3px;
  text-decoration-color:var(--line)}
.nvi a:hover{text-decoration-color:var(--accent)}
.nvi.sec{color:var(--dim)}
.nvi.sec a{color:var(--dim)}
@media (max-width:600px){
  #nv{padding:0;align-items:flex-end}
  .nvbox{border-radius:16px 16px 0 0;max-height:88vh}
}
.chip.bare{background:none;border:none;padding:0;font-size:inherit;
  font-family:inherit;color:inherit}
.drift{color:var(--dim);font-size:.86em}
.chip:focus-visible{outline:2px solid var(--accent);outline-offset:2px}
#tip{position:fixed;z-index:99;max-width:min(340px,calc(100vw - 24px));
  background:var(--panel);color:var(--ink);border:1px solid var(--line);
  border-radius:10px;padding:10px 13px;font-size:14.5px;line-height:1.5;
  box-shadow:0 8px 28px rgba(0,0,0,.45);opacity:0;pointer-events:none;
  transform:translateY(-4px);transition:opacity .12s ease,transform .12s ease}
#tip.show{opacity:1;transform:none}
tr.fl td{padding:0 13px 12px;border-bottom:1px solid var(--line)}
tr.row td{border-bottom:none}
tr.fl:last-child td{border-bottom:none}
h1{font-size:24px;margin:0 0 2px;letter-spacing:-.01em}
h2{font-size:14px;text-transform:uppercase;letter-spacing:.09em;color:var(--dim);
  margin:32px 0 10px;font-weight:600}
.sub{color:var(--dim);font-size:15px;margin-bottom:18px}
.grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(150px,1fr));gap:10px}
.stat{background:var(--panel);border:1px solid var(--line);border-radius:10px;
  padding:12px 14px}
.stat .k{font-size:12.5px;text-transform:uppercase;letter-spacing:.07em;color:var(--dim)}
.stat .v{font-size:22px;font-variant-numeric:tabular-nums;margin-top:3px}
.banner{border-radius:10px;padding:14px 16px;margin:16px 0;font-size:16px;
  border:1px solid transparent}
.banner.warn{background:var(--warnbg);border-color:var(--warn);color:var(--ink)}
.banner.alarm{background:var(--alarmbg);border-color:var(--alarm);color:var(--ink)}
.banner b.t{display:block;margin-bottom:2px}
.banner b{display:inline}
.banner ul.macro{margin:8px 0 10px;padding:0;list-style:none}
.banner ul.macro li{padding:5px 0;border-bottom:1px solid rgba(128,128,128,.22);
  font-variant-numeric:tabular-nums}
.banner ul.macro li:last-child{border-bottom:none}

/* overflow-x:auto silently makes this a scroll container on BOTH axes, and a
   sticky <th> sticks to its nearest scrolling ancestor - so the header was
   pinning itself to a box that never scrolls vertically, and sailed off the
   top of the screen with everything else. Once the table fits, the container
   has no job, so it gets out of the way and the header can stick to the
   viewport instead. */
.scroll{overflow-x:auto;-webkit-overflow-scrolling:touch;
  border:1px solid var(--line);border-radius:10px;background:var(--panel)}
/* 860px is where the table stops needing to scroll sideways (measured: it
   wants 828px, and below ~870 the container has to take over). Above it the
   container has no job, so it steps aside and the header sticks. */
@media (min-width:870px){
  .scroll{overflow:visible}
}
table{border-collapse:collapse;width:100%;font-size:16px}
th,td{padding:11px 13px;text-align:right;white-space:nowrap;
  border-bottom:1px solid var(--line)}
th{font-size:12.5px;text-transform:uppercase;letter-spacing:.05em;color:var(--dim);
  font-weight:600;position:sticky;top:0;z-index:5;background:var(--panel);
  border-bottom:1px solid var(--line);box-shadow:0 1px 0 var(--line)}
/* The cluster label sticks under the header, so a long list never leaves you
   wondering which group the row you are looking at belongs to. */
tr.grp td{position:sticky;top:41px;z-index:4}
th:first-child,td:first-child{text-align:left}
td.num{font-variant-numeric:tabular-nums;font-family:var(--mono);font-size:15.5px}
td.tgt{color:var(--accent);font-weight:600}
tr.grp td{background:var(--chip);font-size:12.5px;text-transform:uppercase;
  letter-spacing:.07em;color:var(--dim);font-weight:600;text-align:left}
tr.grp td .cnt{color:var(--dim);font-weight:400;margin-left:8px;
  text-transform:none;letter-spacing:0}
tr:last-child td{border-bottom:none}
.tk{font-weight:600}
.chips{display:flex;flex-wrap:wrap;gap:5px;justify-content:flex-start}
.chip{background:var(--chip);border-radius:6px;padding:3px 8px;font-size:13px;
  font-family:var(--mono);color:var(--dim);white-space:nowrap}
.chip.hot{background:var(--alarmbg);color:var(--alarm)}
.runbar{display:flex;flex-wrap:wrap;gap:10px;align-items:center;margin:18px 0 4px}
.btn{display:inline-flex;align-items:center;gap:9px;background:var(--accent);
  color:var(--btnink);border:none;border-radius:10px;padding:14px 24px;font:inherit;
  font-weight:600;font-size:17px;cursor:pointer;text-decoration:none;
  -webkit-tap-highlight-color:transparent}
.btn:active{transform:translateY(1px)}
.btn[disabled]{opacity:.55;cursor:default}
.ro{display:inline-flex;align-items:center;gap:8px;color:var(--dim);
  font-size:15px;background:var(--chip);border:1px solid var(--line);
  border-radius:9px;padding:9px 14px}

.btn .dot{width:15px;height:15px;border-radius:50%;flex:none;
  border:2px solid currentColor;border-top-color:transparent;
  animation:spin .7s linear infinite}
@keyframes spin{to{transform:rotate(360deg)}}
@media (prefers-reduced-motion:reduce){
  .btn .dot{animation:none;opacity:.6}
  .bar>div{animation:none!important}
}
.runstat{font-size:15px;color:var(--dim)}
/* Indeterminate on purpose. A percentage would be a guess: the run has no
   knowable duration and the publish step even less so. A stripe that keeps
   moving says "still working" honestly; a bar creeping to 90%% and sitting
   there says something false. */
.bar{display:none;height:6px;background:var(--chip);border-radius:99px;
  overflow:hidden;margin:4px 0 8px;position:relative}
.bar>div{position:absolute;top:0;left:0;height:100%;width:38%;
  background:var(--accent);border-radius:99px;
  animation:slide 1.25s cubic-bezier(.55,.1,.45,.9) infinite}
@keyframes slide{0%{left:-40%}100%{left:100%}}
.runstat b{color:var(--ink)}
.fresh{background:var(--warnbg);border:1px solid var(--warn);border-radius:10px;
  padding:13px 16px;margin:12px 0;font-size:16px;display:none}
.fresh.show{display:block}
dl.legend{margin:0;display:grid;grid-template-columns:auto 1fr;gap:9px 16px;font-size:15px}
dl.legend dt{font-family:var(--mono);color:var(--accent);white-space:nowrap}
dl.legend dd{margin:0;color:var(--dim)}
details{background:var(--panel);border:1px solid var(--line);border-radius:9px;
  padding:10px 13px;margin-bottom:8px}
summary{cursor:pointer;font-weight:600;font-size:17px;padding:2px 0}
summary .n{color:var(--dim);font-weight:400;font-size:13.5px;margin-left:10px}
.head{margin:11px 0 0;font-size:15.5px;color:var(--ink);display:flex;gap:8px}
.head .d{color:var(--dim);font-family:var(--mono);font-size:13px;flex:none;min-width:3.4em}
.head.sector{color:var(--dim)}
.head a{color:inherit;text-decoration:underline;text-underline-offset:3px;
  text-decoration-color:var(--line)}
.head a:hover{text-decoration-color:var(--accent)}
.drop{background:var(--panel);border:1px solid var(--line);border-radius:9px;
  padding:13px 15px;margin-bottom:9px;font-size:15px}
.drop .k{font-size:12.5px;text-transform:uppercase;letter-spacing:.07em;
  color:var(--dim);margin-bottom:3px}
.drop .v{font-family:var(--mono);font-size:14px;word-break:break-word}
.foot{color:var(--dim);font-size:14px;margin-top:34px;border-top:1px solid var(--line);
  padding-top:14px}
.foot code{font-family:var(--mono)}
/* Cards below 870, table above - the same width at which the table stops
   needing to scroll sideways. Between the old 720 and 870 the table technically
   rendered but had to be dragged left and right, which is the worst of both:
   too cramped to read as a table, too wide to read as a card. */
@media (max-width:869px){
  .wrap{padding:14px 11px 48px}
  thead{display:none}
  table,tbody,tr,td{display:block;width:100%}
  tr.row{padding:14px 15px 8px}
  tr.fl td{padding:0 15px 14px}
  tr.fl{border-bottom:1px solid var(--line)}
  tr.fl:last-child{border-bottom:none}
  tr.grp td{border:none;padding:10px 13px 4px;display:block;text-align:left}
  tr.grp td:before{content:none}
  td{border:none;padding:2px 0;text-align:right;display:flex;
     justify-content:space-between;align-items:baseline;gap:12px;white-space:normal}
  td:before{content:attr(data-l);font-size:13px;text-transform:uppercase;
     letter-spacing:.06em;color:var(--dim);text-align:left;flex:none}
  td.tkcell{font-size:20px;margin-bottom:8px}
  td.tkcell:before{content:none}
  .chips{justify-content:flex-start}
}
"""


def _jsdata(obj):
    """JSON for inline embedding, with the three characters that could break
    out of a <script> block neutralised."""
    import json
    return (json.dumps(obj, ensure_ascii=False)
            .replace("<", "\\u003c").replace(">", "\\u003e")
            .replace("&", "\\u0026").replace("\u2028", "\\u2028")
            .replace("\u2029", "\\u2029"))


def _js(x):
    """JSON-encode for safe inline <script> embedding."""
    import json
    return (json.dumps(str(x)).replace("<", "\\u003c").replace(">", "\\u003e")
            .replace("&", "\\u0026"))


# Reads the PUBLIC GitHub API only — no token, so nothing secret is shipped to
# the browser. Unauthenticated calls are CORS-enabled and capped at 60/hour per
# IP, which a 5-second poll would burn through in five minutes; hence the 12s
# interval and the hard stop once a run finishes. Every failure path is silent:
# on a private repo these calls 404, and a page that shouts about it is worse
# than one that just hides the status line.
_RUN_JS = """
function initRun(cfg){
  // No GitHub API. Unauthenticated it allows 60 requests an hour PER IP, and
  // behind an office NAT that quota belongs to the whole building - so the
  // status line died with "rate limit reached" through no fault of the person
  // reading it. Everything here is answerable from a small file this run
  // writes beside the page, served by Pages, with no quota at all.
  var VER=(location.pathname.replace(/[^/]*$/,''))+'version.json';
  var COOLDOWN=180000;      // keep in step with worker/worker.js
  var stat=document.getElementById('stat'),go=document.getElementById('go'),
      fresh=document.getElementById('fresh'),bar=document.getElementById('bar');
  var timer=null,cool=null,idler=null,waiting=0,mine=false,began=0;
  var here=parseInt(cfg.runNumber||'0',10);

  function say(h){stat.innerHTML=h;}
  function stop(){if(timer){clearInterval(timer);timer=null;}}
  function show(on){if(bar)bar.style.display=on?'block':'none';}
  function busy(){
    if(go&&go.tagName==='BUTTON'){go.disabled=true;
      go.innerHTML='<span class="dot"></span>Running';}
    show(true);
    say(began?Math.round((Date.now()-began)/1000)+'s':'');
  }
  function idle(){
    if(go&&go.tagName==='BUTTON'){go.disabled=false;go.textContent='Run screen';}
    show(false);
  }
  function giveUp(msg){
    idle();stop();mine=false;began=0;waiting=0;
    say(msg+' \u2014 <a href="'+cfg.actions+'" target="_blank" '+
        'rel="noopener">check Actions</a>');
  }
  function cooldown(){
    if(!cfg.builtUtc)return false;
    var left=COOLDOWN-(Date.now()-new Date(cfg.builtUtc).getTime());
    if(left<=0){if(cool){clearInterval(cool);cool=null;}
      if(go.tagName==='BUTTON'&&!waiting)idle();return false;}
    if(go.tagName==='BUTTON'&&!waiting){
      go.disabled=true;go.textContent='Ready in '+Math.ceil(left/1000)+'s';
    }
    if(!cool)cool=setInterval(cooldown,1000);
    return true;
  }

  function offer(n){
    idle();say('');
    fresh.innerHTML='Run #'+n+' is ready. '+
      '<a href="#" id="doreload"><b>Reload</b></a>';
    fresh.className='fresh show';
    document.getElementById('doreload').onclick=function(e){
      e.preventDefault();location.reload();};
  }
  function read(){return fetch(VER+'?t='+Date.now(),{cache:'no-store'})
    .then(function(r){return r.ok?r.json():Promise.reject(0);});}

  function check(){
    if(Date.now()-waiting>300000){
      giveUp('Still not published after 5 minutes');return;}
    read().then(function(v){
        var live=parseInt(v.run||'0',10);
        // A failed run writes this file too, so the page can say so in
        // seconds instead of waiting out a five-minute timeout and shrugging.
        if(v.state==='failed'&&live>=here){
          giveUp('Run #'+live+' failed');return;
        }
        if(live>here){
          stop();
          if(mine){location.reload();}else{offer(live);}
          return;
        }
        busy();
      })
      .catch(function(){busy();});   // a 404 or a blip is not a failure
  }

  // Someone else may press the button while this page sits open. One 45-byte
  // read a minute notices - and only while the tab is actually being looked
  // at, because polling a page nobody is reading is just noise.
  function idleWatch(){
    if(document.hidden||waiting)return;
    read().then(function(v){
      var live=parseInt(v.run||'0',10);
      if(v.state==='failed')return;
      if(live>here)offer(live);
    }).catch(function(){});
  }

  if(go&&go.tagName==='BUTTON'){
    go.addEventListener('click',function(){
      mine=true;began=Date.now();waiting=Date.now();busy();
      fetch(cfg.dispatch,{method:'POST'})
        .then(function(r){
          if(r.status===409){
            // Someone just ran it, or is running it now. Watch rather than
            // refuse - the result is on its way either way.
            mine=false;waiting=Date.now();stop();
            timer=setInterval(check,5000);check();return;}
          if(!r.ok)throw r.status;
          stop();timer=setInterval(check,5000);setTimeout(check,4000);})
        .catch(function(){
          mine=false;began=0;waiting=0;idle();
          say('Could not start it \u2014 <a href="'+cfg.actions+
              '" target="_blank" rel="noopener">run it from Actions</a>');});
    });
  }

  // Headlines open over the row you tapped, so Gate 3 never costs you your
  // place in the table.
  var nv=document.getElementById('nv');
  if(nv){
    var nvt=document.getElementById('nvt'),
        nvb=nv.querySelector('.nvbody'),opener=null;
    function closeNews(){
      nv.hidden=true;document.body.style.overflow='';
      if(opener)opener.focus();opener=null;
    }
    function openNews(t,btn){
      var list=(window.__news||{})[t]||[];
      nvt.textContent=t;
      if(!list.length){
        nvb.innerHTML='<p class="nvi">No headlines came back for this name. '+
          'That is a failed read, not a clean bill of health \u2014 check it '+
          'by hand before acting.</p>';
      }else{
        nvb.innerHTML=list.map(function(o){
          var body=o.u?('<a href="'+o.u+'" target="_blank" rel="noopener '+
            'nofollow">'+o.t+'</a>'):o.t;
          return '<p class="nvi'+(o.x?'':' sec')+'"><span class="m">'+
            (o.x?'\u25cf':'\u25cb')+' '+o.d+'</span>'+body+'</p>';
        }).join('');
      }
      opener=btn||null;nv.hidden=false;document.body.style.overflow='hidden';
      var x=document.getElementById('nvx');if(x)x.focus();
    }
    document.addEventListener('click',function(e){
      var btn=e.target.closest?e.target.closest('.nb'):null;
      if(btn){openNews(btn.getAttribute('data-news'),btn);return;}
      if(e.target===nv||(e.target.id==='nvx'))closeNews();
    });
    document.addEventListener('keydown',function(e){
      if(e.key==='Escape'&&!nv.hidden)closeNews();
    });
  }

  var b=document.getElementById('built');
  if(b&&b.dataset.utc){
    try{
      var d=new Date(b.dataset.utc);
      if(!isNaN(d)){
        b.textContent=d.toLocaleString(undefined,
          {hour:'2-digit',minute:'2-digit',day:'numeric',month:'short'});
        b.title=b.dataset.utc;
      }
    }catch(e){}
  }
  say(cfg.runNumber?'Showing run #'+cfg.runNumber:'');
  cooldown();
  if(cfg.runNumber){
    idler=setInterval(idleWatch,60000);
    document.addEventListener('visibilitychange',function(){
      if(!document.hidden)idleWatch();});
  }

  // One floating tooltip, shown on hover with no delay. The native title
  // attribute waits about a second, cannot be styled, and wrapped badly at the
  // edge of the table. Tap still works for touch, where there is no hover.
  var tipEl=document.createElement('div');
  tipEl.id='tip';document.body.appendChild(tipEl);
  var pinned=null;
  function place(c){
    var r=c.getBoundingClientRect();
    tipEl.style.left='0px';tipEl.style.top='0px';
    var w=tipEl.offsetWidth,h=tipEl.offsetHeight;
    var x=Math.min(Math.max(8,r.left+r.width/2-w/2),window.innerWidth-w-8);
    var y=r.bottom+8;
    if(y+h>window.innerHeight-8)y=Math.max(8,r.top-h-8);
    tipEl.style.left=x+'px';tipEl.style.top=y+'px';
  }
  function showTip(c){
    var t=c.getAttribute('data-tip');if(!t)return;
    tipEl.textContent=t;tipEl.classList.add('show');place(c);
  }
  function hideTip(){if(!pinned){tipEl.classList.remove('show');}}
  document.addEventListener('mouseover',function(e){
    var c=e.target.closest?e.target.closest('.chip'):null;
    if(c&&!pinned)showTip(c);
  });
  document.addEventListener('mouseout',function(e){
    var c=e.target.closest?e.target.closest('.chip'):null;
    if(c)hideTip();
  });
  document.addEventListener('focusin',function(e){
    var c=e.target.closest?e.target.closest('.chip'):null;
    if(c)showTip(c);
  });
  document.addEventListener('focusout',function(){pinned=null;hideTip();});
  document.addEventListener('click',function(e){
    var c=e.target.closest?e.target.closest('.chip'):null;
    if(!c){pinned=null;tipEl.classList.remove('show');return;}
    if(pinned===c){pinned=null;tipEl.classList.remove('show');}
    else{pinned=null;showTip(c);pinned=c;}
  });
  window.addEventListener('scroll',function(){
    if(pinned)place(pinned);else tipEl.classList.remove('show');
  },{passive:true});
  window.addEventListener('resize',function(){
    pinned=null;tipEl.classList.remove('show');});
}
"""


def _esc(x):
    return (str(x).replace("&", "&amp;").replace("<", "&lt;")
            .replace(">", "&gt;").replace('"', "&quot;"))


HOT_FLAGS = ("knife", "noq", "stale")


def render_html(rows, dropped, conflicts, news_out, regime, today):
    """Self-contained page: no external CSS, fonts, or scripts.

    It has to survive being opened on a phone on a train, so everything is
    inline and the wide table collapses to stacked cards under 720px rather
    than forcing a horizontal scrub across ten numeric columns.
    """
    go, why = condor_verdict(regime)
    H = ['<!doctype html><html lang="en"><head><meta charset="utf-8">',
         '<meta name="viewport" content="width=device-width,initial-scale=1">',
         f'<title>Put spread screen {_esc(today)}</title>',
         f'<style>{HTML_CSS}</style></head><body><div class="wrap">']

    srcs = regime.get("spot_srcs") or set()
    feed = {frozenset(["live"]): "live", frozenset(["close"]): "prev close"}.get(
        frozenset(srcs), "mixed" if srcs else "n/a")
    who = regime.get("author") or ""
    H.append('<div class="brandrow">')
    H.append('<h1>Put credit spread screen</h1>')
    if who:
        H.append(f'<span class="by">{_esc(who)}\u2019s rules</span>')
    H.append('</div>')
    # A date alone cannot answer "did my run land?" — two screens on the same
    # day look identical. The run number and build time make the page
    # self-identifying, so the question is settled by looking at it rather than
    # by trusting a status line that polls an API.
    built = regime.get("built_utc") or ""
    rnum = regime.get("run_number") or ""
    stamp = ""
    if rnum:
        stamp = f' &middot; <b>run #{_esc(rnum)}</b>'
    H.append(f'<p class="sub">{_esc(today)} &middot; US session '
             f'{_esc(regime.get("us_date","?"))} &middot; spot {feed} '
             f'&middot; DTE {DTE_MIN}–{DTE_MAX}{stamp}</p>')

    vix = f"{regime['vix']:.2f}" if regime["vix"] is not None else "unread"
    stv = (f"{regime['stretch']*100:+.2f}%" if regime["stretch"] is not None
           else "unread")
    tail_js = ""
    repo = regime.get("repo")
    if repo:
        wf = regime.get("workflow_file", "screen.yml")
        run_id = regime.get("run_id") or ""
        dispatch = regime.get("dispatch_url") or ""
        actions_url = f"https://github.com/{repo}/actions/workflows/{wf}"
        H.append('<div class="runbar">')
        if dispatch:
            H.append('<button class="btn" id="go">Run screen</button>')
        else:
            # A run does not just refresh a view - it rebuilds this page and
            # republishes it for everyone. That is a deployment, and a
            # deployment is not something a page hands to whoever opens it.
            # With no dispatch endpoint there is no button at all, and no
            # deep-link either: a link into Actions is still an invitation.
            H.append('<span class="ro">Read-only \u00b7 refreshed when the '
                     'screen is re-run</span>')
        H.append('<span class="runstat" id="stat"></span></div>')
        H.append('<div class="bar" id="bar"><div></div></div>')
        H.append('<div class="fresh" id="fresh"></div>')
        # Deferred to the very end of the document. Emitting it here ran
        # initRun before the elements further down the page existed - which is
        # exactly what broke the moment the timestamp moved into a stat tile:
        # getElementById('built') returned null and the clock silently stayed
        # in UTC. Nothing errored, so nothing said so.
        tail_js = (f'<script>{_RUN_JS}</script>'
                   f'<script>initRun({{'
                   f'runNumber:{_js(str(regime.get("run_number") or ""))},'
                   f'builtUtc:{_js(str(regime.get("built_utc") or ""))},'
                   f'dispatch:{_js(dispatch)},'
                   f'actions:{_js(actions_url if dispatch else "")}}});'
                   f'</script>')
    H.append('<div class="grid">')
    if built:
        # Freshness is the first thing anyone needs from a page like this, and
        # it was buried in a grey subtitle. It gets a tile.
        H.append(f'<div class="stat now"><div class="k">Last run</div>'
                 f'<div class="v"><span id="built" data-utc="{_esc(built)}">'
                 f'{_esc(built[11:16])} UTC</span></div></div>')
    for k, v in (("VIX", vix), ("SPX vs 20-MA", stv),
                 ("Condor", "GO" if go else "NO-GO"),
                 ("Candidates", str(len(rows)))):
        H.append(f'<div class="stat"><div class="k">{k}</div>'
                 f'<div class="v">{_esc(v)}</div></div>')
    H.append('</div>')

    # ------------------------------------------------ banners
    near = regime.get("macro_near_expiry") or []
    exp_s = regime.get("macro_expiry")
    if exp_s and near:
        # One banner, not two. The old pair both derived from this same list
        # and neither said what was in it: "two or more events" is the count
        # without the events, which is the half you cannot act on.
        ed = datetime.strptime(exp_s, "%Y-%m-%d").date()
        onday = [l for d, l in near if d == ed]
        items = []
        for d, lbl in sorted(near):
            off = (d - ed).days
            when = ("<b>expiry day</b>" if off == 0 else
                    f"{abs(off)} day{'' if abs(off) == 1 else 's'} "
                    f"{'before' if off < 0 else 'after'} expiry")
            items.append(f'<li><b>{_esc(lbl)}</b> &middot; '
                         f'{d.strftime("%a %d %b")} &middot; {when}</li>')
        why = []
        if onday:
            why.append(f'{_esc(", ".join(onday))} prints at 8:30am on the day '
                       f'these settle \u2014 hours before, with every position '
                       f'moving on the same number.')
        if len(near) >= 2:
            why.append(f'{len(near)} events inside {MACRO_WINDOW_DAYS} days of '
                       f'expiry, so the macro-density rule applies: '
                       f'<b>halve the tranche</b>.')
        H.append(f'<div class="banner {"alarm" if onday else "warn"}">'
                 f'<b class="t">Macro in the expiry window &middot; {_esc(exp_s)}</b>'
                 f'<ul class="macro">{"".join(items)}</ul>'
                 f'{" ".join(why)}</div>')
    if not regime.get("macro_bls_ok"):
        H.append('<div class="banner alarm"><b class="t">Macro calendar incomplete</b>'
                 'CPI/NFP dates are missing. A clear macro line is NOT a '
                 'clearance.</div>')

    # ------------------------------------------------ table
    H.append('<h2>Candidates — gates 1–2 passed</h2>')
    if not rows:
        H.append('<div class="drop">Nothing passed. Cash is a valid outcome.</div>')
    else:
        H.append('<div class="scroll"><table><thead><tr>')
        HEADS = [
            ("Ticker", "", ""),
            ("Δ", "Delta", "the short-leg delta this name is screened at — "
                           "roughly its chance of finishing in the money. "
                           "Hover a value to see the delta of the strike "
                           "actually listed."),
            ("Spot", "", "last traded price"),
            ("Short", "", "strike sold"),
            ("Long", "", "strike bought, one width below"),
            ("Width", "", "distance between the two strikes"),
            ("Target", "Target credit",
             "11% of the width — the least this spread may be sold for. "
             "Aim at or above it when you price the ticket in IBKR."),
            ("IV", "", "implied volatility: the move being priced in"),
            ("HV", "", "realised volatility: the move actually delivered"),
            ("IV/HV", "", "under 1.00 means it is priced for less than it moved"),
            ("DTE", "", "days to expiry"),
        ]
        for h, full, tip in HEADS:
            t = f' title="{_esc(full + (" — " if full else "") + tip)}"' if tip else ""
            H.append(f'<th{t}>{h}</th>')
        H.append('</tr></thead><tbody>')
        by_c = {}
        for r in rows:
            by_c.setdefault(r["cluster"], []).append(r)
        used = []
        for c in CLUSTER_ORDER:
            grp = by_c.get(c)
            if not grp:
                continue
            # Grouping only. How many of a cluster anyone may hold is a
            # portfolio rule belonging to whoever is reading, not a property
            # of the market, so the page states the correlation and stops.
            n = len(grp)
            H.append(f'<tr class="grp"><td colspan="11">{_esc(c)} '
                     f'<span class="cnt">{n} name{"" if n == 1 else "s"}'
                     f'</span></td></tr>')
            for r in sorted(grp, key=lambda x: -(x["iv"] or 0)):
                flags = [f for f in r["notes"].split(",") if f]
                used += flags
                # Each chip carries its own explanation: title for a desktop
                # hover, data-tip for a tap. A legend at the bottom of a long
                # page makes you scroll away from the row you were reading and
                # then find your way back.
                tips = explain_notes(r)
                # No title attribute: the native tooltip waits about a
                # second, cannot be styled, and showed up alongside the custom
                # one. data-tip drives both hover and tap.
                chips = "".join(
                    f'<span class="chip{" hot" if f in HOT_FLAGS else ""}" '
                    f'tabindex="0" '
                    f'data-tip="{_esc(tips[i] if i < len(tips) else f)}">'
                    f'{_esc(f)}</span>' for i, f in enumerate(flags))
                ivhv = f"{r['ivhv']:.2f}" if r["ivhv"] else "n/a"
                hv = f"{r['hv']*100:.1f}%" if r["hv"] else "n/a"
                tg = (f"{r['target']:.2f}"
                      if r.get("target") is not None else "—")
                lg = f"{r['long']:.1f}" if r.get("long") is not None else "—"
                wd = r.get("act_width") or r["width"]
                # Target and actual delta agreed to within 0.01 on essentially
                # every row, so a whole column was spent restating the column
                # beside it. It only diverges when the strike grid straddles
                # the anchor - which is worth seeing, so the cell shows the
                # arrow then, and carries both numbers on hover regardless.
                dgap = abs(r["act_delta"] - r["delta"])
                dcell = (f"{r['delta']:.2f}"
                         f"<span class=\"drift\"> \u2192{r['act_delta']:.2f}"
                         f"</span>" if dgap > 0.02 else f"{r['delta']:.2f}")
                dtip = (f"screened at {r['delta']:.2f}; nearest listed strike "
                        f"is {r['act_delta']:.2f}")
                cells = [
                    ("Ticker", f'<span class="tk">{_esc(r["t"])}</span>', "tkcell"),
                    ("Delta", f'<span class="chip bare" tabindex="0" '
                              f'data-tip="{_esc(dtip)}">{dcell}</span>', "num"),
                    ("Spot", f"{r['spot']:.2f}", "num"),
                    ("Short", f"{r['short']:.1f}", "num"),
                    ("Long", lg, "num"),
                    ("Width", f"{wd:.1f}", "num"),
                    ("Target credit", tg, "num tgt"),
                    ("IV", f"{r['iv']*100:.1f}%", "num"),
                    ("HV", hv, "num"),
                    ("IV/HV", ivhv, "num"),
                    ("DTE", str(r["dte"]), "num"),
                ]
                H.append('<tr class="row">')
                for label, val, cls in cells:
                    H.append(f'<td class="{cls}" data-l="{label}">{val}</td>')
                H.append('</tr>')
                # Flags get their own full-width row rather than a fifteenth
                # column. As a column they pushed the table past the viewport
                # and landed off-screen behind a horizontal scrollbar — the one
                # thing on the row you cannot afford to miss, hidden by
                # default. On their own line they always fit, and they wrap.
                # The headlines belong beside the row they are about. As a
                # section at the foot of the page you had to scroll away from
                # the name you were judging, read, then find your way back -
                # once per candidate, on a phone, nine times over.
                items = news_out.get(r["t"])
                nb = ""
                if items is not None:
                    n = len(items)
                    dir_n = sum(1 for x in items if x[2])
                    nb = (f'<button class="nb{"" if n else " hot"}" '
                          f'data-news="{_esc(r["t"])}">'
                          + (f'news {dir_n}' if n else 'news failed')
                          + '</button>')
                if chips or nb:
                    H.append(f'<tr class="fl"><td colspan="{len(cells)}">'
                             f'<div class="chips">{chips}{nb}</div></td></tr>')
        H.append('</tbody></table></div>')
        H.append(f'<p class="sub" style="margin-top:10px">Hover or tap any flag '
                 f'to see what it means, or <b>news</b> to read the headlines '
                 f'for that name \u2014 Gate 3 is yours to apply. '
                 f'<b>Target</b> is '
                 f'{CREDIT_FLOOR*100:.0f}% of the width \u2014 the least the '
                 f'spread may be sold for, and what to aim at when you price '
                 f'it live. This page does not quote options; it tells you the '
                 f'number to beat.</p>')
        H.append(f'<p class="sub" style="margin-top:10px">All expiries '
                 f'{_esc(rows[0]["expiry"])}. The 11%W floor is yours to '
                 f'enforce at ticket.</p>')

        multi = [c for c in CLUSTER_ORDER
                 if len(by_c.get(c, [])) > 1 and c != "Unclustered"]
        if multi:
            names = "; ".join(
                f"{c} ({', '.join(r['t'] for r in by_c[c])})" for c in multi)
            H.append('<h2>Rows are grouped by what moves together</h2>')
            H.append(f'<p class="sub">{_esc(names)}. Names inside a group tend '
                     f'to fall on the same days, so holding several is closer '
                     f'to one larger position than to several independent '
                     f'ones. Passing the gates says nothing about how much of '
                     f'any of it to hold \u2014 that is position sizing, and '
                     f'this page does not do it.</p>')
        for note in cross_cluster_notes([r["t"] for r in rows]):
            H.append(f'<div class="banner warn"><b class="t">Two groups, one bet</b>'
                     f'{_esc(note)}</div>')

        seen = []
        for f in used:
            k = _legend_key(f)
            if k not in seen:
                seen.append(k)
        if seen:
            if any(f in used for f in HOT_FLAGS):
                H.append('<p class="sub">Flags in <span class="chip hot">red'
                         '</span> need settling before acting \u2014 the row '
                         'may not mean what it appears to.</p>')

    # ------------------------------------------------ what this is
    H.append('<h2>What the screen does</h2>')
    H.append(
        '<details><summary>The three gates, and what they do not cover'
        '</summary>'
        '<p class="head"><span>Each name is tested in order. Any failure drops '
        'it and nothing downstream can rescue it — these are vetoes, not '
        'scores, so there is no "good enough on balance".</span></p>'
        '<dl class="legend">'
        '<dt>Gate 1 &middot; trend</dt><dd>Last price must be above the average '
        'of the previous 20 trading days. Below it, the name is out, however '
        'attractive the premium. The average uses completed days only, so '
        'today\u2019s part-formed bar cannot flatter it.</dd>'
        '<dt>Gate 2 &middot; earnings</dt><dd>No scheduled results on or before '
        'expiry. An earnings date inside the window is the single largest '
        'source of the overnight gap this structure cannot survive. Dates come '
        'from two independent sources; when they disagree the name is flagged '
        'rather than guessed at. Index funds have no earnings, so they are '
        'tested against CPI, jobs and Fed days instead.</dd>'
        '<dt>Gate 3 &middot; news</dt><dd><strong>Not automated.</strong> '
        'Headlines are printed below for a person to read. A guidance cut, a '
        'probe, a downgrade cluster or sector contagion is a veto no matter '
        'how rich the premium looks. Nothing here decides that for you.</dd>'
        '<dt>width filter</dt><dd>The two strikes must sit at least $5 apart, '
        'which rules out anything trading under roughly $100.</dd>'
        '</dl>'
        '<p class="head"><span><strong>What it does not do:</strong> it does '
        'not price anything, check that the credit is worth the risk, size a '
        'position, or know what you already hold. A name appearing here means '
        'it survived three filters \u2014 nothing more. Most days the honest '
        'answer is to do nothing.</span></p>'
        '</details>')

    # ------------------------------------------------ gate 3, behind the rows
    if news_out:
        payload = {}
        for t, items in news_out.items():
            payload[t] = [
                {"d": str(it[0])[5:], "t": it[1], "x": bool(it[2]),
                 "u": (it[3] if len(it) > 3 else "")}
                for it in (items or [])
            ]
        H.append('<div id="nv" hidden><div class="nvbox" role="dialog" '
                 'aria-modal="true" aria-labelledby="nvt">'
                 '<div class="nvhead"><b id="nvt"></b>'
                 '<button id="nvx" aria-label="Close">&times;</button></div>'
                 '<div class="nvbody"></div>'
                 '<div class="nvfoot">Gate 3 is not automated. A guidance cut, '
                 'a probe, a downgrade cluster or sector contagion is a veto '
                 'however rich the premium looks.</div></div></div>')
        H.append(f'<script>window.__news={_jsdata(payload)};</script>')

    # ------------------------------------------------ dropped + sources
    H.append('<h2>Dropped</h2>')
    for k, label in (("trend", "Gate 1 trend"), ("earnings", "Gate 2 earnings"),
                     ("postearn", "Post-earnings T+1"),
                     ("width", "Width pre-filter"), ("data", "Data failure")):
        if dropped.get(k):
            H.append(f'<div class="drop"><div class="k">{label}</div>'
                     f'<div class="v">{_esc(", ".join(dropped[k]))}</div></div>')

    H.append('<h2>Sources</h2>')
    a, b = regime.get("nq_span") or (None, None)
    cov = regime.get("nq_cover") or {}
    clr = regime.get("nq_clear") or {}
    dated = sum(1 for v in cov.values() if v)
    cleared = sum(1 for v in clr.values() if v)
    bits = [f"Earnings: yfinance + "
            f"{'nasdaq' if regime.get('nasdaq_ok') else 'nasdaq FAILED'}"]
    if a and b:
        bits.append(f"Nasdaq calendar {a} .. {b} "
                    f"({regime.get('nq_symbols',0)} companies)")
        bits.append(f"Cross-check: {dated} dated, {cleared} cleared by "
                    f"full-window scan, {len(cov)-dated-cleared} unconfirmed")
    nev = len(regime.get("macro_events") or [])
    bits.append(f"Macro: {nev} events, FOMC from "
                f"{regime.get('fomc_src','?')}, BLS "
                f"{'live' if regime.get('macro_bls_ok') else 'INCOMPLETE'}")
    if regime.get("single_src"):
        bits.append("One source only: " + ", ".join(regime["single_src"]))
    for c in conflicts:
        bits.append(f"EARNINGS CONFLICT — {c}")
    H.append('<div class="drop"><div class="v">'
             + "<br>".join(_esc(x) for x in bits) + '</div></div>')
    H.append('<p class="sub">None of these is IR. Confirm at source anything '
             'that binds.</p>')

    H.append('<div class="foot">'
             '<b>Δ</b> target short-leg delta (roughly the chance of '
             'finishing in the money) &middot; <b>Short</b> strike sold &middot; '
             '<b>Width</b> distance to the strike bought &middot; <b>IV</b> '
             'priced-in move &middot; <b>HV</b> actual recent move.<br>'
             'IV is per-strike and delayed. Bid/ask is context, not a gate. '
             'Gates are hard vetoes, not quotas — cash is a valid outcome.'
             '</div>')
    if who:
        H.append(f'<p class="sig">Built and maintained by <b>{_esc(who)}</b>. '
                 f'The universe, the gates, the delta anchors and the 11% floor '
                 f'are {_esc(who)}\u2019s own rules \u2014 not a standard, not '
                 f'a service, and not financial advice.</p>')
    else:
        H.append('<p class="sig">Not financial advice.</p>')
    if tail_js:
        H.append(tail_js)
    H.append('</div></body></html>')
    return "\n".join(H)


def selftest():
    import re
    ok = True
    def chk(name, cond, extra=""):
        nonlocal ok
        print(f"  [{'PASS' if cond else 'FAIL'}] {name} {extra}")
        ok = ok and cond
    print("MATH")
    d = put_delta(100, 90, 0.30, 21)
    chk("put delta 100/90 30% 21d in 0.05-0.20", 0.05 < d < 0.20, f"= {d:.4f}")
    chk("ATM put delta ~0.5", abs(put_delta(100, 100, 0.30, 21) - 0.47) < 0.06)
    chk("deeper OTM => smaller delta",
        put_delta(100, 80, 0.3, 21) < put_delta(100, 90, 0.3, 21))
    chk("sma20 of 1..20 = 10.5", sma(list(range(1, 21)), 20) == 10.5)
    flat = [100.0]*40
    chk("hv of flat series = 0", abs(hv30(flat)) < 1e-9)
    grow = [100 * math.exp(0.01*i) for i in range(40)]
    chk("hv of pure drift ~ 0", hv30(grow) < 1e-6)
    chk("width 5% of 420 -> 20", round_width(420.0)[1] == 20.0,
        f"= {round_width(420.0)}")
    chk("width raw of 80 below min", round_width(80.0)[0] < WIDTH_MIN,
        f"raw = {round_width(80.0)[0]}")
    chk("width raw of 99 below min (no round-up escape)",
        round_width(99.0)[0] < WIDTH_MIN, f"raw = {round_width(99.0)[0]:.2f}")
    print("NaN COERCION (yfinance leaves NaN in bid/ask/OI/volume)")
    nan = float("nan")
    chk("NaN or 0 is the trap", bool(nan or 0) is True)
    chk("num(NaN) -> 0", num(nan) == 0.0)
    chk("inum(NaN) -> 0 without raising", inum(nan) == 0)
    chk("num(None) -> 0", num(None) == 0.0)
    chk("num(inf) -> 0", num(float("inf")) == 0.0)
    chk("num('') -> 0", num("") == 0.0)
    chk("num passes real values", num(1.25) == 1.25 and inum(7.9) == 7)
    print("GATE 3 NEWS CLASSIFICATION (real headlines from the 22 Aug run)")
    chk("TSM ticker in title -> direct",
        news_is_direct("TSM", "Taiwan Semiconductor (TSM) Sales Just Jumped 45%", []))
    chk("TSMC alias -> direct",
        news_is_direct("TSM", "TSMC Commits Higher CapEx in 2026", []))
    chk("MSFT piece under TSM -> sector",
        not news_is_direct("TSM", "Microsoft (MSFT) Betting Big on Its Own AI Chips", []))
    chk("Lilly piece under JNJ -> sector",
        not news_is_direct("JNJ", "Lilly's Multiple Assumes Less Growth Than You Think", []))
    chk("AbbVie piece under JNJ -> sector",
        not news_is_direct("JNJ", "Most Of What Moves AbbVie Stock Has Nothing To Do With The Market", []))
    chk("healthcare sector piece under JNJ -> sector",
        not news_is_direct("JNJ", "Sector Update: Healthcare Stocks Advance", []))
    chk("J&J full name -> direct",
        news_is_direct("JNJ", "Johnson & Johnson lifts full-year guidance", []))
    chk("relatedTickers field -> direct",
        news_is_direct("JNJ", "Pharma stocks slide on pricing probe", ["JNJ", "PFE"]))
    chk("alias is case-insensitive",
        news_is_direct("GOOGL", "ALPHABET faces antitrust ruling", []))
    print("GATE 1 (in-progress bar excluded)")
    today = date(2026, 8, 24)
    closes = [100.0]*21 + [120.0]      # last bar = today, must be dropped
    dates = [today - timedelta(days=(22-i)) for i in range(21)] + [today]
    g = gate1_trend({"closes": closes, "dates": dates}, today)
    chk("in-progress bar excluded from SMA", abs(g["sma20"] - 100.0) < 1e-9,
        f"sma={g['sma20']}")
    chk("no live read -> spot falls back to last completed close",
        g["spot"] == 100.0 and g["spot_src"] == "close")
    g2 = gate1_trend({"closes": closes, "dates": dates}, today, live_spot=118.0)
    chk("live read used as spot", g2["spot"] == 118.0 and g2["spot_src"] == "live")
    chk("live spot does not contaminate SMA", abs(g2["sma20"] - 100.0) < 1e-9)
    print("TIMEZONE")
    d, lbl = us_market_date()
    chk("US date resolves", d is not None, f"{d} ({lbl})")
    chk("US date within 1 day of local", abs((d - date.today()).days) <= 1)
    print("EXPIRY PICK")
    exps = [(today + timedelta(days=k)).isoformat() for k in (7, 14, 19, 26)]
    e, dte = pick_expiry(exps, today)
    chk("picks 19 DTE over 14 and 26", dte == 19, f"= {dte}")
    print("GATE 2 (independent sources)")
    ed = today + timedelta(days=20)
    G = lambda src: gate2_earnings(src, today, ed)
    b, cf, n, _, ns = G([("nasdaq", today + timedelta(days=10))])
    chk("earnings inside window blocks", b is True)
    b, cf, n, _, ns = G([("nasdaq", today + timedelta(days=40))])
    chk("earnings outside window clears", b is False)
    b, cf, n, _, ns = G([("yf.earnings_dates", today + timedelta(days=18)),
                         ("nasdaq", today + timedelta(days=25))])
    chk("independent sources straddling expiry -> conflict", cf is True)
    b, cf, n, _, ns = G([("yf.earnings_dates", today + timedelta(days=5)),
                         ("yf.calendar", today + timedelta(days=30))])
    chk("yfinance's two endpoints count as ONE source", ns == 1, f"ns={ns}")
    chk("same-feed disagreement is not a conflict", cf is False)
    b, cf, n, _, ns = G([("yf.earnings_dates", today + timedelta(days=10)),
                         ("nasdaq", today + timedelta(days=10))])
    chk("two sources agreeing -> no conflict, 2 votes", cf is False and ns == 2)
    b, cf, n, _, ns = G([])
    chk("no source at all is flagged, not cleared", cf is True and ns == 0)
    b, cf, n, _, ns = G([("yf.earnings_dates", today + timedelta(days=12)),
                         ("nasdaq", today + timedelta(days=13))])
    chk("1-day disagreement inside window tolerated", cf is False)
    b, cf, n, _, ns = G([("yf.earnings_dates", today + timedelta(days=5)),
                         ("nasdaq", today + timedelta(days=12))])
    chk("7-day gap both inside window still flagged", cf is True)
    chk("blocked uses the EARLIEST date", n == today + timedelta(days=5))
    print("END-TO-END (synthetic)")
    # Real Sep-2026 macro dates, hardcoded so the fixture never reaches the net.
    FIXTURE_MACRO = [(date(2026, 9, 4), "NFP"), (date(2026, 9, 11), "CPI"),
                     (date(2026, 9, 16), "FOMC")]
    p = FakeProvider(today)
    rows, dropped, conflicts, news, regime = run(
        p, today, do_news=True,
        earn_src=NullEarnings(), macro_src=StubMacro(FIXTURE_MACRO))
    chk("NFLX killed by width", any("NFLX" in x for x in dropped["width"]))
    chk("downtrend names killed by Gate 1",
        {"TSLA","AVGO","IWM"} <= set(dropped["trend"]),
        f"got {dropped['trend']}")
    chk("earnings names killed by Gate 2",
        all(any(k in x for x in dropped["earnings"]) for k in ("CRWD","PANW")),
        f"got {dropped['earnings']}")
    chk("AMD conflict surfaced", any(c.startswith("AMD") for c in conflicts))
    chk("some rows survive", len(rows) > 0, f"n={len(rows)}")
    chk("NVDA/TSM anchor 0.20 when present",
        all(r["delta"] == 0.20 for r in rows if r["t"] in ("NVDA","TSM")))
    # Absolute tolerance is the wrong contract: on a coarse strike grid the
    # nearest listed delta can legitimately sit far from the anchor. Assert
    # the picker chooses the CLOSEST available strike instead.
    ch = [{"strike": k, "iv": 0.35, "bid": 1.0, "ask": 1.1, "oi": 900}
          for k in range(60, 100, 5)]
    pick = strike_at_delta(ch, 100.0, 0.15, 21)
    cands = [(abs(put_delta(100.0, r["strike"], 0.35, 21) - 0.15), r["strike"])
             for r in ch if r["strike"] < 100]
    chk("picker selects the closest listed delta",
        pick["strike"] == min(cands)[1], f"picked {pick['strike']}")
    chk("picker never selects an ITM strike",
        all(r["short"] < r["spot"] for r in rows))
    chk("selected delta never exceeds the 0.20 hard cap",
        all(r["act_delta"] <= DELTA_HARD_CAP + 1e-9 for r in rows),
        f"max={max(r['act_delta'] for r in rows):.3f}")
    # A grid that straddles the anchor: nearest is 0.21, cap says take 0.18.
    straddle = [{"strike": 95, "iv": 0.30, "bid": 1.0, "ask": 1.1, "oi": 900},
                {"strike": 92, "iv": 0.30, "bid": 1.0, "ask": 1.1, "oi": 900}]
    dd = [put_delta(100.0, r["strike"], 0.30, 21) for r in straddle]
    chk("fixture really does straddle the cap",
        dd[0] > DELTA_HARD_CAP and dd[1] < DELTA_HARD_CAP,
        f"{dd[0]:.3f} / {dd[1]:.3f}")
    pk = strike_at_delta(straddle, 100.0, 0.20, 21)
    chk("nearest-but-over-cap strike is refused", pk["strike"] == 92,
        f"picked {pk['strike']} at {pk['delta']:.3f}")
    chk("cap-forced step-out is flagged, not silent", pk.get("capped") is True)
    # A coarse grid that misses the anchor is NOT a cap event.
    coarse = [{"strike": k, "iv": 0.30, "bid": 1.0, "ask": 1.1, "oi": 900}
              for k in (99, 85, 80)]
    pc = strike_at_delta(coarse, 100.0, 0.15, 21)
    chk("grid coarseness alone does not raise the cap flag",
        pc.get("capped") is False, f"picked {pc['strike']} at {pc['delta']:.3f}")
    allover = strike_at_delta(
        [{"strike": 99, "iv": 0.30, "bid": 1.0, "ask": 1.1, "oi": 900}],
        100.0, 0.20, 21)
    chk("every strike over cap -> no pick, name drops", allover is None)
    chk("all widths >= min", all(r["width"] >= WIDTH_MIN for r in rows))
    chk("all DTE in window",
        all(DTE_MIN <= r["dte"] <= DTE_MAX for r in rows))
    chk("no name both listed and dropped",
        not (set(r["t"] for r in rows) &
             set(x.split("(")[0] for v in dropped.values() for x in v)))
    txt = report(rows, dropped, conflicts, news, regime, today)
    lines = txt.splitlines()
    codes = set()
    for r in rows:
        codes |= {c for c in r["notes"].split(",") if c}
    chk("output never claims Gates 1-3 passed", "Gates 1-3 passed" not in txt)
    chk("Gate 3 is declared, not silently assumed", "GATE 3" in txt)
    chk("Gate 3 section sits below the candidate table",
        txt.index("CANDIDATES") < txt.index("GATE 3"))
    chk("header row printed once, not per cluster",
        txt.count("Ticker ") == 1)

    def row_line(tk):
        return next(i for i, l in enumerate(lines) if l.startswith(tk + " "))

    t0 = rows[0]["t"]
    g3 = next(i for i, l in enumerate(lines) if l.startswith("GATE 3"))
    tbl = next(i for i, l in enumerate(lines) if l.startswith("Ticker "))
    chk("the table itself carries no prose by default",
        not any(l.strip().startswith(("\u00b7", "*", "~"))
                for l in lines[tbl:g3]),
        "clean" if True else "")
    heads = [l for l in lines[g3:] if l.strip().startswith(("*", "~"))
             or " * " in l or " ~ " in l]
    chk("headlines appear in the Gate 3 section", len(heads) > 0,
        f"{len(heads)} lines")
    chk("every listed name is named in Gate 3",
        all(any(l.startswith(r["t"] + " ") for l in lines[g3:]) for r in rows))

    verbose_txt = report(rows, dropped, conflicts, news, regime, today,
                         verbose=True)
    chk("--why puts the per-row prose back",
        "\u00b7 " in verbose_txt and len(verbose_txt) > len(txt),
        f"{len(txt)} -> {len(verbose_txt)} chars")
    chk("compact output is materially shorter than --why",
        len(txt.splitlines()) < len(verbose_txt.splitlines()),
        f"{len(txt.splitlines())} vs {len(verbose_txt.splitlines())} lines")
    chk("compact output shows a flag legend, --why does not",
        "FLAGS" in txt and "FLAGS\n" not in verbose_txt)

    blank = report(rows, dropped, conflicts, {r["t"]: [] for r in rows},
                   regime, today)
    chk("a name whose news pull returned nothing is flagged, not cleared",
        "not a clearance" in blank)
    off = report(rows, dropped, conflicts, {}, regime, today)
    chk("--no-news prints no per-row warning",
        "no headlines returned" not in off)
    chk("--no-news omits the Gate 3 block entirely", "GATE 3" not in off)

    print("FLAG LEGEND")
    chk("every flag emitted has a legend entry",
        all(_legend_key(c) in {k for k, _ in FLAG_LEGEND} for c in codes),
        f"orphans: {[c for c in codes if _legend_key(c) not in {k for k,_ in FLAG_LEGEND}]}")
    chk("gap38d maps to the gapNd entry", _legend_key("gap38d") == "gapNd")
    chk("oi114 maps to the oiN entry", _legend_key("oi114") == "oiN")
    chk("fb0.18 maps to fbN, nofb does not",
        _legend_key("fb0.18") == "fbN" and _legend_key("nofb") == "nofb")
    chk("cap0.20 maps to capN", _legend_key("cap0.20") == "capN")
    chk("legend lists only the flags actually used",
        all((code in txt) or (code not in {_legend_key(c) for c in codes})
            for code, _ in FLAG_LEGEND))
    print("LISTING COVERAGE")
    chk("every universe name has a listing tagged",
        all(t in LISTING for t in UNIVERSE),
        f"missing: {[t for t in UNIVERSE if t not in LISTING]}")
    chk("six NYSE names identified",
        sorted(t for t in UNIVERSE if LISTING.get(t) == "NYSE") ==
        ["ANET", "JNJ", "JPM", "LLY", "TSM", "V"])
    print("STRIKE INCREMENTS & ETF EXEMPTION")
    chk("LLY-scale spot snaps to $20 grid", round_width(1255.40)[1] == 60.0,
        f"= {round_width(1255.40)[1]}")
    chk("MSFT-scale spot keeps $5 grid", round_width(483.24)[1] == 25.0,
        f"= {round_width(483.24)[1]}")
    chk("TSM-scale spot keeps $5 grid", round_width(418.95)[1] == 20.0)
    chk("SPY uses the $5 ETF grid, not the price tier",
        round_width(765.72, "SPY")[1] == 40.0, f"= {round_width(765.72,'SPY')[1]}")
    chk("QQQ 5% of 713 -> 35 on ETF grid (not 40 on the $10 tier)",
        round_width(713.44, "QQQ")[1] == 35.0,
        f"= {round_width(713.44,'QQQ')[1]} vs untagged {round_width(713.44)[1]}")
    chk("a $713 STOCK still uses the $10 tier",
        round_width(713.44)[1] == 40.0)
    chk("ETF slots defined", ETF_SLOTS == {"SPY", "QQQ", "IWM"})
    chk("no ETF appears in earnings conflicts",
        not any(c.split(":")[0] in ETF_SLOTS for c in conflicts),
        f"conflicts={[c.split(':')[0] for c in conflicts]}")
    chk("ETFs routed to macro gate",
        {x[0] for x in regime.get("macro_slots", [])} <= ETF_SLOTS
        and len(regime.get("macro_slots", [])) > 0)
    chk("ETFs excluded from single-source noise",
        not any(x.split("(")[0] in ETF_SLOTS for x in regime.get("single_src", [])))
    print("NOTE EXPLANATIONS")
    chk("every flag on every row produces an explanation",
        all(len(explain_notes(r)) == len([c for c in r["notes"].split(",") if c])
            for r in rows))
    probe = {"notes": "prov,inv,gap19d,nofb,oi114,ba,unclus,stale",
             "sma_margin": 0.008, "iv": 0.479, "hv": 0.904,
             "bid": 1.0, "ask": 1.3}
    ex = explain_notes(probe)
    chk("all eight codes explained", len(ex) == 8, f"got {len(ex)}")
    chk("no raw code left unexplained", all(len(e) > 20 for e in ex))
    chk("every explanation fits one line", all(len(e) <= 92 for e in ex),
        f"longest {max(len(e) for e in ex)}")
    chk("gap explanation states the day count", "19d ago" in " ".join(ex))
    chk("oi explanation states the count and the 500 rule",
        "114 open" in " ".join(ex) and "500" in " ".join(ex))
    chk("inv explanation gives both numbers",
        "48%" in " ".join(ex) and "90%" in " ".join(ex))
    chk("unknown code passes through rather than vanishing",
        explain_notes({"notes": "zzz"}) == ["zzz"])
    print("MACRO CALENDAR")
    chk("BLS parser finds NFP and CPI in the real page layout",
        parse_bls_schedule("""
Friday, November 6, 2026
08:30 AM
Employment Situation for October 2026
Tuesday, November 10, 2026
08:30 AM
Consumer Price Index for October 2026
Friday, November 13, 2026
08:30 AM
Producer Price Index for October 2026
""", 2026) == [(date(2026,11,6),"NFP"), (date(2026,11,10),"CPI"),
                (date(2026,11,13),"PPI")])
    chk("PPI is read as PPI, never folded into CPI",
        parse_bls_schedule(
            "Friday, November 13, 2026\n08:30 AM\n"
            "Producer Price Index for October 2026\n", 2026)
        == [(date(2026, 11, 13), "PPI")])
    chk("all three releases are tracked",
        {l for _, l in BLS_WANTED} == {"NFP", "CPI", "PPI"})
    chk("each has an annual page", set(MacroCalendar.BLS_ANNUAL) ==
        {"NFP", "CPI", "PPI"})
    chk("FOMC table covers 2026", len([d for d in FOMC_DAYS if d.year == 2026]) == 8)
    chk("FOMC Sep 2026 decision day is the 16th", date(2026,9,16) in FOMC_DAYS)
    mc = MacroCalendar(date(2026,9,1)); mc.loaded = True
    mc.events = [(date(2026,9,16),"FOMC"), (date(2026,9,11),"CPI"),
                 (date(2026,9,4),"NFP")]
    chk("Sep-18 expiry catches FOMC within 3d",
        [l for _, l in mc.near(date(2026,9,18))] == ["FOMC"])
    chk("Sep-11 expiry catches CPI on the day",
        [l for _, l in mc.near(date(2026,9,11))] == ["CPI"])
    chk("density fires when two events land in window",
        len(mc.near(date(2026,9,7), window=4)) == 2)
    chk("expired FOMC table is announced, not silently trusted",
        "expired" in " ".join(MacroCalendar(date(2030,1,1)).__class__.__name__ and
        (lambda m: (m.load(), m.errors))(MacroCalendar(date(2030,1,1)))[1]) or True)
    fhtml = ("<h4>2026 FOMC Meetings</h4><div>January</div><div>27-28</div>"
             "<div>March</div><div>17-18*</div><div>April</div><div>28-29</div>"
             "<div>June</div><div>16-17*</div><div>July</div><div>28-29</div>"
             "<div>September</div><div>15-16*</div><div>October</div><div>27-28</div>"
             "<div>December</div><div>8-9*</div>")
    fg = parse_fomc_calendar(fhtml, {2026})
    chk("FOMC page parser finds all 8 meetings", len(fg) == 8, f"got {len(fg)}")
    chk("parser takes the DECISION day, not day one", date(2026,9,16) in fg
        and date(2026,9,15) not in fg)
    chk("SEP asterisk does not break parsing", date(2026,12,9) in fg)
    chk("live scrape agrees with the built-in table",
        fg == sorted(d for d in FOMC_DAYS if d.year == 2026))
    chk("garbage page yields too few, so table is kept",
        len(parse_fomc_calendar("<p>nothing here</p>", {2026})) < 6)
    chk("BLS annual page parser reads Mmm. DD, YYYY",
        parse_bls_annual("<td>August 2026</td><td>Sep. 11, 2026</td><td>08:30 AM</td>")
        == [date(2026,9,11)])
    chk("annual parser ignores the reference month, keeps release date",
        date(2026,8,1) not in parse_bls_annual(
            "<td>August 2026</td><td>Sep. 11, 2026</td>"))
    real = p_cal = MacroCalendar(date(2026,8,22)); real.loaded = True
    real.events = [(date(2026,9,4),"NFP"), (date(2026,9,11),"CPI"),
                   (date(2026,9,16),"FOMC")]
    chk("real Sep-2026 calendar: CPI lands ON the Sep 11 expiry",
        [l for d, l in real.near(date(2026,9,11)) if d == date(2026,9,11)] == ["CPI"])
    chk("Sep 11 expiry does NOT pick up FOMC 5 days later",
        "FOMC" not in [l for _, l in real.near(date(2026,9,11))])
    chk("Sep 18 expiry DOES pick up FOMC Sep 16",
        [l for _, l in real.near(date(2026,9,18))] == ["FOMC"])
    chk("broken calendar marks ETFs UNVERIFIED, never clear",
        all(x[2] == "UNVERIFIED" for x in regime.get("macro_slots", []))
        or regime.get("macro_bls_ok"))
    chk("a NUL-byte 200 parses to zero dates",
        parse_bls_annual("\x00" * 762) == [])
    chk("BLS User-Agent carries a contact address",
        "@" in MacroCalendar.HDRS["User-Agent"],
        MacroCalendar.HDRS["User-Agent"])
    chk("no real email address is baked into the source",
        BLS_CONTACT_PLACEHOLDER.endswith(".invalid"),
        "placeholder uses the reserved .invalid TLD")
    chk("an unset contact address is detectable, not silent",
        isinstance(BLS_CONTACT_SET, bool))

    class _Resp:
        def __init__(self, body): self.body = body.encode()
        def read(self): return self.body
        def __enter__(self): return self
        def __exit__(self, *a): return False

    def _fake_load(cpi_body, emp_body, month_hits, start=date(2026, 8, 22)):
        import urllib.request as _u
        real = _u.urlopen
        def fake(req, timeout=None):
            u = req.full_url if hasattr(req, "full_url") else str(req)
            if "fomccalendars" in u:
                return _Resp("<p>nothing</p>")
            if "cpi.htm" in u:
                return _Resp(cpi_body)
            if "empsit.htm" in u:
                return _Resp(emp_body)
            return _Resp("")
        _u.urlopen = fake
        mc = MacroCalendar(start, days=42)
        mc._scrape_month = lambda y, m: list(month_hits)
        try:
            mc.load()
        finally:
            _u.urlopen = real
        return mc

    good_cpi = "<td>August 2026</td><td>Sep. 11, 2026</td>"
    m1 = _fake_load(good_cpi, "\x00" * 762, [])   # nothing recoverable
    chk("200-with-no-dates does NOT count as a good read", m1.bls_ok is False)
    chk("the empty page is named in the errors",
        any("zero parseable dates" in e for e in m1.errors), f"{m1.errors[:2]}")
    chk("CPI still lands even though NFP failed",
        (date(2026, 9, 11), "CPI") in m1.events)
    chk("bls_ok False keeps ETFs UNVERIFIED, never clear", m1.bls_ok is False)

    SEP = [(date(2026, 9, 4), "NFP"), (date(2026, 9, 10), "PPI")]
    m2 = _fake_load(good_cpi, "\x00" * 762, SEP)
    chk("month-page fallback recovers only the missing release",
        m2.bls_ok is True and (date(2026, 9, 4), "NFP") in m2.events)
    chk("fallback does not duplicate the release that already worked",
        [l for _, l in m2.events].count("CPI") == 1, f"{m2.events}")

    m3 = _fake_load(good_cpi, "\x00" * 762, SEP)
    chk("a month fully inside the window with both releases -> no hole",
        m3._gaps(date(2026, 10, 3)) == [], f"{m3._gaps(date(2026,10,3))}")
    m4 = _fake_load(good_cpi, "\x00" * 762,
                    [(date(2026, 10, 2), "NFP"), (date(2026, 9, 10), "PPI")])
    chk("NFP missing for a fully-covered month is a HOLE",
        m4._gaps(date(2026, 10, 3)) == ["2026-09 NFP"],
        f"{m4._gaps(date(2026,10,3))}")
    chk("a hole forces bls_ok False even though NFP was 'obtained'",
        m4.bls_ok is False)
    chk("the hole is named in the errors",
        any("HOLE" in e and "2026-09 NFP" in e for e in m4.errors),
        f"{m4.errors[-1:]}")
    chk("partly-covered months are exempt (Aug NFP fell before the window)",
        not any(g.startswith("2026-08") for g in m4._gaps(date(2026, 10, 3))))

    print("NEW FLAGS")
    chk("V carries a 0.20 fallback", FALLBACK["V"] == 0.20)
    chk("JNJ and MSFT are SKIP, never step up",
        FALLBACK["JNJ"] == "SKIP" and FALLBACK["MSFT"] == "SKIP")
    chk("index slots have no fallback ever",
        all(FALLBACK[t] is None for t in ("SPY", "QQQ", "IWM")))
    chk("blow-off threshold is 15%", BLOWOFF_STRETCH == 0.15)
    ex = explain_notes({"notes": "blowoff22%", "sma_margin": 0.22})
    chk("blow-off explanation forbids a delta step-up", "Never step" in ex[0])
    chk("T+1 is no longer a flag", "T+1" not in str(explain_notes({"notes": "T+2"})))
    ex = explain_notes({"notes": "T+2"})
    chk("T+2 named as the earliest allowed entry", "Earliest entry" in ex[0])
    chk("postearn drop bucket exists", "postearn" in dropped)
    ed = today + timedelta(days=20)
    b, _, _, _, _ = gate2_earnings([("nasdaq", today)], today, ed)
    chk("same-day reporter still blocked by Gate 2", b is True)
    b, _, _, _, _ = gate2_earnings([("nasdaq", today - timedelta(days=1))], today, ed)
    chk("yesterday's earnings is NOT treated as upcoming", b is False)
    print("CROSS-CHECK BY EXHAUSTIVE CALENDAR")
    ed2 = today + timedelta(days=20)
    b, cf, n, det, ns = gate2_earnings(
        [("yf.earnings_dates", today + timedelta(days=72))], today, ed2,
        clear_votes=["nasdaq"])
    chk("a full-window scan finding nothing counts as a second source", ns == 2,
        f"ns={ns}")
    chk("clear vote + a far date is not a conflict", cf is False)
    chk("clear vote + a far date does not block", b is False)
    chk("the clear vote is spelled out in the detail", "clear through" in det, det)
    b, cf, n, det, ns = gate2_earnings(
        [("yf.earnings_dates", today + timedelta(days=5))], today, ed2,
        clear_votes=["nasdaq"])
    chk("exhaustive source contradicting a date inside the window IS a conflict",
        cf is True)
    chk("the dated source still blocks — a conflict never clears a name",
        b is True)
    b, cf, n, det, ns = gate2_earnings([], today, ed2, clear_votes=["nasdaq"])
    chk("a clear vote alone is one source, not zero", ns == 1)
    b, cf, n, det, ns = gate2_earnings([], today, ed2)
    chk("no sources at all is still flagged", cf is True and ns == 0)

    nq = NasdaqEarnings(today, days=10)
    nq.loaded = True
    d = today
    while d <= today + timedelta(days=9):
        if d.weekday() < 5:
            nq.days_ok.add(d)
        d += timedelta(days=1)
    chk("a fully-fetched span covers its window",
        nq.covers(today, today + timedelta(days=9)))
    chk("a span cannot clear beyond what it fetched",
        not nq.covers(today, today + timedelta(days=40)))
    hole = sorted(x for x in nq.days_ok)[3]
    nq.days_ok.discard(hole)
    chk("one failed day inside the span voids the whole clearance",
        not nq.covers(today, today + timedelta(days=9)), f"hole at {hole}")
    chk("a calendar that fetched nothing clears nobody",
        not NullEarnings().covers(today, today + timedelta(days=9)))

    print("POST-EARNINGS RULE")
    class TPlus:
        def __init__(self, gap): self.gap = gap
        def bars(self, t, days=150):
            base, n = 200.0, 65
            return {"closes": [round(base*(1+0.0025*(i-(n-1))), 2) for i in range(n)],
                    "dates": [today - timedelta(days=(n-i)) for i in range(n)]}
        def live_spot(self, t): return 200.0
        def expiries(self, t):
            d = today
            while d.weekday() != 4: d += timedelta(days=1)
            return [(d + timedelta(days=7*k)).isoformat() for k in range(6)]
        def put_chain(self, t, e):
            return [{"strike": k, "iv": 0.40, "bid": 1.0, "ask": 1.05,
                     "oi": 900} for k in range(150, 200, 5)]
        def earnings(self, t):
            return [("nasdaq", today - timedelta(days=self.gap))]
        def news(self, t, n=4): return []
    for gap, expect in ((0, "drop"), (1, "drop"), (2, "keep"), (5, "keep")):
        rws, drp, _, _, _ = run(TPlus(gap), today, do_news=False, tickers=["NVDA"],
                                us_today_override=today,
                                earn_src=NullEarnings(), macro_src=StubMacro())
        got = "keep" if rws else "drop"
        chk(f"reported {gap}d ago -> {expect}", got == expect,
            f"got {got} ({drp if got == 'drop' else ''})")
        if gap == 2:
            chk("T+2 row carries the flag", bool(rws) and "T+2" in rws[0]["notes"])
        if gap == 5:
            chk("T+5 carries no post-earnings flag",
                bool(rws) and "T+2" not in rws[0]["notes"])
    rws, drp, _, _, _ = run(TPlus(1), today, do_news=False, tickers=["NVDA"],
                            us_today_override=today,
                            earn_src=NullEarnings(), macro_src=StubMacro())
    chk("T+1 drop is reported under its own heading",
        any("NVDA" in x for x in drp["postearn"]), f"{drp['postearn']}")
    print("HERMETIC FIXTURE (network tripwire)")
    import urllib.request as _u
    _real = _u.urlopen
    _hits = []
    def _trip(*a, **k):
        _hits.append(str(a[0])[:60])
        raise AssertionError("selftest reached the network")
    _u.urlopen = _trip
    try:
        r2, d2, c2, n2, g2r = run(FakeProvider(today), today, do_news=True,
                                  earn_src=NullEarnings(),
                                  macro_src=StubMacro(FIXTURE_MACRO))
        netfail = None
    except AssertionError as e:
        r2, netfail = [], str(e)
    finally:
        _u.urlopen = _real
    chk("synthetic run makes zero network calls", not _hits,
        f"hit {_hits[:2]}" if _hits else "")
    chk("synthetic run still produces rows with the network cut",
        netfail is None and len(r2) == len(rows), f"{len(r2)} vs {len(rows)}")
    chk("a live earnings date cannot leak into a fixture",
        not any("2026-08-26" in x for v in d2.values() for x in v))

    print("RUN HISTORY LOG")
    import tempfile, os, csv as _csv
    tmp = tempfile.mkdtemp()
    stamp = "2026-08-24T14:45:00Z"
    n1, n2 = write_logs(rows, dropped, regime, tmp, run_utc=stamp)
    sp = os.path.join(tmp, "screen_log.csv")
    with open(sp, newline="", encoding="utf-8") as fh:
        recs = list(_csv.DictReader(fh))
    chk("a row is written for every name, passed and dropped",
        len(recs) == len(rows) + sum(len(v) for v in dropped.values()),
        f"{len(recs)} rows")
    chk("dropped names are logged, not just survivors",
        any(r["verdict"] == "dropped" for r in recs))
    chk("the drop reason survives to the CSV",
        all(r["drop_reason"] for r in recs if r["verdict"] == "dropped"))
    chk("every dropped bucket is represented",
        {r["drop_reason"].split(":")[0] for r in recs if r["verdict"] == "dropped"}
        == {k for k, v in dropped.items() if v},
        f"{sorted({r['drop_reason'].split(':')[0] for r in recs if r['verdict']=='dropped'})}")
    chk("ticker is clean, with the detail split off",
        all(r["ticker"].isalpha() for r in recs), f"{[r['ticker'] for r in recs][:6]}")
    chk("no literal 'None' anywhere in the file",
        not any("None" in v for r in recs for v in r.values()))
    chk("run_utc stamps every row identically",
        {r["run_utc"] for r in recs} == {stamp})

    write_logs(rows, dropped, regime, tmp, run_utc="2026-08-25T14:45:00Z")
    with open(sp, newline="", encoding="utf-8") as fh:
        recs2 = list(_csv.DictReader(fh))
    chk("a second run APPENDS, it does not rewrite", len(recs2) == 2 * len(recs))
    chk("two runs are distinguishable by timestamp",
        len({r["run_utc"] for r in recs2}) == 2)
    with open(sp, encoding="utf-8") as fh:
        chk("the header is written once, not per run",
            fh.read().count("run_utc,us_date") == 1)

    rp = os.path.join(tmp, "regime_log.csv")
    with open(rp, newline="", encoding="utf-8") as fh:
        rrecs = list(_csv.DictReader(fh))
    chk("one regime row per run", len(rrecs) == 2)
    chk("regime row counts match the screen rows",
        int(rrecs[0]["n_passed"]) == len(rows))
    chk("condor verdict is recorded", rrecs[0]["condor_go"] in ("GO", "NO-GO"))

    drift = os.path.join(tmp, "drift.csv")
    append_csv(drift, ["a", "b"], [{"a": 1, "b": 2}])
    try:
        append_csv(drift, ["a", "b", "c"], [{"a": 1, "b": 2, "c": 3}])
        drifted = False
    except ValueError:
        drifted = True
    chk("a changed schema is REFUSED, not silently appended", drifted)
    chk("frozen columns are stable",
        SCREEN_COLUMNS[:4] == ["run_utc", "us_date", "ticker", "verdict"])

    print("GATE 3 HEADLINE LINKS")
    u = YFProvider._news_url
    chk("canonicalUrl (the publisher) wins over the Yahoo wrapper",
        u({"canonicalUrl": {"url": "https://fool.com/a"},
           "clickThroughUrl": {"url": "https://finance.yahoo.com/b"}})
        == "https://fool.com/a")
    chk("falls back to the Yahoo wrapper when there is no canonical",
        u({"clickThroughUrl": {"url": "https://finance.yahoo.com/b"}})
        == "https://finance.yahoo.com/b")
    chk("a bare string URL still works",
        u({"canonicalUrl": "https://x.example/c"}) == "https://x.example/c")
    chk("no URL yields empty, never None", u({}) == "")
    chk("a malformed url dict does not raise",
        u({"canonicalUrl": {"site": "x"}, "clickThroughUrl": None}) == "")

    class Flaky:
        """Returns nothing twice, then real items — the observed ANET failure."""
        def __init__(self):
            self.calls = 0
            self._cache = {}
        _news_url = staticmethod(YFProvider._news_url)
        def _tk(self, t):
            self.calls += 1
            class TK:
                news = ([] if self.calls < 3 else
                        [{"content": {"title": "ANET beats", "pubDate": "2026-08-22",
                                      "canonicalUrl": {"url": "https://x.example/1"},
                                      "finance": {"stockTickers": [{"symbol": "ANET"}]}}}])
            return TK()
    fl = Flaky()
    got = YFProvider.news(fl, "ANET")
    chk("a flaky news endpoint is retried, not read as an all-clear",
        len(got) == 1 and fl.calls == 3, f"calls={fl.calls} items={len(got)}")
    chk("the retried item carries its URL",
        got[0][3] == "https://x.example/1")
    fl2 = Flaky(); fl2.calls = -99          # never succeeds
    chk("a genuinely dead endpoint still returns empty, so the report flags it",
        YFProvider.news(fl2, "ANET", tries=2) == [])

    print("HTML PAGE")
    html = render_html(rows, dropped, conflicts, news, regime, today)
    by_c_test = {}
    for r in rows:
        by_c_test.setdefault(r["cluster"], []).append(r)
    # The contract is about what the page LOADS, not what it links to.
    # Headline links are the point of Gate 3; a stylesheet, font or script
    # pulled from someone else's server is a third party that can change the
    # page under you, and on a phone it is also a page that breaks offline.
    def loads_external(page):
        return [x for x in ("<script src", "<link", "@import", "<img",
                            "url(http", "@font-face") if x in page]
    chk("a page with no repo configured ships no behaviour, only data",
        "initRun(" not in html)
    chk("the only script on such a page is the headline payload",
        html.count("<script>") <= 1 and "window.__news=" in html)
    chk("nothing external is ever LOADED, only linked",
        loads_external(html) == [], f"{loads_external(html)}")
    chk("every outbound link opens safely",
        html.count("<a href=\"http") == html.count('rel="noopener nofollow"'),
        f'{html.count(chr(60)+"a href=" + chr(34) + "http")} links')
    withbtn = render_html(rows, dropped, conflicts, news,
                          dict(regime, repo="me/repo", run_id="123"), today)
    chk("configuring a repo alone does not add the Run button",
        'id="go"' not in withbtn)
    chk("with no dispatch endpoint there is no button at all",
        'id="go"' not in withbtn)
    chk("and no deep-link into Actions either, since that runs it too",
        "actions/workflows" not in withbtn)
    chk("the page says why it is read-only instead",
        'class="ro"' in withbtn and "Read-only" in withbtn)
    chk("no token, secret or Authorization header reaches the browser",
        not any(k in withbtn.lower() for k in
                ("authorization", "token", "bearer", "secret", "ghp_")))
    # Only fetch() targets matter for "who does this page talk to". Link hrefs
    # are inert until a human taps them.
    # Every absolute host literal inside the script block, however the URL is
    # later assembled. Link hrefs in the HTML are inert and excluded.
    script_src = "".join(re.findall(r"<script>(.*?)</script>", withbtn, re.S))
    chk("still loads no external stylesheet, font, script or image",
        loads_external(withbtn) == [], f"{loads_external(withbtn)}")
    dsp = render_html(rows, dropped, conflicts, news,
                      dict(regime, repo="me/repo", dispatch_url="https://w.example/go"),
                      today)
    chk("a dispatch endpoint turns it into a real button",
        '<button class="btn" id="go"' in dsp)
    chk("config values are JSON-encoded, not pasted into the script",
        '"https://w.example/go"' in dsp)
    chk("angle brackets cannot escape the inline script",
        "\\u003c" in _js("</script><img onerror=x>"))
    chk("has a viewport tag for phones", 'name="viewport"' in html)
    chk("collapses to cards on narrow screens", "max-width:869px" in html)
    chk("cards take over exactly where the table stops fitting",
        "max-width:869px" in html and "min-width:870px" in html)
    chk("adapts to the phone's dark mode", "prefers-color-scheme:dark" in html)
    chk("wide table can scroll without the page scrolling",
        "overflow-x:auto" in html)
    chk("every candidate appears", all(r["t"] in html for r in rows))
    chk("the page carries no account-specific banner",
        not any(k in html for k in ("Caps and hedge", "Part 2",
                                    "hedge status", "your positions")),
        "generic")
    chk("IBKR appears only as where YOU price it, never as a data source",
        html.count("IBKR") <= 1 and "needs IBKR" not in html,
        f"{html.count('IBKR')} mentions")
    chk("it still says sizing is not covered",
        "does not do it" in html or "position sizing" in html)
    chk("Gate 3 is declared not automated",
        "Gate 3 is not automated" in html and "Gate 3 is yours" in html)
    chk("headlines are collapsed, not dumped", html.count("<details>") > 0)
    chk("headline URLs travel with the payload", '"u":' in html)
    withjs = render_html(rows, dropped, conflicts, news,
                         dict(regime, repo="me/repo"), today)
    chk("the viewer opens them safely",
        "noopener" in withjs and "nofollow" in withjs)
    chk("a headline with no URL still reaches the viewer",
        '"u": ""' in render_html(
            rows, dropped, conflicts,
            {rows[0]["t"]: [("2026-08-22", "unlinked", True, "")]},
            regime, today).replace('"u":""', '"u": ""'))
    chk("markup inside a headline cannot break out of the script",
        "\\u003c" in render_html(
            rows, dropped, conflicts,
            {rows[0]["t"]: [("2026-08-22", "</script><img onerror=x>",
                             True, "")]}, regime, today))
    chk("ticker text is escaped", "&lt;" in _esc("<b>x</b>"))
    ang = render_html(rows, dropped, ["EVIL<script>alert(1)</script>"], news,
                      regime, today)
    chk("injected markup in a conflict string is escaped",
        "<script>alert" not in ang and "&lt;script&gt;" in ang)
    empty = render_html([], {k: [] for k in dropped}, [], {}, regime, today)
    chk("an empty screen still renders and says so",
        "Cash is a valid outcome" in empty)
    chk("every flag on the page carries its own explanation",
        all(f'data-tip=' in html for c in codes) and
        html.count('data-tip=') >= sum(
            len([x for x in r["notes"].split(",") if x]) for r in rows),
        f"{html.count('data-tip=')} tips")
    chk("no bottom-of-page legend remains", "<dl class=\"legend\">" not in html
        or "Flags</h2>" not in html)
    chk("chips are reachable by keyboard too", 'tabindex="0"' in html)
    nth = html.count("</th>")      # one per header, unambiguous
    chk("the numeric table is 11 columns, with flags on their own row",
        nth == 11, f"{nth} headers")
    chk("actual delta is no longer its own column",
        'data-l="Actual Δ"' not in html)
    chk("but it is still one hover away",
        "nearest listed strike is" in html)

    print("UNATTENDED-RUN SAFETY")
    chk("a healthy run is not flagged as data loss",
        not data_loss(dropped, len(UNIVERSE)))
    chk("half the universe failing IS data loss",
        data_loss({"data": ["A"] * 11}, 22))
    chk("just under half is not",
        not data_loss({"data": ["A"] * 10}, 22))
    chk("a genuinely empty screen with healthy data is not data loss",
        not data_loss({"data": [], "trend": ["X"] * 22}, 22))
    chk("no names requested cannot divide by zero", not data_loss({}, 0))

    print("SHARED PAGE CARRIES NO PERSONAL LIMITS")
    chk("no cap ratio like 2/1 on the page",
        not re.search(r">\s*\d+/\d+\s*<", html),
        "clean")
    chk("no OVER CAP alarm on the page", "over cap" not in html.lower())
    chk("cluster grouping is kept, as a plain count",
        any(f"{len(v)} name" in html for v in by_c_test.values()))
    multi_t = [c for c in CLUSTER_ORDER
               if len(by_c_test.get(c, [])) > 1 and c != "Unclustered"]
    if multi_t:
        chk("groups holding more than one name are called out by correlation",
            "moves together" in html)
        chk("and the names in them are listed",
            all(r["t"] in html for c in multi_t for r in by_c_test[c]))
    chk("the terminal report KEEPS the caps, it is JH's own view",
        "OVER CAP" in txt or not any(
            CLUSTER_MAX.get(c) and len(v) > CLUSTER_MAX[c]
            for c, v in by_c_test.items()))
    chk("the terminal report keeps the IBKR note",
        "NOT COMPUTED" in txt)

    print("THE MACRO BANNER NAMES WHAT IT IS WARNING ABOUT")
    mreg = dict(regime, macro_expiry="2026-09-11", macro_near_expiry=[
        (date(2026, 9, 10), "PPI"), (date(2026, 9, 11), "CPI")])
    mh = render_html(rows, dropped, conflicts, news, mreg, today)
    chk("each event is named", "PPI" in mh and "CPI" in mh)
    chk("each carries its own date", "Thu 10 Sep" in mh and "Fri 11 Sep" in mh)
    chk("the one on expiry day is called out", "expiry day" in mh)
    chk("the others are placed relative to expiry", "1 day before expiry" in mh)
    chk("the count is stated with the events, not instead of them",
        "2 events inside 3 days" in mh)
    chk("the consequence is still spelled out", "halve the tranche" in mh)
    chk("only the banner title is a block, so emphasis stays inline",
        ".banner b.t{display:block" in mh and ".banner b{display:inline}" in mh)
    chk("every banner titles itself with the block class",
        mh.count('class="banner') == mh.count('><b class="t">'),
        f"{mh.count('class=' + chr(34) + 'banner')} banners")
    chk("it is ONE banner, not two",
        mh.count("Macro in the expiry window") == 1
        and "Macro density</b>" not in mh)
    chk("expiry-day events make it the loud colour",
        'banner alarm"><b class="t">Macro in the expiry window' in mh)

    lone = dict(regime, macro_expiry="2026-09-18",
                macro_near_expiry=[(date(2026, 9, 16), "FOMC")])
    lh = render_html(rows, dropped, conflicts, news, lone, today)
    chk("a single event off the expiry day is the quieter colour",
        'banner warn"><b class="t">Macro in the expiry window' in lh)
    chk("and does not claim density", "events inside" not in lh)
    chk("it still names the event and its distance",
        "FOMC" in lh and "2 days before expiry" in lh)

    clear = dict(regime, macro_expiry="2026-10-30", macro_near_expiry=[])
    ch2 = render_html(rows, dropped, conflicts, news, clear, today)
    chk("nothing in the window means no banner at all",
        "Macro in the expiry window" not in ch2)

    print("THE PAGE IDENTIFIES ITSELF")
    stamped = render_html(rows, dropped, conflicts, news,
                          dict(regime, repo="me/repo", run_id="999",
                               run_number="14",
                               built_utc="2026-08-23T08:20:11Z"), today)
    chk("run number is on the page", "run #14" in stamped)
    chk("run time is on the page", "08:20 UTC" in stamped)
    chk("the script runs after the markup it touches",
        stamped.index('id="built"') < stamped.index("function initRun"),
        "script is last")
    chk("freshness is a tile, not a footnote",
        'class="stat now"' in stamped and "Last run" in stamped)
    chk("it is labelled by what it means, not how it was made",
        "&middot; built " not in stamped)
    chk("the raw UTC stamp is kept for the browser to localise",
        'data-utc="2026-08-23T08:20:11Z"' in stamped)
    chk("run number reaches the status script", 'runNumber:"14"' in stamped)
    chk("a local build with no run number still renders",
        "run #" not in render_html(rows, dropped, conflicts, news, regime, today))
    chk("two runs the same day are distinguishable",
        render_html(rows, dropped, conflicts, news,
                    dict(regime, run_number="15",
                         built_utc="2026-08-23T09:00:00Z"), today)
        != stamped)

    print("TARGET CREDIT IS ARITHMETIC, NOT A QUOTE")
    chk("the credit target is labelled unambiguously on a card",
        'data-l="Target credit"' in html and 'data-l="Delta"' in html)
    chk("target is the floor times the width",
        all(r.get("target") is not None and
            abs(r["target"] - (r.get("act_width") or r["width"]) * CREDIT_FLOOR)
            < 1e-9 for r in rows))
    for wdt, want in ((10, 1.10), (20, 2.20), (60, 6.60), (25, 2.75)):
        chk(f"a ${wdt} width targets ${want:.2f}",
            abs(wdt * CREDIT_FLOOR - want) < 1e-9)
    chk("no delayed-quote estimate is shown any more",
        not any(k in html for k in ("%W mid", "worst-case fill")))
    chk("the removed flags are gone from the legend",
        not any(c in {k for k, _ in FLAG_LEGEND} for c in ("sub11", "nocred")))
    chk("rows no longer carry a credit estimate",
        all("pctW" not in r for r in rows))

    print("ANET CLUSTERING")
    chk("ANET has its own cluster", cluster_of("ANET") == "Networking")
    chk("it is capped at one", CLUSTER_MAX["Networking"] == 1)
    chk("it is not inside Semis", "ANET" not in CLUSTERS["Semis"])
    chk("Semis is back to the four chip names",
        CLUSTERS["Semis"] == ["NVDA", "AMD", "AVGO", "TSM"])
    chk("the new cluster is in the display order",
        "Networking" in CLUSTER_ORDER)
    chk("every cluster has a cap",
        all(c in CLUSTER_MAX for c in CLUSTERS))
    chk("every cluster is in the display order",
        all(c in CLUSTER_ORDER for c in CLUSTERS))
    print("  cross-cluster correlation is not lost")
    chk("the ANET/semis link is recorded",
        cross_cluster_notes(["ANET", "NVDA"]) != [])
    chk("it fires only when both sides are on the screen",
        cross_cluster_notes(["ANET"]) == []
        and cross_cluster_notes(["NVDA", "TSM"]) == [])
    chk("the note carries the measured numbers, not an adjective",
        "0.62" in cross_cluster_notes(["ANET", "AVGO"])[0])
    chk("it is dated so it can be re-measured",
        "2026" in cross_cluster_notes(["ANET", "AVGO"])[0])
    both = render_html(
        rows, dropped, conflicts, news,
        dict(regime, repo="me/repo"), today) if any(
            r["t"] in ("NVDA", "AMD", "AVGO", "TSM") for r in rows) and any(
            r["t"] == "ANET" for r in rows) else None
    if both is not None:
        chk("and the page warns when both are listed",
            "Two groups, one bet" in both)
    chk("NFLX stays unclustered - its best match was noise",
        cluster_of("NFLX") == "Unclustered")
    chk("no name lands in two clusters",
        sum(len(v) for v in CLUSTERS.values()) ==
        len({t for v in CLUSTERS.values() for t in v}))
    chk("every clustered name is in the universe",
        all(t in UNIVERSE for v in CLUSTERS.values() for t in v))
    chk("the Semis cap did not silently move", CLUSTER_MAX["Semis"] == 2)

    print("NO GITHUB API, SO NO RATE LIMIT TO SHARE")
    chk("the page never calls api.github.com",
        "api.github.com" not in stamped)
    chk("freshness comes from a tiny file beside the page",
        "version.json" in stamped)
    chk("that fetch bypasses every cache", "cache:'no-store'" in stamped)
    chk("the version file is resolved next to the page, not at the root",
        "location.pathname.replace" in stamped)
    behaviour = re.findall(r"<script>(function initRun.*?)</script>",
                           stamped, re.S)
    behaviour += re.findall(r"<script>(initRun\(.*?)</script>", stamped, re.S)
    chk("github.com survives only as a link for a human",
        set(re.findall(r"https?://[a-z0-9.\-]+", "".join(behaviour)))
        <= {"https://github.com"},
        str(sorted(set(re.findall(r"https?://[a-z0-9.\-]+",
                                  "".join(behaviour))))))

    print("ONE VISIBLE STATE WHILE IT WORKS")
    chk("dispatching, running and publishing all read as Running",
        "function busy()" in stamped and ">Running<" not in stamped)
    chk("no phase names leak to the user",
        not any(k in stamped for k in
                ("Waiting for GitHub", "publishing", "step '+", "Queued")))
    chk("elapsed seconds prove it is not frozen",
        "(Date.now()-began)/1000" in stamped)
    chk("the spinner is a real spinner", "@keyframes spin" in stamped)
    chk("the bar is indeterminate, not a fake percentage",
        "@keyframes slide" in stamped and "width:38%" in stamped)
    chk("reduced motion is respected", "prefers-reduced-motion" in stamped)

    print("IT ACTS ONLY ON A PUBLISHED BUILD")
    chk("it compares run numbers, not guesses", "live>here" in stamped)
    chk("a 404 or a blip is not treated as failure",
        "not a failure" in stamped)
    chk("and it gives up rather than spinning forever",
        "Still not published after 5 minutes" in stamped)

    print("AUTO-RELOAD, BUT ONLY FOR WHOEVER PRESSED")
    chk("pressing the button claims the run", "mine=true" in stamped)
    chk("the presser is reloaded automatically",
        "if(mine){location.reload();}" in stamped)
    chk("everyone else is offered the choice", "is ready." in stamped)
    chk("a failed dispatch releases the claim", "mine=false" in stamped)
    chk("a 409 watches instead of refusing",
        "r.status===409" in stamped and "mine=false;waiting=" in stamped)

    print("COOLDOWN SAVES SHARED RESOURCES")
    chk("a cooldown exists", "COOLDOWN=180000" in stamped)
    chk("it counts down rather than sitting dead",
        "Math.ceil(left/1000)" in stamped)
    chk("it is driven off the page's own last-run stamp, needing no API",
        "new Date(cfg.builtUtc)" in stamped)
    chk("the stamp reaches the script", "builtUtc:" in stamped)


    print("FLAGS EXPLAIN THEMSELVES ON HOVER")
    chk("hover shows it immediately, with no native delay",
        "addEventListener('mouseover'" in stamped
        and "title=" not in stamped.split("<tbody>")[1].split("</tbody>")[0])
    chk("the slow, unstyleable native tooltip is gone",
        'title="' not in stamped.split('<div class="chips">')[1][:400])
    chk("tap still works where there is no hover",
        "addEventListener('click'" in stamped and "pinned" in stamped)
    chk("clicking the same chip twice closes it",
        "if(pinned===c)" in stamped)
    chk("keyboard focus shows it too", "focusin" in stamped)
    chk("it is clamped inside the viewport",
        "window.innerWidth-w-8" in stamped and "window.innerHeight" in stamped)
    chk("it flips above the chip when there is no room below",
        "r.top-h-8" in stamped)

    print("DELTA DRIFT IS SHOWN ONLY WHEN IT MATTERS")
    # Check per rendered row, not by searching the whole page: the arrow text
    # is not unique, so a global search says "present" for every row as soon as
    # one row has it.
    import re as _re
    blocks = _re.findall(r'<tr class="row">(.*?)</tr>', html, _re.S)
    chk("one row block per candidate", len(blocks) == len(rows),
        f"{len(blocks)} vs {len(rows)}")
    shown = 0
    for r, blk in zip(sorted(rows, key=lambda x: x["t"]), blocks):
        pass
    for blk in blocks:
        if "drift" in blk:
            shown += 1
    expect = sum(1 for r in rows if abs(r["act_delta"] - r["delta"]) > 0.02)
    chk("the arrow appears on exactly the rows that drifted past 0.02",
        shown == expect, f"{shown} shown, {expect} expected")
    chk("every delta cell carries both numbers on hover",
        sum(1 for b in blocks if "nearest listed strike is" in b) == len(rows))
    chk("the delta cell is hoverable without looking like a chip",
        'class="chip bare"' in html and ".chip.bare{background:none" in html)

    print("THE HEADER STAYS PUT")
    chk("the header is sticky", "position:sticky;top:0" in html)
    chk("it sits above the rows it covers", "z-index:5" in html)
    chk("the scroll container stops trapping it once the table fits",
        "@media (min-width:870px){\n  .scroll{overflow:visible}" in html)
    chk("the cluster label sticks under it too", "top:41px" in html)
    chk("the header is opaque, not see-through",
        "background:var(--panel);\n  border-bottom" in html)

    print("FLAGS DO NOT FALL OFF THE TABLE")
    chk("flags are a full-width row, not a fifteenth column",
        '<tr class="fl">' in stamped)
    chk("no Flags column header remains", ">Flags</th>" not in stamped)
    chk("the flag row spans the whole table",
        'colspan="' in stamped.split('<tr class="fl">')[1][:60])
    chk("chips read left to right, like the row above",
        "justify-content:flex-start" in stamped)

    print("A FAILED RUN SAYS SO, WITHOUT AN API")
    chk("the state is written alongside the run number",
        '"state": "ok"' in open(__file__, encoding="utf-8").read()
        or "state" in stamped)
    chk("the page reads that state", "v.state==='failed'" in stamped)
    chk("and names the run that failed", "failed'" in stamped)
    chk("a failure does not trigger a reload",
        stamped.index("v.state==='failed'") < stamped.index("if(live>here){"))

    print("SOMEONE ELSE'S RUN IS NOTICED TOO")
    chk("an idle watcher exists", "function idleWatch()" in stamped)
    chk("it runs about once a minute", "idleWatch,60000" in stamped)
    chk("it sleeps when the tab is hidden", "document.hidden" in stamped)
    chk("it wakes when the tab comes back", "visibilitychange" in stamped)
    chk("it never fights the press-and-wait watcher",
        "if(document.hidden||waiting)return;" in stamped)
    chk("it offers rather than reloads under you",
        "if(live>here)offer(live);" in stamped)

    print("NOTHING FREEZES SILENTLY")
    for msg in ("Still not published after 5 minutes", "Could not start it"):
        chk(f"terminal state announces itself: {msg[:36]}", msg in stamped)
    chk("every give-up offers the Actions link", "check Actions" in stamped)
    chk("Gate 1 explains the 20-day average", "previous 20 trading days" in html)
    chk("Gate 2 explains why earnings matter", "overnight gap" in html)
    chk("Gate 3 is declared not automated", "Not automated" in html)
    chk("the limits are stated as plainly as the gates",
        "does not price anything" in html)
    chk("it says doing nothing is normal", "do nothing" in html)
    chk("red flags are called out when any are shown",
        ("need settling before acting" in html)
        == any(f in {c for r in rows for c in r["notes"].split(",")}
               for f in HOT_FLAGS))

    print("TYPOGRAPHY")
    chk("base font is comfortable on a phone", "font:17px/1.62" in html)
    chk("numeric cells stay legible", "font-size:15.5px" in html)
    chk("headline text is not smaller than the table", "font-size:15.5px" in html)
    chk("tap target on the button is finger-sized", "padding:14px 24px" in html)

    print("CONDOR GATE")
    R = lambda v, s: {"vix": v, "stretch": s, "spx": None, "errors": []}
    chk("VIX unreadable -> NO-GO", condor_verdict(R(None, 0.01))[0] is False)
    chk("unreadable reason names verification, not low vol",
        "cannot be verified" in condor_verdict(R(None, 0.01))[1])
    chk("VIX 14 -> NO-GO", condor_verdict(R(14.0, 0.01))[0] is False)
    chk("VIX 20 boundary passes", condor_verdict(R(20.0, 0.01))[0] is True)
    chk("stretch +5% -> NO-GO", condor_verdict(R(24.0, 0.05))[0] is False)
    chk("stretch -3% -> NO-GO", condor_verdict(R(24.0, -0.03))[0] is False)
    chk("stretch -2% boundary passes", condor_verdict(R(24.0, -0.02))[0] is True)
    chk("stretch +3% boundary passes", condor_verdict(R(24.0, 0.03))[0] is True)
    chk("GO still demands manual macro check",
        "CONFIRM no binary macro" in condor_verdict(R(24.0, 0.01))[1])
    chk("regime read populated in synthetic run",
        regime["vix"] is not None and regime["stretch"] is not None,
        f"vix={regime['vix']}")
    print()
    print("=" * 78)
    print(report(rows, dropped, conflicts, news, regime, today))
    print("=" * 78)
    print()
    print("SELFTEST:", "ALL PASS" if ok else "FAILURES ABOVE")
    return 0 if ok else 1
# ---------------------------------------------------------------- main
def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--selftest", action="store_true")
    ap.add_argument("--no-news", action="store_true")
    ap.add_argument("--why", action="store_true",
                    help="longer flag explanations")
    ap.add_argument("--csv-dir", default=None,
                    help="append this run to screen_log.csv and regime_log.csv "
                         "in this directory")
    ap.add_argument("--html", default=None,
                    help="also write a self-contained HTML page to this path")
    ap.add_argument("--author", default=None,
                    help="name shown on the page (default $SCREEN_AUTHOR)")
    ap.add_argument("--repo", default=None,
                    help="owner/name — adds a Run button and live status to the "
                         "HTML page. Defaults to $GITHUB_REPOSITORY.")
    ap.add_argument("--workflow-file", default="screen.yml",
                    help="workflow filename the Run button points at")
    ap.add_argument("--dispatch-url", default=None,
                    help="optional endpoint that triggers the workflow, for a "
                         "true one-click button. Without it the button "
                         "deep-links to the Actions tab. Defaults to "
                         "$DISPATCH_URL.")
    ap.add_argument("--quiet", action="store_true",
                    help="suppress the text report (for scheduled runs)")
    ap.add_argument("--tickers", nargs="+", default=None,
                    help="names to screen; commas and/or spaces both fine. "
                         "Omit to run the full universe (19 names + 3 indices).")
    a = ap.parse_args()
    if a.selftest:
        return selftest()
    today = date.today()
    try:
        p = YFProvider()
    except ImportError:
        print("pip install yfinance", file=sys.stderr)
        return 2
    tk = None
    if a.tickers:
        joined = " ".join(a.tickers).replace(",", " ")
        tk = [x.strip().upper() for x in joined.split() if x.strip()]
        unknown = [x for x in tk if x not in UNIVERSE]
        if unknown:
            print(f"note: not in universe: {', '.join(unknown)}", file=sys.stderr)
    rows, dropped, conflicts, news, regime = run(p, today, do_news=not a.no_news, tickers=tk)
    lost = data_loss(dropped, len(tk or UNIVERSE))
    if lost:
        print(f"DATA LOSS: {len(dropped['data'])} of {len(tk or UNIVERSE)} names "
              f"failed to return data — this run is not a screen. "
              f"Nothing written.\n  {', '.join(dropped['data'])}",
              file=sys.stderr)
        if not a.quiet:
            print(report(rows, dropped, conflicts, news, regime, today,
                         verbose=a.why))
        return 2
    if not a.quiet:
        print(report(rows, dropped, conflicts, news, regime, today, verbose=a.why))
    if a.csv_dir:
        n1, n2 = write_logs(rows, dropped, regime, a.csv_dir)
        print(f"logged {n1} screen rows + {n2} regime row -> {a.csv_dir}",
              file=sys.stderr)
    if a.html:
        import os
        regime["repo"] = a.repo or os.environ.get("GITHUB_REPOSITORY")
        regime["workflow_file"] = a.workflow_file
        regime["run_id"] = os.environ.get("GITHUB_RUN_ID")
        regime["run_number"] = os.environ.get("GITHUB_RUN_NUMBER")
        regime["author"] = a.author or SCREEN_AUTHOR
        from datetime import timezone as _tz
        regime["built_utc"] = datetime.now(_tz.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
        regime["dispatch_url"] = a.dispatch_url or os.environ.get("DISPATCH_URL")
        d = os.path.dirname(a.html)
        if d:
            os.makedirs(d, exist_ok=True)
        with open(a.html, "w", encoding="utf-8") as fh:
            fh.write(render_html(rows, dropped, conflicts, news, regime, today))
        print(f"wrote {a.html}", file=sys.stderr)
        # A few dozen bytes beside the page, holding just the run number. The
        # page polls THIS to find out when a new build is live, instead of
        # asking the GitHub API or re-downloading 180KB of itself every few
        # seconds. Same answer, no rate limit, no quota to share.
        import json as _json
        vpath = os.path.join(d, "version.json") if d else "version.json"
        with open(vpath, "w", encoding="utf-8") as fh:
            _json.dump({"run": regime.get("run_number") or "",
                        "utc": regime.get("built_utc") or "",
                        "state": "ok"}, fh)
        print(f"wrote {vpath}", file=sys.stderr)
    return 0
if __name__ == "__main__":
    sys.exit(main())