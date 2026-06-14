# Reliable 15-minute refresh (external scheduler)

GitHub's built-in `schedule:` cron is **best-effort** — it often starts hours late, drifts,
or skips runs under load. For a dependable 15-minute refresh, have a free external scheduler
([cron-job.org](https://cron-job.org)) call the workflow's `workflow_dispatch` API on a fixed
interval. GitHub then runs the existing `fetch.yml` exactly when pinged.

```
cron-job.org (every 15 min)
   └─ POST .../actions/workflows/fetch.yml/dispatches  (Bearer PAT)
        └─ GitHub runs fetch.yml → commits data/wc2026.json
```

The token lives only at cron-job.org — never in this repo.

---

## 1. Create a token (fine-grained PAT)

GitHub → **Settings → Developer settings → Personal access tokens → Fine-grained tokens → Generate new token**:

- **Repository access** → *Only select repositories* → `BerlinoPotato/fbwc2026`
- **Permissions** → *Repository permissions* → **Actions: Read and write**
- **Expiration** → 90 days (renew when it lapses; or pick longer)
- Generate → copy the token (`github_pat_…`). You only see it once.

> Minimal scope: it can trigger Actions on this one repo and nothing else.

## 2. Create the cron job

Sign up free at [cron-job.org](https://cron-job.org) → **Create cronjob**:

| Field | Value |
|---|---|
| **Title** | `WC2026 fetch` |
| **URL** | `https://api.github.com/repos/BerlinoPotato/fbwc2026/actions/workflows/fetch.yml/dispatches` |
| **Schedule** | Every 15 minutes (`*/15`) |
| **Request method** | `POST` |

**Request headers** (Advanced → Headers):

```
Accept: application/vnd.github+json
Authorization: Bearer github_pat_YOUR_TOKEN
X-GitHub-Api-Version: 2022-11-28
Content-Type: application/json
User-Agent: wc2026-cron
```

**Request body**:

```json
{"ref":"main"}
```

Save. cron-job.org now triggers the fetch every 15 minutes.

## 3. Verify

- A successful trigger returns **HTTP 204** (cron-job.org shows the job as OK).
- GitHub → **Actions → Fetch World Cup data** → new runs appear with event **`workflow_dispatch`**, actor = your token.
- `401/403` → token scope/expiry wrong. `404` → URL typo or workflow filename changed.

---

## Notes

- Works because `fetch.yml` is on the **default branch** and declares `workflow_dispatch`.
- You can **keep** the GitHub `schedule:` block as a backup — both can run; the commit step
  is a no-op when data is unchanged, so duplicate triggers are harmless.
- During the tournament you could tighten cron-job.org to every 5 minutes (free tier allows it).
  GitHub Actions minutes are free on public repos.
- Rotate/renew the PAT before it expires, or scheduled triggers silently stop (cron-job.org
  will show `401`).
