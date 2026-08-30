#!/usr/bin/env python3
"""
One-time (or occasional) helper: pulls each ticker's logo from Wikipedia/
Wikimedia Commons — free, no API key, no signup — and bakes the results into
logos.json as small base64 PNG data URIs.

Why this exists rather than a live logo API in the page itself: Clearbit's
free logo API (the old default answer to "how do I get a company logo") is
being sunset in 2026, and every replacement found (Logo.dev, CompaniesLogo,
LogoKit) wants an account and an API key. Putting a key in a page anyone can
view means anyone can lift and use it. This universe is small and fixed
(~19 names) and rarely changes, so fetching once and committing the result
is both simpler and more durable than a live dependency — the page keeps
its "nothing external is ever loaded" guarantee, and a dead API key can
never turn every ticker into a broken image icon.

Why the infobox field, not "any image with 'logo' in its name": tried that
first. It returned Wikipedia's own Commons-logo.svg for JNJ and META (a
sitewide housekeeping icon, not a company mark), Apple's 1970s rainbow logo
for AAPL, and Bear Stearns' logo for JPM (mentioned in a "history" section,
matched anyway because the filename contains the word "logo"). The infobox
`logo=` field is the one thing on the page an editor curated specifically
to mean "this is the company's current logo" — asking for that instead of
guessing from a filename fixed all four.

Run this locally whenever UNIVERSE changes (a name added or dropped):
    python3 fetch_logos.py
It writes logos.json beside itself, MERGING with whatever is already there
(so a ticker fetched once is never re-fetched, and a failure on one ticker
never loses the rest). Commit the result — pcs_screen.py reads it at build
time; no network involved there at all.

A shared or heavily-used connection can get 429'd by Wikimedia's rate
limiter even at the default 1.5s/1.0s pacing below. If that happens, re-run
this later or from a different connection — already-fetched tickers are
skipped, so a re-run only chases what's still missing.
"""
import base64
import json
import os
import re
import sys
import time
import urllib.request
import urllib.parse

UA_CONTACT_PLACEHOLDER = "set-LOGO_FETCH_CONTACT_EMAIL@example.invalid"
UA_CONTACT = os.environ.get("LOGO_FETCH_CONTACT_EMAIL", UA_CONTACT_PLACEHOLDER)
if UA_CONTACT == UA_CONTACT_PLACEHOLDER:
    print(f"Note: LOGO_FETCH_CONTACT_EMAIL is not set, so requests go out "
          f"identifying as '{UA_CONTACT}'. Set that env var to your own "
          f"address first if you'd rather Wikimedia see a real contact.",
          file=sys.stderr)
UA = f"PutSpreadScreener/1.0 (personal project; contact {UA_CONTACT})"
API = "https://en.wikipedia.org/w/api.php"
OUT = "logos.json"

# Ticker -> the Wikipedia article that carries the company's own logo in its
# infobox. Hand-picked once rather than guessed, so a redirect or a
# disambiguation page can never silently pull the wrong company's mark.
# Index funds (SPY/QQQ/IWM) are left out on purpose — a logo would suggest
# they are companies, and they aren't.
WIKI_TITLE = {
    "AAPL": "Apple Inc.", "AMD": "Advanced Micro Devices",
    "AMZN": "Amazon (company)", "ANET": "Arista Networks",
    "AVGO": "Broadcom Inc.", "CRWD": "CrowdStrike",
    "GOOGL": "Alphabet Inc.", "JNJ": "Johnson & Johnson",
    "JPM": "JPMorgan Chase", "LLY": "Eli Lilly and Company",
    "META": "Meta Platforms", "MSFT": "Microsoft",
    "NFLX": "Netflix", "NVDA": "Nvidia",
    "PANW": "Palo Alto Networks", "PLTR": "Palantir Technologies",
    "TSLA": "Tesla, Inc.", "TSM": "TSMC", "V": "Visa Inc.",
}


def _get(params):
    url = API + "?" + urllib.parse.urlencode(params)
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=20) as r:
        return json.load(r)


def infobox_logo_file(title):
    """The exact file an editor put in the infobox's `logo=` field."""
    data = _get({"action": "parse", "page": title, "prop": "wikitext",
                 "section": 0, "format": "json"})
    if "error" in data:
        return None
    wikitext = data.get("parse", {}).get("wikitext", {}).get("*", "")
    m = re.search(r"\|\s*logo\s*=\s*([^\n|]+)", wikitext, re.I)
    if not m:
        return None
    name = m.group(1).strip()
    name = re.sub(r"^\[\[(?:File|Image):", "", name, flags=re.I)
    name = name.split("]]")[0].split("|")[0].strip()
    return name if name else None


def fetch_data_uri(file_name, width=160):
    data = _get({"action": "query", "titles": f"File:{file_name}",
                 "prop": "imageinfo", "iiprop": "url", "iiurlwidth": width,
                 "format": "json"})
    pages = data.get("query", {}).get("pages", {})
    for p in pages.values():
        info = p.get("imageinfo")
        if not info:
            continue
        url = info[0].get("thumburl") or info[0].get("url")
        req = urllib.request.Request(url, headers={"User-Agent": UA})
        with urllib.request.urlopen(req, timeout=20) as r:
            raw = r.read()
        ctype = "image/png" if url.lower().endswith(".png") else "image/png"
        return f"data:{ctype};base64," + base64.b64encode(raw).decode()
    return None


def main():
    out = {}
    if os.path.exists(OUT):
        with open(OUT, encoding="utf-8") as fh:
            out = json.load(fh)
    todo = [(t, title) for t, title in WIKI_TITLE.items() if t not in out]
    if not todo:
        print("logos.json already has every ticker.", file=sys.stderr)
        return
    failed = []
    for i, (ticker, title) in enumerate(todo):
        if i:
            time.sleep(1.5)
        try:
            file_name = infobox_logo_file(title)
            if not file_name:
                failed.append(f"{ticker}: no logo= field found on {title!r}")
                continue
            time.sleep(1.0)
            uri = fetch_data_uri(file_name)
            if not uri:
                failed.append(f"{ticker}: found {file_name!r} but couldn't read its URL")
                continue
            out[ticker] = uri
            print(f"  {ticker:<6} <- {file_name}", file=sys.stderr)
        except Exception as e:
            failed.append(f"{ticker}: {e}")
    with open(OUT, "w", encoding="utf-8") as fh:
        json.dump(out, fh, indent=1, sort_keys=True)
    print(f"\nwrote {OUT}: {len(out)}/{len(WIKI_TITLE)} logos total", file=sys.stderr)
    if failed:
        print("Missing this run — the page works fine without these, just no "
              "icon for them yet. Re-run later to retry:", file=sys.stderr)
        for f in failed:
            print(f"  {f}", file=sys.stderr)


if __name__ == "__main__":
    main()
