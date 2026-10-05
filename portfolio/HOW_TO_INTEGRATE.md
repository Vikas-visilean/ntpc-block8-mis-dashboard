# How to integrate the portfolio page

This guide covers adding `portfolio/index.html` to
[Vikas-visilean/ntpc-block8-mis-dashboard](https://github.com/Vikas-visilean/ntpc-block8-mis-dashboard)
so that it is:

- **built by GitHub Actions**, the same way as the six project dashboards
- **published on GitHub Pages** at `https://vikas-visilean.github.io/ntpc-block8-mis-dashboard/portfolio/`
- **checked daily** by the sync-health workflow

> **Done, 5 Oct 2026:** steps 1–5 below are in place: `scripts/portfolio_template.html`, `scripts/projects/portfolio.json`, `scripts/build_portfolio.py`, `.github/workflows/refresh-portfolio.yml` and the `check_sync.py` row. The config also carries each project's short `name`, which the page shows. What remains is the rollout checklist in section 4. Section 1 describes the state before integration.

For what the page shows and how its figures are calculated, see
[PORTFOLIO_README.md](PORTFOLIO_README.md). This file covers only how to wire it into the repo.

---

## 1. Where things stand today

- **The page is a hand-edited static snapshot.** Its data is fixed at the 30 Sep 2026 data date. No workflow builds it and nothing links to it.
- **Its data is inline.** `const DATA = {...};` in `portfolio/index.html` holds every figure the page uses. The rest of the file is template: CSS, script and the KP logo.
- **The builder files from the first version are not available.** `extract.py`, `template.html` and `build.py` are in another person's temporary folder. They are also out of date: they would bring back PPC and the KPIs, and they don't produce the weekly series.
- **The weekly series** were produced by `weekly.js`, which is also in a temporary folder (path in PORTFOLIO_README §3a).

So integrating the page means building one new builder in `scripts/`, plus one workflow. Nothing in the existing builders or project pages needs to change.

**The rule from [ONBOARDING.md](../ONBOARDING.md) applies here too:** source goes in `scripts/`, and published folders are build output. After integration, nobody edits `portfolio/index.html` by hand.

---

## 2. What to add

| File | Purpose |
|---|---|
| `scripts/portfolio_template.html` | The page, with the inline data replaced by a placeholder |
| `scripts/projects/portfolio.json` | Values KP supplied that the project pages don't hold: type, MW, location, contract type |
| `scripts/build_portfolio.py` | Reads the six published project pages, recalculates, writes `portfolio/` |
| `.github/workflows/refresh-portfolio.yml` | Rebuilds and publishes on a schedule and after the project refreshes |
| `scripts/check_sync.py` | Add one line so the daily health check covers the portfolio |

**No VisiLean token is needed.** The builder reads only files that are already in the repo: the project pages the other workflows commit. It never calls the API.

---

## 3. Step by step

### Step 1: Create the template

Copy the current page and replace the data with a placeholder:

```
cp portfolio/index.html scripts/portfolio_template.html
```

In `scripts/portfolio_template.html`, the line that starts `const DATA = {"projects":[` is one long line. Replace it with:

```js
const DATA = __PAYLOAD__;
```

Leave the rest of the file as it is, including the inline KP logo.

### Step 2: Put KP's project values in config

Create `scripts/projects/portfolio.json`. The project pages don't carry these values in this form; KP supplied them.

```json
{
  "_comment": "Portfolio page - values KP supplied that the project pages do not carry. Order = default order on the page.",
  "projects": [
    {"id": "adani",    "type": "Solar", "mw": 234,   "site": "Khavda",     "state": "Gujarat",   "contract": "EPC"},
    {"id": "adani-s7", "type": "Solar", "mw": 300,   "site": "Khavda",     "state": "Gujarat",   "contract": "EPC"},
    {"id": "talaja",   "type": "Wind",  "mw": 83.75, "site": "Talaja",     "state": "Gujarat",   "contract": "EPC"},
    {"id": "v3",       "type": "Solar", "mw": 200,   "site": "Bikaner",    "state": "Rajasthan", "contract": "EPC"},
    {"id": "sjvn",     "type": "Solar", "mw": 200,   "site": "Khavda",     "state": "Gujarat",   "contract": "EPC"},
    {"id": "floating", "type": "Solar", "mw": 110,   "site": "Kadana Dam", "state": "Gujarat",   "contract": "EPC"}
  ]
}
```

`id` is the published folder name. The page links each row to `../<id>/index.html`.

**NTPC uses `v3`:** `refresh-v2.yml` builds both `v2/` and `v3/` from the same VisiLean data, so their figures are identical. The portfolio reads and links to `v3/`, the newer theme. If KP promotes a different NTPC page later, change only this `id`.

### Step 3: Write `scripts/build_portfolio.py`

This is a Python port of the logic in PORTFOLIO_README §1–§3a. Python matches the other builders and the workflow runner. It should do the following.

1. **Read each project's page.** For each `id` in `portfolio.json`, read `<id>/index.html` and `<id>/meta.json`. Parse the inline `const DATA = {...};`.
   - Look up columns **by name** through `DATA.cols`. NTPC has 37 columns; the others have 40.
   - Build the working-day calendar from `DATA.cfg.calendar` (`startDate`, `weeklyOff`) exactly as the template does: day 1 is the start date, and weekly-off days are skipped.
2. **Recalculate with the template's own formulas.** Use `wgt()`, `planPct()`, `fcPct()` and `actPctAt()` from `scripts/ntpc_dash_template_v3.html`. Apply them to all rows, and to each Activity Type subset:
   - E = `Engineering`
   - P = `Procurement - Supply` + `Procurement - Services`
   - C = `Construction`
3. **Produce, per project:**

   | Field | Source |
   |---|---|
   | `id`, `type`, `mw`, `site`, `state`, `contract` | `portfolio.json` |
   | `name`, `full` | short name for the row; `meta.json` → `project` |
   | `statusIso`, `generatedAt`, `startDate`, `plan`, `act`, `spi`, `codBaseline`, `codForecast`, `baselineFinish`, `forecastFinish`, `done`, `late` | `meta.json` |
   | `total` | number of activity rows |
   | `epc.{all,E,P,C}` | `{n, plan, act}` at the status working day, rounded to 2 decimals |
   | `months`, `sc.{all,E,P,C}.{plan,fc,act}` | one value per `DATA.months` month end, with `months` as `YYYY-MM`. Actual is `null` after the data date, and the data-date month uses the status working day. |
   | `weeks`, `wsc.{all,E,P,C}.{plan,fc,act}` | week ends every 7 days, aligned to the data-date weekday. The working-day position of a date = the number of working days up to and including it. Actual is `null` after the data date. |
   | `href` | `../<id>/index.html` |

4. **Run self-checks, and fail the build on any mismatch.**
   - Recalculated overall `plan` and `act` equal `meta.json` to 0.1 points.
   - Recalculated month-end values equal the weekly code's values at the same working day, to 0.01.
   - The output contains no `accessToken`. The other builders assert the same thing.
5. **Write the output.**
   - `portfolio/index.html` = the template with `__PAYLOAD__` replaced by the compact JSON (`{"projects":[...]}`). Escape non-ASCII as `\uXXXX`.
   - `portfolio/meta.json` = `{"generatedAt", "generatedAtEpoch", "statusDate", "statusIso", "projects": [ids]}`. `check_sync.py` reads `generatedAt` and `generatedAtEpoch`.
   - `portfolio/.datahash` = hash of the payload. `portfolio/.tplhash` = hash of the template.
   - Leave `PORTFOLIO_README.md` and `HOW_TO_INTEGRATE.md` alone. The workflow commits only the generated files (see Step 4).

The scratchpad `weekly.js` is a working JavaScript version of points 1–3 for the series. Port it rather than re-deriving the formulas.

**Test locally:** run `python scripts/build_portfolio.py`. With the current project pages, the output must match today's snapshot:

- portfolio actual **22.3%**, plan **35.8%**
- Adani S6a weekly actual at 30 Sep **30.44**

Open the page and check it renders. Then discard the local build output. Per ONBOARDING, published pages come from the workflow, not from a laptop.

### Step 4: Add the workflow

Create `.github/workflows/refresh-portfolio.yml`. It follows the pattern of the `refresh-*.yml` workflows, including their publish step, but has no credentials step.

```yaml
name: Refresh portfolio page

# Rebuilds portfolio/ from the project pages already in the repo - no VisiLean call,
# no token. Runs after the project refreshes and on a schedule as a fallback.

on:
  workflow_run:
    workflows:                # exact `name:` lines of the six feeding workflows
      - "Refresh v2 dashboard from VisiLean"           # NTPC - builds v2 AND v3; the portfolio reads v3/
      - "Refresh SJVN dashboard from VisiLean"
      - "Refresh Adani S6a dashboard from VisiLean"
      - "Refresh Adani S7 dashboard from VisiLean"
      - "Refresh Floating Solar dashboard from VisiLean"
      - "Refresh ABREL Talaja dashboard from VisiLean"
    types: [completed]
  schedule:
    - cron: "15 5 * * *"      # 10:45 IST, after the morning project refreshes
    - cron: "15 11 * * *"     # 16:45 IST, after the afternoon ones
  workflow_dispatch:          # manual: Actions tab -> "Run workflow", or `gh workflow run refresh-portfolio.yml`
    inputs:
      refresh_projects:
        description: "Refresh all six projects from VisiLean first, then rebuild"
        type: boolean
        default: false

permissions:
  contents: write
  actions: write              # only used to start the project workflows when refresh_projects is ticked

concurrency:
  group: refresh-portfolio
  cancel-in-progress: false   # let a running build finish; the next one picks up newer data

jobs:
  refresh:
    runs-on: ubuntu-latest
    timeout-minutes: 60         # 15 is plenty for a plain rebuild; the wait below can take longer
    steps:
      # Manual run with "refresh projects" ticked: start the six project workflows, wait
      # for them to finish, then fall through to the build. Waiting here, rather than
      # relying on workflow_run, guarantees the rebuild sees all six new pages.
      - name: Refresh the projects first (manual runs only)
        if: github.event_name == 'workflow_dispatch' && inputs.refresh_projects
        env:
          GH_TOKEN: ${{ github.token }}
        run: |
          set -uo pipefail
          WFS="refresh-v2.yml refresh-sjvn.yml refresh-adani.yml refresh-adani-s7.yml refresh-floating.yml refresh-talaja.yml"
          since=$(date -u +%Y-%m-%dT%H:%M:%SZ)
          for wf in $WFS; do gh workflow run "$wf" -R "$GITHUB_REPOSITORY" --ref master; done
          sleep 30
          for i in $(seq 1 90); do            # up to ~45 min
            pending=0
            for wf in $WFS; do
              st=$(gh run list -R "$GITHUB_REPOSITORY" --workflow "$wf" --event workflow_dispatch --limit 5 \
                     --json status,createdAt --jq "[.[] | select(.createdAt >= \"$since\")][0].status // \"missing\"")
              [ "$st" = "completed" ] || pending=$((pending+1))
            done
            [ "$pending" -eq 0 ] && { echo "all six project refreshes finished"; break; }
            echo "waiting on $pending project refresh(es)…"; sleep 30
          done
          for wf in $WFS; do
            c=$(gh run list -R "$GITHUB_REPOSITORY" --workflow "$wf" --event workflow_dispatch --limit 5 \
                  --json conclusion,createdAt --jq "[.[] | select(.createdAt >= \"$since\")][0].conclusion // \"none\"")
            echo "$wf: $c"
            [ "$c" = "success" ] || echo "::warning title=$wf::did not succeed ($c) - the portfolio uses that project's last good page"
          done

      - uses: actions/checkout@v4
        with:
          ref: master           # newest project pages, not the commit that triggered the run

      - uses: actions/setup-python@v5
        with:
          python-version: "3.12"

      - name: Build and publish if changed
        run: |
          set -uo pipefail
          git config user.name  "visilean-bot"
          git config user.email "support@visilean.com"
          python scripts/build_portfolio.py || { echo "::error title=Portfolio build failed::see log"; exit 1; }

          if git diff --quiet -- portfolio/.datahash portfolio/.tplhash ; then
            echo "no change - nothing published"; exit 0
          fi

          # Same re-cut pattern as the project workers: generated output, ours is newest.
          for try in 1 2 3 4 5 ; do
            git fetch -q origin master
            git reset -q --mixed origin/master
            git add portfolio/index.html portfolio/meta.json portfolio/.datahash portfolio/.tplhash
            git commit -q -m "portfolio auto-refresh $(TZ=Asia/Kolkata date '+%d-%b %H:%M IST')" || { echo "nothing to publish"; exit 0; }
            git push -q && { echo "published"; exit 0; }
            echo "push retry $try"; sleep $((10*try))
          done
          echo "::error::could not push after 5 tries"; exit 1
```

Notes:
- **When the portfolio updates:** the six project workflows are scheduled three minutes apart, from 10:00 to 10:21 IST and again from 16:00 to 16:21 IST. GitHub often starts them 10–30 minutes late, and occasionally up to about two hours late.
  - With `workflow_run`, the portfolio rebuilds after **each** project run finishes, so a cycle can trigger up to six rebuilds.
  - A rebuild publishes only if the hashes changed, so a project run that published nothing leads to no portfolio commit.
  - The `concurrency` group runs the rebuilds one after another, and the last one always sees every project's latest page.
  - The 10:45 and 16:45 IST schedule only catches a cycle where every trigger was missed.
- **Use `workflow_run`, not `on: push`.** A push made with `GITHUB_TOKEN`, which is how every refresh workflow publishes, does not trigger other workflows. A `paths:` push trigger on the project folders would therefore never fire.
- **List workflows by their `name:` line.** `workflow_run` matches each workflow's `name:` line, not its file name. Copy the six names exactly from the `refresh-*.yml` files. A mistyped name silently never fires.
- **The schedule is a fallback.** Scheduled runs start late and are sometimes dropped, as with the other workers. For fresh numbers now, refresh it manually (next section).
- **Checkout comes after the wait.** In the YAML, the checkout step runs *after* the project-refresh step, so it picks up the pages those runs just pushed.

### Step 4a: Refresh the portfolio manually

There are two kinds of manual run. Pick one based on how fresh the numbers need to be.

| You want | Run | Time |
|---|---|---|
| The portfolio to match the project pages as they are now | **Rebuild only**, with "refresh projects" unticked | ~1 min |
| The latest VisiLean data on every project, then the portfolio | **Refresh projects, then rebuild**, with it ticked | ~10–45 min, depending on VisiLean |

**From the GitHub website:**

1. Open the repo → **Actions** tab.
2. In the left list, pick **Refresh portfolio page**.
3. Click **Run workflow** (top right of the run list).
4. Leave the branch as `master`. Tick **Refresh all six projects from VisiLean first, then rebuild** if you need new VisiLean data.
5. Click the green **Run workflow** button.
6. Open the run that appears. It's green when done.
   - **Log says `published`:** the page is updated. GitHub Pages usually shows the new page within 1–2 minutes; hard-refresh the browser (Ctrl+F5).
   - **Log says `no change - nothing published`:** nothing differed from the last build.
   - **A warning names a project:** that project's refresh failed, and its row keeps showing its last good page.

**From a terminal** (GitHub CLI, signed in with access to the repo):

```
# rebuild only
gh workflow run refresh-portfolio.yml -R Vikas-visilean/ntpc-block8-mis-dashboard

# refresh all six projects from VisiLean first, then rebuild
gh workflow run refresh-portfolio.yml -R Vikas-visilean/ntpc-block8-mis-dashboard -f refresh_projects=true

# follow the run
gh run watch -R Vikas-visilean/ntpc-block8-mis-dashboard
```

**To refresh one project** (for example after fixing data in VisiLean for SJVN only), run that project's workflow from Actions, here *Refresh SJVN dashboard from VisiLean*. The portfolio rebuilds automatically when it finishes, through `workflow_run`. If it hasn't updated a few minutes later, run **Rebuild only**.

Both kinds of manual run join the same queue as the automatic ones, so they never publish over each other.

### Step 5: Add the page to the health check

In `scripts/check_sync.py`, add one row to `DASH`:

```python
    ("Portfolio (all projects)", "portfolio", "refresh-portfolio.yml"),
```

The daily `sync-health.yml` then reports the portfolio's build age and whether its workflow is running.

### Step 6: Decide on links

- **Root page:** the root `index.html` is the locked v1.0 baseline. **Do not add a link there.** Share `/portfolio/` directly.
- **Project pages:** to add a "← Portfolio" link to each project page, make the change in **both** `ntpc_dash_template_v2.html` and `ntpc_dash_template_v3.html`, as ONBOARDING requires for template changes. This is optional and can come later.

---

## 4. Rollout checklist

1. Create a branch, for example `portfolio-integration`. Don't commit to `master` directly.
2. Add the files from Steps 1–5 and open a PR. The README says the page "is not built by any workflow"; update it in the same PR.
3. After merging, run *Actions → Refresh portfolio page → Run workflow* once, as in Step 4a. Also try one run with **refresh projects** ticked, to confirm the workflow is allowed to start the project workflows.
4. Check:
   - the run is green and its log says `published`
   - `https://vikas-visilean.github.io/ntpc-block8-mis-dashboard/portfolio/` loads, after GitHub Pages has deployed
   - the banner's data date matches the project pages
   - every row's **open** arrow reaches its project dashboard
   - the Monthly / Weekly switch works, and the weekly chart scrolls sideways
   - `python scripts/check_sync.py` lists the portfolio
5. Wait for the next project refresh. Confirm the portfolio rebuilds from `workflow_run` without a manual run.

---

## 5. Things that will bite you

- **The portfolio depends on the project pages.** If a project's sync is broken, its row shows that project's last good build. The daily health check shows which project is stale. The portfolio itself will look "fresh" because it rebuilt.
- **Template changes reach the portfolio.** If a column is renamed or removed in the project template, or the formulas change, the self-checks in Step 3 fail the build loudly. That is intended: update the builder, don't loosen the check.
- **Data dates differ between projects.** If one project refreshes and another doesn't, they can have different data dates. The page uses the latest data date for the S-curve marker and the earliest for "Data as of". Consider failing, or warning in the step summary, when they differ by more than a day.
- **Adding a project** takes a row in `scripts/projects/portfolio.json` and its workflow name in the `workflow_run` list. Nothing else is needed, as long as the project uses the standard template.
- **Merge conflicts in `portfolio/`:** take your own build, as ONBOARDING describes for the other pages. Never commit conflict markers into `index.html` or `meta.json`.
- **Docs in a published folder:** `PORTFOLIO_README.md` and this file sit in `portfolio/` and are published as plain files. That's harmless. If you'd rather keep `portfolio/` pure build output, move them to `scripts/` or the repo root and fix the links.

---

## 6. Open decisions for KP and VisiLean

- **Portfolio weighting:** percentages are currently weighted by MW. Weighting by cost or by activity weightage would give different figures.
- **Status thresholds:** SPI cut-offs of 0.95 and 0.80, and phase gaps of 2 and 10 points.
- **Week ends:** weeks currently end on the data-date weekday (Wednesday for this snapshot). If KP reports weeks ending on another day, change the alignment in the builder.
- **Publishing approval:** whether the page goes live before KP has reviewed it. Until then, merge the workflow but leave the link unshared.
