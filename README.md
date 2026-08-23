# put-spread-screener

Put-credit-spread screen, gates 1–3 of workflow 2-1-5. Market-data half only —
no broker account, nothing about your positions or exposure.

Runs **only when you press the button**. There is no schedule.

- **Page:** `docs/index.html` → your GitHub Pages URL
- **History:** `runs/screen_log.csv`, `runs/regime_log.csv`, appended per run
- **Archive:** `docs/archive/YYYY-MM-DD-HHMM.html`, one frozen page per run

## Setup (once)

1. Push this repo. **Public** — Pages on private repos needs a paid plan.
2. **Settings → Secrets and variables → Actions → New repository secret**
   - Name: `BLS_CONTACT_EMAIL`
   - Value: any email address you own.

   There is nothing to sign up for and no account anywhere. bls.gov returns
   **403** to any User-Agent that looks like a browser and **200** to one
   containing an email address — they want scripted callers identifiable, and
   block the ones pretending to be people. The address goes into the request
   header sent to bls.gov and nowhere else. Nothing is ever sent *to* it, so a
   throwaway is fine.

   If you skip this the screen still works: the built-in placeholder is
   address-shaped, and BLS only checks the shape. But it is unreachable, which
   is the one thing the header is for, and a filter that loose is one BLS could
   tighten without warning. The run tells you when it is unset.
3. **Actions → screen → Run workflow.** Do this before enabling Pages: it
   writes the first real page.
4. **Settings → Pages → Deploy from a branch → `main` / `docs`**

Your URL is `https://<user>.github.io/<repo>/`. Bookmark it on your phone.

## The button

The page carries a **Run screen** button and a live status line that polls the
public GitHub API — no token, so nothing secret is shipped to the browser.

Out of the box the button opens the Actions tab, where you press *Run workflow*
(GitHub does the authenticating). The page then shows `Running · 34s`, and
offers **Reload** when new results land. That is two extra taps.

### True one-click (optional, free)

To make the button fire the run directly, you need something that holds a
token — it cannot live in the page, because a token in a page anyone can view
is a token anyone can use. A Cloudflare Worker on the free tier does it in
about fifteen lines:

```js
export default {
  async fetch(req, env) {
    const cors = { "Access-Control-Allow-Origin": env.ORIGIN,
                   "Access-Control-Allow-Methods": "POST, OPTIONS" };
    if (req.method === "OPTIONS") return new Response(null, { headers: cors });
    if (req.method !== "POST") return new Response("no", { status: 405, headers: cors });
    const r = await fetch(
      "https://api.github.com/repos/OWNER/REPO/actions/workflows/screen.yml/dispatches",
      { method: "POST",
        headers: { Authorization: `Bearer ${env.GH_TOKEN}`,
                   Accept: "application/vnd.github+json",
                   "User-Agent": "pcs-dispatch" },
        body: JSON.stringify({ ref: "main" }) });
    return new Response(r.ok ? "ok" : await r.text(),
                        { status: r.ok ? 202 : 502, headers: cors });
  }
};
```

- `GH_TOKEN` — a **fine-grained** PAT scoped to this one repo with
  *Actions: read and write* and nothing else. Store it as a Worker secret.
- `ORIGIN` — your Pages origin, so other sites cannot use your Worker.
- Then set repository **variable** `DISPATCH_URL` to the Worker URL (a
  variable, not a secret — it ends up in the page either way).

Anyone who can open the page can then start a run. That is the point if you are
sharing it, and the reason to scope the token to exactly one workflow.

## Local

```
python pcs_screen.py                 # compact screen
python pcs_screen.py --why           # per-row explanations, all headlines
python pcs_screen.py --no-news       # skip Gate 3 pull, faster
python pcs_screen.py --tickers TSM ANET
python pcs_screen.py --selftest      # offline, ~1s
python pcs_screen.py --quiet --csv-dir runs --html docs/index.html
```

Set `BLS_CONTACT_EMAIL` in your shell for local runs too.

## Exit codes

| code | meaning |
|---|---|
| 0 | ran; the screen is valid, including a legitimately empty one |
| 1 | bad arguments, or yfinance missing |
| 2 | **data loss** — half the universe returned nothing. Nothing written. |

Code 2 exists because "nothing passed" and "every feed is down" print
identically. On a page you read on your phone, that difference matters more
than anything else in the run. On a code 2 the job goes red and the previous
page is left standing.

## Reading the log

```python
import pandas as pd
s = pd.read_csv("runs/screen_log.csv", parse_dates=["run_utc"])

s[s.verdict == "passed"].groupby("ticker").size()          # how often shown
s[s.drop_reason.str.startswith("trend", na=False)]         # trend vetoes
s[s.flags.str.contains("knife", na=False)]                 # Gate 1 knife-edges
s.pivot_table(index="us_date", columns="ticker",
              values="verdict", aggfunc="first")           # day-by-day grid
```

Dropped names are logged with their reason. That half is the point: the
question is not only whether the screen was right about what it showed, but
what it hid and why.

## What this does not do

Caps, hedge status, exposure, Step 6b expiry checks and the fill/hold logs all
need IBKR and are **not** here. Nothing in this repo knows your account exists.
The page says so on every render.

Gate 3 is printed, never applied — headlines are for a human to veto on.
The 11%W credit floor is checked by hand at the ticket, not here.

Not financial advice.
