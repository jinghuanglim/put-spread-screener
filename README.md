# put-spread-screener

Put-credit-spread screen, gates 1–3 of workflow 2-1-5. Market-data half only —
no broker account, nothing about your positions or exposure.

Runs **only when you press the button**. There is no schedule.

- **Page:** `docs/index.html` → your GitHub Pages URL
- **Worker:** `worker/` → optional, makes the button work for people who do
  not have access to your GitHub account
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

It works in one of two modes, chosen automatically:

| `DISPATCH_URL` set? | Button | Who can use it |
|---|---|---|
| no | opens the Actions tab | only people with write access to this repo |
| yes | starts the run directly | anyone who can open the page |

If you are sharing this with anyone, you want the second mode. Setting it up is
below and takes about ten minutes, once.

### Why the page cannot just do it

Starting a workflow needs a GitHub token. A token in a page anyone can view is
a token anyone can use, and there is no way to hide one in client-side
JavaScript — "obfuscated" is not "hidden". So the token has to live somewhere
the browser cannot read, and something has to sit between the two. That is all
the Worker in `worker/` is.

### Setting up the one-click button

**1 — Make a token.** GitHub → Settings (your account, not the repo) →
Developer settings → Personal access tokens → **Fine-grained tokens** →
Generate new token.

- Repository access: **Only select repositories** → this repo alone
- Permissions → Repository permissions → **Actions: Read and write**
- Nothing else. Not contents, not workflows.
- Expiration: your call; the button stops working when it lapses.

Copy the token — it is shown once.

**2 — Edit the Worker.** In `worker/worker.js`, set `OWNER_REPO` to
`yourname/put-spread-screener`.

**3 — Deploy it.**

```
cd worker
npx wrangler login
npx wrangler secret put GH_TOKEN     # paste the token when prompted
npx wrangler deploy
```

Set `ORIGIN` in `wrangler.toml` to your Pages origin
(`https://yourname.github.io`, no trailing path) before deploying, or the
Worker will refuse the browser's request. Deploy prints the Worker URL.

**4 — Point the page at it.** Repo → Settings → Secrets and variables →
Actions → **Variables** tab → New repository variable:

- Name: `DISPATCH_URL`
- Value: the Worker URL

A variable, not a secret — it ends up in the published page either way, and
pretending otherwise would be theatre. It is a URL that starts a run; that is
all it can do.

**5 — Run the workflow once** so the page rebuilds with the real button.

### What a stranger can do with it

Start a screen. That is the whole surface. The token cannot push, cannot read
your other repos, cannot see the secret. The Worker refuses requests from other
origins, and refuses to queue a second run while one is already going, so the
button cannot be used to pile up runs or spam the log.

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
