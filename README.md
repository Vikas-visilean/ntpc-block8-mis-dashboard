# KP MIS dashboards — live from VisiLean

One repository serving the live MIS dashboards and user-activity reports for KP Group's
projects. Each page is rebuilt from the VisiLean PowerBI API by a GitHub Actions workflow
and published on GitHub Pages. **No dashboard is ever built on a laptop**; if one needs
to be, the sync is broken and that is what to fix.

Published at **https://vikas-visilean.github.io/ntpc-block8-mis-dashboard/**. The root
page (`index.html`) is the locked v1.0 baseline, tag `v1.0-baseline-2026-08-17`, and is
not edited.

**Portfolio, all six projects on one page:**
**https://vikas-visilean.github.io/ntpc-block8-mis-dashboard/portfolio/** (review draft, see
[below](#portfolio)).

This README condenses the other documents in the repo; each section links to the full
file. For day-to-day working rules, conflicts and pitfalls, read
**[ONBOARDING.md](ONBOARDING.md)**.

---

## Projects

Every project has one configuration file, `scripts/projects/<code>.json`, and one
VisiLean token.

| Code | Project | VisiLean project GUID | Page | Workflow | Token secret |
|---|---|---|---|---|---|
| `ntpc` | NTPC Bikaner Block 8 · 200 MW | `7A2842F6-7E5F-DB7C-3E7F-0EE7EF60698F` | [/v2/](https://vikas-visilean.github.io/ntpc-block8-mis-dashboard/v2/), [/v3/](https://vikas-visilean.github.io/ntpc-block8-mis-dashboard/v3/) | `refresh-v2.yml` | `VL_TOKEN_NTPC` |
| `sjvn` | SJVN Khavda · 200 MW | `7DAD8CE4-4DD0-62DA-9D8D-9D10A2E11289` | [/sjvn/](https://vikas-visilean.github.io/ntpc-block8-mis-dashboard/sjvn/) | `refresh-sjvn.yml` | `VL_TOKEN_SJVN` |
| `adani` | Adani Green Energy S6a · 234 MW | `8E1DC8F3-B98D-7466-372B-A885DE53F1BB` | [/adani/](https://vikas-visilean.github.io/ntpc-block8-mis-dashboard/adani/) | `refresh-adani.yml` | `VL_TOKEN_ADANI` |
| `adanis7` | Adani Green Energy S7 · 300 MW | `11127A8C-E796-06BF-8B4A-82CF074A6C4E` | [/adani-s7/](https://vikas-visilean.github.io/ntpc-block8-mis-dashboard/adani-s7/) | `refresh-adani-s7.yml` | `VL_TOKEN_ADANIS7` |
| `floating` | Floating Solar · Kadana Dam · 110 MW | `A52816EA-1EA7-A978-EEEA-29A0D775CD7F` | [/floating/](https://vikas-visilean.github.io/ntpc-block8-mis-dashboard/floating/) | `refresh-floating.yml` | `VL_TOKEN_FLOATING` |
| `talaja` | ABREL Talaja · 83.7 MW wind | `2F7F0BA6-2345-C92E-81E8-C034D1E9848D` | [/talaja/](https://vikas-visilean.github.io/ntpc-block8-mis-dashboard/talaja/) | `refresh-talaja.yml` | `VL_TOKEN_TALAJA` |

The two user-activity reports reuse those projects' tokens; neither has one of its own.

| Report | Reads | Page | Workflow |
|---|---|---|---|
| Adoption tracker | NTPC | [/adoption/](https://vikas-visilean.github.io/ntpc-block8-mis-dashboard/adoption/) | `refresh-adoption.yml` |
| User Updates | NTPC, Adani S6a, Adani S7, Floating, Talaja | [/updates/](https://vikas-visilean.github.io/ntpc-block8-mis-dashboard/updates/) | `refresh-updates.yml` |

### Portfolio

**[/portfolio/](https://vikas-visilean.github.io/ntpc-block8-mis-dashboard/portfolio/)** rolls
the six project pages up into one view: progress, EPC split, and a monthly or weekly S-curve,
weighted by MW.

- **No token needed.** `scripts/build_portfolio.py` recalculates everything from the project
  pages already in the repo.
- **Rebuilds automatically** after each project refresh, and at 10:45 and 16:45 IST as a fallback.
- **Review draft.** Not linked from the root page; share it only once KP has approved it.
- **Docs:** what the page shows and how it is calculated is in
  [portfolio/PORTFOLIO_README.md](portfolio/PORTFOLIO_README.md); the wiring and manual-refresh
  steps are in [portfolio/HOW_TO_INTEGRATE.md](portfolio/HOW_TO_INTEGRATE.md).

| Report | Reads | Page | Workflow |
|---|---|---|---|
| Portfolio | the six project pages (`scripts/projects/portfolio.json`) | [/portfolio/](https://vikas-visilean.github.io/ntpc-block8-mis-dashboard/portfolio/) | `refresh-portfolio.yml` |

---

## VisiLean API and parameters

Every request goes to one endpoint, with the project's token and GUID:

```
https://app.visilean.net/pb/PowerBiAPI/resource/powerBi/getData/visilean?accessToken=<token>&projectId=<GUID>
```

The rest of the query string chooses what comes back. **One token serves every request
for its project**; only the parameters change.

**Project dashboards** (`scripts/dash_data.py`, `scripts/ntpc_dash_data_v2.py`):

| Feed | Parameters | Used for |
|---|---|---|
| Task list | `&type=task` | every activity, dates, % complete, status, custom fields |
| History | `&type=task&IncludeStatusChange=true&IncludeReschedule=true&IncludeQuantities=true&IncludeConstraintNotes=true` | fills `activityHistory`, where the variance reasons live |
| Constraints | `&type=constraintLog` | the constraints log |

**Adoption and Updates reports** (`scripts/adoption_data.py`, `scripts/updates_data.py`):

| Feed | Parameters | Used for |
|---|---|---|
| Task list | `&type=task` | the assignee roster and the activity count |
| History | `&type=task&IncludeStatusChange=true&IncludeReschedule=true&IncludeTaskCreation=true&IncludeWorkforceAssignment=true&IncludeQuantities=true&IncludeConstraintNotes=true&IncludeOther=true` | the whole activity trail in one response |

The API answers **403 to any request carrying a browser `Origin` header**, so pages never
call VisiLean themselves; only the workflows do. The builds assert that no `accessToken`
reaches the published HTML.

---

## Sync setup

Condensed from **[SYNC-SETUP.md](SYNC-SETUP.md)**.

**Tokens.** A VisiLean token works only for the project it was generated for, and one
token serves all of that project's feeds. Each project's token is a repository secret,
`VL_TOKEN_<CODE>` as in the table above, holding the token alone with no URL.

**Fallback.** A second secret, `VL_TOKENS_JSON`, can hold every token in one flat map:

```json
{
  "ntpc":     "<NTPC token>",
  "sjvn":     "<SJVN token>",
  "adani":    "<Adani S6a token>",
  "adanis7":  "<Adani S7 token>",
  "floating": "<Floating Solar token>",
  "talaja":   "<ABREL Talaja token>"
}
```

A workflow tries `VL_TOKEN_<CODE>` first. If it is missing or VisiLean rejects it, the
workflow switches to that project's entry in `VL_TOKENS_JSON` and warns on the run,
naming the secret to fix. The run fails only when both are rejected. Locally the same
flat map can live in the gitignored `scripts/vl_tokens.json`.

**Schedule.** Every workflow runs one refresh at about 10:00 and 16:00 IST, a few minutes
apart per project, and publishes only when the data or the template changed. GitHub
starts scheduled runs late and sometimes drops them, so for fresh numbers now use
*Actions → pick the workflow → Run workflow*.

**Helpers.**

- `python scripts/check_sync.py`: build age and sync state of every published page.
- `python scripts/check_tokens_json.py <file>`: tries each token in a flat map against
  all three dashboard feeds, printing row counts, never tokens.
- `python scripts/prepare_tokens.py <file>`: turns tokens in any shape, including pasted
  feed URLs, into the flat map, verified.

**When something is wrong.** A project with no token skips its refresh with a warning.
A rejected token falls back with a warning, and fails the run if every token is rejected.
A VisiLean outage is retried three times and then fails the run. A malformed
`VL_TOKENS_JSON` fails the run straight away. The daily `sync-health.yml` at 09:05 IST
reports anything unhealthy, and a page older than 26 hours shows a banner saying why.

**Rotating a token.** Replace that project's secret, or its `VL_TOKENS_JSON` entry, and
run its workflow once.

---

## Specification

Condensed from **[SPEC.md](SPEC.md)**. **Section 10A is the authoritative description of
the live system.** Sections 1–9 describe the locked v1.0 baseline, which was driven by a
static MSP export, and are kept for reference only.

- **Builds.** `/v2/` is the page KP uses, embedded in VisiLean's Custom Analytics. `/v3/`
  has identical logic in the VisiLean brand palette. Every functional change must be made
  in both `ntpc_dash_template_v2.html` and `ntpc_dash_template_v3.html`; nothing enforces
  it.
- **Counting rules**, reconciled with VisiLean's own dashboard: Total is every leaf task.
  Completed is 100% progress. Delayed is past planned start at 0%, or past planned finish
  and not complete. Actual % is weightage-weighted. Activities with trade "Not
  Applicable" are excluded everywhere, at KP's instruction. E / P / C are counted on
  Activity Type.
- **Other rules in 10A**: the data contract, weightage and progress, the post-baseline
  revision rule, reasons for variance, predecessor-derived notes, the drill engine and
  property panel, and how the pages cope with running inside VisiLean's iframe.
- **Open items (10B)**: Planned % does not reconcile with VisiLean's published figure and
  needs a definition from VisiLean; many activities carry no weightage or no baseline;
  VisiLean's own Critical flag is almost unused; `vl_relations.json` must be regenerated
  whenever the schedule is re-imported; promoting v3 awaits KP.

---

## Request to VisiLean: file events

Condensed from **[FILE-EVENTS-REQUEST.md](FILE-EVENTS-REQUEST.md)**, raised 29-Sep-2026.

- **The gap.** The User Updates report counts status changes, reschedules, quantities,
  notes and imports, but cannot see a document being uploaded. No PowerBI feed carries
  file events, and no field holds a filename.
- **Why it cannot be fixed here.** The events exist, named `ACTIVITY_FILE_ADDED`,
  `ACTIVITY_FILE_UPLOADED` and `ACTIVITY_MULTIPLE_FILE_UPLOADED`. They live on a
  per-activity endpoint behind a browser login, which a scheduled build cannot call.
- **The ask.** VisiLean adds those events to `activityHistory` on the `type=task` feed
  for NTPC, Adani S6a, Adani S7, Talaja and Floating, in the sentence shape the web
  client already writes.
- **Afterwards.** Nothing is needed from this side: the parser already recognises the
  upload sentence, so uploads are counted the day they appear.

---

## Working on this repo

See **[ONBOARDING.md](ONBOARDING.md)**. It covers what to run first, the pitfalls that
have bitten before, handling conflicts with the refresh workflows, and never committing
tokens. Source changes go in `scripts/`; the published folders are build output.
