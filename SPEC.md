# NTPC Bikaner Block 8 (200 MW) — MIS Dashboard Specification

**Version:** v1.0 (Baseline — LOCKED)
**Live URL:** https://vikas-visilean.github.io/ntpc-block8-mis-dashboard/
**Repository:** https://github.com/Vikas-visilean/ntpc-block8-mis-dashboard
**Baseline tag:** `v1.0-baseline-2026-08-17`
**Data as of:** 05-Aug-2026 (status date) · Project: KPIGEL-NTPC Bikaner Block 8 (200 MW) Project-SAT
**Owner:** VisiLean (Vikas Patel) for KPI Green Energy / KP Group

> **Change control:** this version is the signed-off baseline. No changes are made to it on ad-hoc requests.
> Any modification requires an explicit "unlock / new version" decision, is built as **v1.1+ on a separate
> branch**, and the `v1.0-baseline-2026-08-17` tag always restores this exact state.

---

## 1. What this dashboard is

A single self-contained HTML file (no external dependencies, ~2.2 MB) that renders a complete
project-management review system for the NTPC Bikaner Block 8 (200 MW) solar project:
13 pages covering the project summary, plant layout, procurement pipeline, MOM/actions, and nine
department views. It is generated from the approved **Rev-2 Weightages schedule**
(11,228 tasks / 10,853 dependency links) and published on GitHub Pages.

* All progress figures are **weightage-based** (the KP-approved Rev-2 weightages: Project Initiation 4 %,
  Regulatory 2 %, Design 8 %, Quality 1 %, Procurement 41 %, Execution & Construction 43 %, HOTO 1 %).
* All computations run **client-side** from an embedded JSON dataset, so every filter/toggle recomputes
  instantly with no server.

---

## 2. Architecture & data flow (current — MSP file driven)

```
MS Project schedule (TRACKED Rev-2 XML)
        │  ntpc_dash_data.py  (Python + mpxj: reads schedule, computes forecast + float,
        │                      classifies every activity, emits compact JSON)
        ▼
ntpc_dashboard_data.json  (~2 MB: meta + months + depts + milestones + 10,362 leaf records)
        │  build_ntpc_dash2.py  (injects JSON + KP logo into the template)
        ▼
ntpc_dash_template.html  ──►  index.html  (single file, everything inline)
        │  git commit + push
        ▼
GitHub Pages  →  https://vikas-visilean.github.io/ntpc-block8-mis-dashboard/
```

The **template never touches the data source** — it only consumes the JSON contract below. This is
what makes the VisiLean API switch a data-layer swap (§10) with zero UI change.

---

## 3. Data contract (the JSON the template consumes)

```jsonc
{
  "meta":   { "statusDate", "statusWd", "startDate", "project",
              "baselineFinishWd", "forecastFinishWd", "baselineFinish", "forecastFinish",
              "codBaseline", "codForecast", "statusIso",
              "plan", "act", "spi", "svPts", "svPct",          // weightage-based overall metrics
              "delayDays", "critical", "done", "inprog", "late", "total" },
  "months": [ { "label": "May-26", "wd": 22 }, ... ],           // month-end working-day markers
  "depts":  [ { "key": "engineering", "name": "Design & Engineering" }, ... ],  // 9 departments
  "milestones": [ { "name", "b", "f", "slip", "status" }, ... ],// 9 key milestones (wd indices)
  "cols":   ["dept","type","area","pkg","sec","stage","name","bES","bEF","fES","fEF",
             "pct","dur","qty","uom","tf","state","owner","sub","cost","seq"],
  "leaves": [ [ ...one array per activity, indexed by cols... ], ... ]   // 10,362 records
}
```

Per-activity fields (`leaves`):

| Field | Meaning |
|---|---|
| `dept` | department key (initiation / engineering / quality / supply / services / regulatory / execution / tnc / hoto) |
| `type` | Activity Type custom field (Engineering, Procurement-Supply, Construction, …) |
| `area` | Block-N / PSS / ICR / Plant-General / Off-site |
| `pkg`, `sec` | package (L3-ish) and section (L2-ish) names from the WBS |
| `stage`, `sub` | coarse stage bucket and fine pipeline sub-stage (Design/Tender/PO/…/At Site/Payment) |
| `bES`,`bEF`,`fES`,`fEF` | baseline / forecast start & finish as **working-day indices** |
| `pct` | % complete (0–100) |
| `dur` | duration in working days |
| `qty`,`uom` | quantity + unit (physical rows only) |
| `tf` | total float (working days) on the forecast network |
| `state` | done / inprog / late (past planned start, unstarted) / future |
| `owner` | department role owner (custom field Text4) |
| `cost` | activity cost in ₹ — **the Rev-2 weightage carrier** |
| `seq` | schedule (file) order for stable sorting |

**Working-day calendar:** 6-day weeks (Mon–Sat, Sundays off), day 1 = 07-May-2026 (LOA zero date).
Every date in the system is an index on this axis; `wdate()` converts back to dd-MMM-yy.

---

## 4. Calculation engine

### 4.1 Weighting
`weight(activity) = cost` (the Rev-2 weightage carrier). For any *filtered subset* whose total cost is
zero (e.g. pure quality-process views), the engine falls back to **duration weights** so bars never blank out.

### 4.2 The three curves (used by gauge, S-curves, progress bars)
For a set of activities R at date *t* (working-day index), with `w` = weight and clamp to [0,1]:

* **Plan %** `= Σ clamp((t − bES)/dur) · w ÷ Σ w` — planned value: each activity earns its weight
  linearly across its **baseline** window.
* **Actual %** `= Σ min(pct/100, elapsed-on-forecast) · w ÷ Σ w` — earned value; at today this equals
  Σ(pct·w)/Σw. (The `min` only matters when the date slider is dragged into the past.)
* **Forecast %** `= Σ clamp((t − fES)/dur) · w ÷ Σ w` — the projection on **forecast** dates.

Derived: **SPI = Actual ÷ Plan** · **Progress Variance = Actual − Plan** (percentage points).
Cross-check that always holds: Cost card EV ÷ BAC = overall Actual %.

### 4.3 Forecast dates (per activity)
Computed by a forward CPM pass over all 10,853 links:

1. **Complete (100 %)** → forecast = recorded actual dates.
2. **In progress** → forecast start = actual start; forecast finish = status date + duration × (1 − pct/100).
3. **Not started** → earliest start = max(status date, predecessor constraints
   (FS: pred fEF + lag · SS: pred fES + lag · FF: back-computed)); finish = start + duration.
4. Hard floor: *Project Closeout* cannot finish before wd 470 (**05-Nov-2027**, the FNET constraint).

Result at the 05-Aug-2026 status: baseline finish **05-Nov-27**, forecast **11-Nov-27** (+5 days).

### 4.4 Float & criticality
Backward pass from the forecast project end relaxes a Latest-Finish per activity through every link;
**Total Float = LF − fEF**. `Critical` = float ≤ 5 days and not complete (237 activities);
`Supercritical` = float ≤ 0 (169).

### 4.5 Status model (VisiLean-aligned)
Until the live VisiLean feed is connected, the dashboard asserts only what the schedule knows:

| Status | Colour | Rule |
|---|---|---|
| **Complete** | green `#1b8a2f` | pct = 100 |
| **Started** | purple `#7a4fb3` (VisiLean "Started") | 0 < pct < 100 |
| **Not Committed** | yellow `#8a7500` on wash | pct = 0 (all unstarted work) |

*Not Ready / Warning / Stopped and the quality states are reserved for the VisiLean live feed.*
Overdue-ness is shown as a **date fact** (red "was due dd-MMM-yy" text), never as an invented status.
Group/rollup status priority: all-done → Complete; **any progress → Started**; else Not Committed.
Other definitions: `Delayed` = forecast finish ≥ 4 days behind baseline (unfinished);
`Awaiting start` = pct 0 and baseline start before status date.

---

## 5. Pages & components

### 5.1 Project Summary (page 1)
| Component | Content / calculation |
|---|---|
| **Overall progress** (speedometer) | needle = Actual %, tick = Plan % (§4.2 on the filtered scope). Stats: SPI — Schedule Performance Index (= Actual % ÷ Planned %), Progress Variance (= Actual − Plan). Needle colour: green ≥ plan, amber ≥ 85 % of plan, red below. |
| **EPC bifurcation** | Engineering / Procurement / Construction rows: Actual % vs Baseline Plan %, activity counts, Δ progress variation, SPI chip. |
| **Cost** | Budget (BAC) = Σ cost; Earned Value = Σ cost·pct; CPI/Actual "—" awaiting accounts feed; FAC = BAC. |
| **KPI cards** | Total activities (incl. 9 milestones) · Completed (+% of count) · Delayed (≥4 days behind, + delayed-start count + critical chip) · Baseline vs Forecast (dates + "+N days" chip) · Days to COD. |
| **Key Milestones** | colour legend (green ≤6 days slip · amber 7–15 · red >15), mini progress track with today line, 9 cards: baseline/forecast dates + slip chip. |
| **Long Lead Item Delivery Status** | top-12 supply packages by weightage; delivery = "GRN at Site" step; baseline vs forecast delivery, Delay/Ahead in days, status chip. |
| **S-curve — Plan vs Actual** | **multi-select** discipline chips (Overall / E / P / C) overlaying curves — solid = actual, dashed = forecast, dotted = plan; **Cumulative and Monthly charts stacked**; Chart/Table toggle (table grows per-series columns). |
| **Stage progress** | Actual % vs Plan tick per stage bucket (Initiation → HOTO). |
| **Critical points — management attention** | top-5 *actionable* critical activities due within ~60 days (buffer/closeout excluded), each with full WBS path, VisiLean status, float, window, owner; supercritical counter. |
| **Open Constraints / Awaiting to Start** | two tabs: *Awaiting Start* (activities past planned start: WBS, Owner·Dept, planned start, pending-since days) and *VisiLean Constraints* (API placeholder — will list the constraints log + category pie once connected). |

### 5.2 Plant Layout
Block/feeder tile grid (24 blocks + PSS/ICR/general): each tile shows **Actual %** (red when behind
plan), plan %, activity count, delayed-count alarm chip, and per-category quantity bars
(Civil/Piling/MMS/Module/DC/AC-HT/BOP — physical quantities only; %-type rows excluded).
Clicking a tile filters the whole dashboard to that area. Below: Area Scorecard table
(plan/actual/SPI/delayed/critical per area).

### 5.3 Package Pipeline
Procurement pipeline matrix: rows = 61 packages, columns = **actual schedule steps** ordered by
earliest baseline start (up to 32, with a stage-column multi-select popover). Cell = VisiLean status
chip + due/done date (red when overdue vs baseline). Stage summary cards on top (done/total + "N in
progress"). Controls: **L1 section / L2-L3 package cascading filters**, package search, delayed-only
toggle. Click a row → step-level detail. Plus "Scope vs Order vs Deliver" quantity table.

### 5.4 MOM & Actions
Action tracker (seed content) — Responsible / Due / VisiLean-coloured status. Will sync from the
VisiLean action log (MOM category) via API.

### 5.5 Department pages (9)
Every department page: gauge, department S-curve, KPI cards, and:

* **Design & Engineering** — *Engineering Overview (Exec View)* single-row strip: stage, design status,
  % Engg complete (weightage-based), % RFP shared, TBER %, Material approval (client) %, tech queries
  (manual feed), current critical activity + float, On-track/Delayed chip. Then the engineering
  document pipeline (doc stages per package).
* **Procurement — Supply / Services** — *Key Procurement Dates (Exec View)* matrix (11 fixed columns
  RFP→GRN, dates coloured green ✓ complete / purple ▶ started / red overdue), *PO Tracker*
  (Wt %, baseline vs forecast/actual PO, Δ days, reason column for manual feed), *Committed vs
  Budgeted* card (committed = packages with PO placed), *Delay Analysis* bars for the ED heads a–e
  (RFQ receipt → PO placement), then the full pipeline matrix.
* **Regulatory & Statutory** — *Critical approvals tracker* (schedule order, sortable, searchable,
  status filter; **click a row to focus the Updates Sheet**), *All approval groups*, *Statutory
  Updates Sheet* (all 104 documents: timeline, scope/owner, target vs revised date, status).
* **Execution & Construction / T&C** — block/feeder scorecard + stage progress by work type.
* **Project Initiation / Quality / HOTO** — sections progress bars.

---

## 6. UI / UX system (VisiLean design language)

* **Colours (light):** page `#f5f6f8`, surface `#fff`, blue `#1793e6`, good `#00a455`, warn `#f59e00`,
  crit `#ff4343`; dark theme: page `#0E1216`, surface `#161B20`, blue `#45a9eb`. S-curve series:
  actual blue, plan purple, forecast dashed-blue; discipline overlays blue/purple/green/amber.
* **VisiLean status chips** (from the VisiLean Task Colours legend): Complete green · Started purple
  `#5C2D91`-family · Not Committed yellow · (Not Ready salmon / Warning amber reserved for live feed).
  A permanent legend sits in the filter bar.
* **Typography:** Inter; compact 11 px base scaled by **default zoom 1.3** on large screens
  (1.15 ≤ 1680 px, 1.0 ≤ 1400 px) per exec readability review.
* **Layout:** 12-column card grid, 8 px radius cards, sticky filter bar, left sidebar navigation
  (Project pages + Departments), Auto/Light/Dark theme toggle (persisted).
* **Terminology rules:** always “days” (never wd); "Actual % vs Baseline Plan %" phrasing; activity
  counts written as "N activities".

## 7. Interactions

* **Global filter bar** (applies to every page): Department, EPC type, Area, Package, **Owner**,
  **From/To date range** (forecast-window overlap), Critical-only, Delayed-only, **date slider**
  (re-evaluates all curves/KPIs at any as-of date), Reset.
* **Click-to-filter:** plant tiles → area filter; approvals tracker row → statutory sheet focus;
  pipeline row → step detail expand.
* **Scroll behaviour:** re-renders (toggles, filters) keep scroll position; only page *changes* scroll to top.
* **Tooltips:** S-curve hover (per-series values by month), milestone dots, pipeline quantity cells.
* **Sorting/search:** regulatory tables sortable by any column; package/approval search boxes.

## 8. Known placeholders (by design, awaiting feeds)
Tech query counts, billing status, CPI/actual cost, PO-delay reasons, committed-cost reasons —
shown as "— (manual)". VisiLean Constraints tab and MOM tracker await the API connection.

---

## 9. Update runbook (current MSP pipeline)

```
1. python ntpc_dash_data.py        # point P at the new TRACKED xml → ntpc_dashboard_data.json
2. python build_ntpc_dash2.py      # template + data + logo → index.html
3. QA: serve locally, walk 13 pages, zero console errors, spot-check EV ÷ BAC = Actual %
4. git commit + push (repo dir: C:\Users\vikas\AppData\Local\Temp\ntpc-mis-dash)
   (GitHub Pages may need: POST /repos/.../pages/builds to rebuild; verify by content marker)
5. Optional PDF: python make_print_html.py + headless Edge --print-to-pdf
```

All scripts live in `_build tools (do not delete)` and in the baseline snapshot (§11).

---

## 10. VisiLean API integration plan (next phase — real-time)

**Principle:** the template and every calculation stay untouched. Only the producer of
`ntpc_dashboard_data.json` changes — a new adapter builds the same JSON contract (§3) from VisiLean
APIs instead of the MSP file. Stub prepared: `visilean_api_adapter.py`.

What the adapter needs from the VisiLean APIs (to be mapped when API specs are provided):

| Need | Maps to |
|---|---|
| Activity list with WBS hierarchy (or L1–L7), name, duration, baseline start/finish | `pkg/sec/area` classification + `bES/bEF/dur` |
| Live % complete + actual start/finish per activity | `pct`, forecast engine inputs |
| VisiLean task status (Not Committed / Ready / Started / Warning / Stopped / Complete / quality states) | status chips — replaces the interim 3-state model, full legend activates |
| Custom fields: Department, Owner, Activity Type, Location, Package, Qty, UOM, Cost/Weightage | corresponding columns |
| Constraints log (category, status, activity link) | Open Constraints tab + category pie |
| Action log (MOM category) | MOM & Actions page |
| Assignee (VisiLean Activity Owner) | owner column/filter |

Refresh model options (decide with API): (a) scheduled regeneration (adapter → JSON → static publish,
e.g. every 15–60 min), or (b) client-side fetch where the page pulls JSON from a VisiLean endpoint at
load — template already reads one JSON object, so both are drop-in. Forecast/float can continue to be
computed in the adapter, or be replaced by VisiLean's own dates if preferred.

---

## 10A. v2 — live from the VisiLean APIs (deployed)

v1.0 at the repository root stays locked. **v2 lives at `/v2/` and is the live one.**

### Data source

Three VisiLean PowerBI endpoints, project `7A2842F6-7E5F-DB7C-3E7F-0EE7EF60698F`:
`type=task` (activities), `type=task` (history), `type=constraintLog`. Tokens are GitHub Actions
secrets (`VL_TOKEN_TASK` / `VL_TOKEN_HISTORY` / `VL_TOKEN_CONSTRAINTS`) and a gitignored
`scripts/vl_tokens.json` locally. The API returns 403 to any request carrying a browser `Origin`
header, so the page cannot fetch VisiLean directly — everything goes through the Action.

`prerequisites` always comes back empty, so activity logic is read from the static sidecar
`scripts/vl_relations.json` (10,853 pairs captured from the source MSP). **This file does not
update itself** — when the schedule is restructured in VisiLean it must be regenerated, or float
and criticality drift. `meta.logicCoverage` publishes the share of activities still wired into the
network so the drift is visible rather than silent.

### Fields are taken from VisiLean verbatim (KP rule, 18-Aug-2026)

| Dashboard dimension | VisiLean source |
|---|---|
| Department filter / department pages | `Department` custom field |
| Activity type filter **and all E/P/C figures** | `Activity Type` custom field |
| Location filter | `Location` |
| Package filter, long-lead packages | `Package` custom field |
| Owner filter | native VisiLean activity owner (the assigned person) |
| Ownership filter | `Owner.` custom field (group), renamed *Ownership* |
| Baseline dates | `baselineStartDate` / `baselineEndDate` |
| Forecast dates | `plannedStartDate` / `plannedEndDate` — **never recomputed** |
| % complete (project) | weightage-weighted from the Cost field |

### Counting rules — these tie the dashboard to VisiLean 1:1 (KP observations, 24-Aug-2026)

* **Total activities = VisiLean "All Tasks"** = every leaf task. Rows created straight in VisiLean
  have no MSP `externalId` (drawing revisions `R0`/`R1`/`R2`); they get a synthetic negative UID so
  they are still counted.
* **Not-baselined rows** (`nd=1`) have no baseline dates. They count in Total but are excluded from
  Completed, Delayed, critical and progress — which is exactly what VisiLean's own counters do, and
  is why VisiLean shows 6,430 tasks but only 189 complete out of 197 complete leaves.
* **E / P / C are counted on `Activity Type`, not on the department mapping.** The department
  mapping folded Testing & Commissioning into Construction (2,850 + 40 = 2,890) and disagreed with
  VisiLean. Activity types outside E/P/C (Quality, Statutory & Approvals, Project Management,
  Testing & Commissioning, Handover) are listed under the card so the three rows reconcile to Total.
* **Delayed** = not complete **and** past its planned start with 0% progress, or past its planned
  finish. Mirrors VisiLean's Delayed Tasks. The previous test (forecast finish >= 4 days past
  baseline) always read 0, because VisiLean's planned dates equal the baseline until a reschedule.
* **Milestones** are added to the headline count only when no filter is applied.
* **Long Lead Item Delivery Status** lists *every* `Procurement - Supply` package grouped by the
  `Package` field (33 today), not a top-N slice. Delivery row = the package's "GRN at site"
  activity, falling back to its last activity.

### Refresh — how it actually works

`schedule` events on GitHub are best-effort and heavily throttled. Measured on this repo with
`cron: "*/5"` over 23-24 Aug 2026: **median gap 27 min, maximum 111 min** — it never once ran at
5 minutes, which is why the dashboard was serving hour-old numbers.

The schedule therefore only has to *start* a worker:

* `cron: "7 */2 * * *"` starts a worker every 2 hours; `concurrency: cancel-in-progress: true`
  means a new worker cleanly replaces the running one.
* The worker itself loops **every 5 minutes for ~5h40m** (under the 6-hour job ceiling), so a
  delayed or skipped trigger is still covered by the previous worker.
* Each cycle publishes only when `v2/.datahash` changes (the hash excludes `generatedAt`).
  A failed cycle logs and continues; it never kills the worker.
* `workflow_dispatch` with `once: true` runs a single refresh — useful for a manual catch-up.

On the page: the header shows the build time **in IST** plus a live **data-age chip**
(green <= 10 min, amber <= 30 min, red beyond), and a background poll checks `meta.json` every
60 seconds and reloads when a new build lands — so nobody has to press Refresh to stay current.
`meta.generatedAtEpoch` carries the build instant in unix seconds for that age maths.

### Build & run

```
python scripts/ntpc_dash_data_v2.py     # VisiLean APIs -> scripts/ntpc_dashboard_data_v2.json
python scripts/build_ntpc_dash_v2.py    # + template + logo -> v2/index.html, meta.json, .datahash
```

The working copy lives at `C:\Users\vikas\ntpc-mis-dash` — **not** under `%TEMP%`, where Windows
cleanup previously deleted tracked files and corrupted the local git objects.

---

## 11. Baseline lock & backups

* **Git tag** `v1.0-baseline-2026-08-17` on the public repo — restores this exact dashboard any time
  (`git checkout v1.0-baseline-2026-08-17`).
* **Frozen snapshot folder:** `Downloads\Baseline Schedule KP\Dashboard Baseline v1.0 (17-Aug-2026)\`
  — index.html, template, data JSON, all build scripts, the PDF export, this spec, and the API adapter
  stub — plus a ZIP of the same.
* **Change policy:** v1.0 is not modified. New requests → explicit sign-off → v1.1+ on a branch;
  the baseline URL/tag stays untouched.

## 12. File inventory (baseline v1.0)

| File | Role |
|---|---|
| `index.html` | the deployed dashboard (self-contained) |
| `ntpc_dash_template.html` | UI template (all pages, calculations, interactions) |
| `ntpc_dashboard_data.json` | embedded dataset (built 05-Aug-2026 status) |
| `ntpc_dash_data.py` | MSP→JSON data builder (forecast + float engine, classification) |
| `build_ntpc_dash2.py` | template+data+logo → index.html |
| `make_print_html.py` | print-mode build for the PDF export |
| `visilean_api_adapter.py` | API adapter stub (produces the same JSON contract) |
| `SPEC.md` | this document |
| `NTPC ... MIS Dashboard (status 05-Aug-2026).pdf` | 27-page A3 PDF snapshot |
