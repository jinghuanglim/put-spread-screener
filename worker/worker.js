/**
 * Dispatches the screen workflow on behalf of anyone who opens the page.
 *
 * The page cannot do this itself. Triggering a workflow needs a GitHub token,
 * and a token in a page anyone can view is a token anyone can use — including
 * to push to the repo, if it is scoped that widely. This Worker is the smallest
 * thing that can hold the token out of reach: the browser POSTs here with no
 * credentials at all, and only this code ever sees the secret.
 *
 * Deploy notes are in ../README.md. Two bindings:
 *   GH_TOKEN  (secret)   fine-grained PAT, THIS repo only, Actions: read+write
 *   ORIGIN    (variable) your Pages origin, e.g. https://you.github.io
 */

const OWNER_REPO = "jinghuanglim/put-spread-screener";        // <-- edit
const WORKFLOW = "screen.yml";
const REF = "main";
const UA = "pcs-dispatch";

function cors(origin) {
  return {
    "Access-Control-Allow-Origin": origin,
    "Access-Control-Allow-Methods": "POST, OPTIONS",
    "Access-Control-Max-Age": "86400",
    "Vary": "Origin",
  };
}

async function gh(path, env, init = {}) {
  return fetch(`https://api.github.com/repos/${OWNER_REPO}${path}`, {
    ...init,
    headers: {
      Authorization: `Bearer ${env.GH_TOKEN}`,
      Accept: "application/vnd.github+json",
      "X-GitHub-Api-Version": "2022-11-28",
      "User-Agent": UA,
      ...(init.headers || {}),
    },
  });
}

export default {
  async fetch(req, env) {
    const allowed = env.ORIGIN || "*";
    const h = cors(allowed);

    if (req.method === "OPTIONS") return new Response(null, { headers: h });
    if (req.method !== "POST")
      return new Response("POST only", { status: 405, headers: h });

    // Same-origin enforcement. A browser cannot forge Origin, so this stops
    // another site from quietly using your Worker as a free button. It is not
    // a defence against curl — nothing here is, and nothing here needs to be:
    // the worst a determined stranger can do is start a run that reads public
    // market data.
    const origin = req.headers.get("Origin");
    if (allowed !== "*" && origin && origin !== allowed)
      return new Response("bad origin", { status: 403, headers: h });

    // Refuse to pile runs on top of each other.
    //
    // The first version of this filtered on `status=in_progress` and
    // `status=queued`, and caught nothing: three POSTs 40 seconds apart all
    // sailed through. Two reasons. A run blocked by the workflow's own
    // `concurrency` group reports as `pending`, which neither filter matches,
    // and a freshly dispatched run takes a few seconds to appear in the runs
    // list at all — so even a correct status filter loses the race against a
    // double-tap.
    //
    // Testing `conclusion === null` sidesteps the whole status vocabulary:
    // every unfinished state has a null conclusion, whatever GitHub decides to
    // call it next. The cooldown then covers the window where the run exists
    // but is not yet listed.
    const COOLDOWN_MS = 120000;
    try {
      const r = await gh(`/actions/workflows/${WORKFLOW}/runs?per_page=1`, env);
      if (r.ok) {
        const run = ((await r.json()).workflow_runs || [])[0];
        if (run) {
          if (run.conclusion === null)
            return new Response("already running", { status: 409, headers: h });
          if (Date.now() - Date.parse(run.created_at) < COOLDOWN_MS)
            return new Response("just ran", { status: 409, headers: h });
        }
      }
    } catch (e) {
      // A failed pre-check should not block the run it was only guarding.
    }

    const res = await gh(`/actions/workflows/${WORKFLOW}/dispatches`, env, {
      method: "POST",
      body: JSON.stringify({ ref: REF }),
    });

    if (res.status === 204)
      return new Response("queued", { status: 202, headers: h });
    return new Response(`github said ${res.status}: ${await res.text()}`,
                        { status: 502, headers: h });
  },
};
