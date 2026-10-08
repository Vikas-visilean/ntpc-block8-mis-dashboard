# Portfolio dashboard — review draft

`portfolio/index.html` is one page that rolls up the KP Group project MIS dashboards. It shows progress, the EPC split and a monthly or weekly S-curve for all projects.

**Status:**
- **Review draft.** Built and published by GitHub Actions, but not linked from any other page and not yet shared with KP.
- **Refreshes itself.** `refresh-portfolio.yml` rebuilds it after each project refresh, and at 10:45 and 16:45 IST as a fallback. The page shows the project pages' data date.
- **One file.** It is self-contained: data, styles, scripts and the KP logo are all inline, so it works offline once saved.

Source: `scripts/portfolio_template.html` (the page) and `scripts/build_portfolio.py` (the data). `portfolio/index.html` is build output, so don't edit it by hand.

How it is wired into the repo's GitHub Actions and Pages setup: [HOW_TO_INTEGRATE.md](HOW_TO_INTEGRATE.md).

---

## Projects included

| Project | Source page | Type | Capacity | Location | Type of project |
|---|---|---|---|---|---|
| Adani S6a | `adani/` | Solar | 234 MW | Khavda, Gujarat | EPC |
| Adani S7 | `adani-s7/` | Solar | 300 MW | Khavda, Gujarat | EPC |
| ABREL Talaja | `talaja/` | Wind | 83.75 MW | Talaja, Gujarat | EPC |
| NTPC Bikaner | `v3/` | Solar | 200 MW | Bikaner, Rajasthan | EPC |
| SJVN Khavda | `sjvn/` | Solar | 200 MW | Khavda, Gujarat | EPC |
| Floating Solar | `floating/` | Solar | 110 MW | Kadana Dam, Gujarat | EPC |
| INOX Wind | `inox/` | Wind | 99 MW | Khavda, Gujarat | EPC |

- KP supplied the Type, Capacity, Location and Type of project values. The pages do not hold them in this form.
- The `adoption/` and `updates/` reports are deliberately left out for now.

---

## How it was built

### 1. Reading the data already in the project pages

Each project page (`<folder>/index.html`) carries its full dataset as plain JSON in an inline script: `const DATA = {...};`. All seven pages come from the same template, `scripts/ntpc_dash_template_v3.html`, so the data has the same shape:

- **`meta`:** status date, plan %, actual %, SPI, COD (commercial operation date) baseline and forecast, and activity counts. This is the same content as `meta.json`.
- **`cfg`:** the project config, including its calendar, document rule (`acceptRe`) and PO step (`poStep`).
- **`months`:** month-end positions, used for the S-curve.
- **`cols` and `leaves`:** one row per activity. Each row has its type, department, baseline, forecast and actual dates, % complete and weightage.

Two details matter when reading it:

- Columns must be looked up **by name** through `cols`, never by position. NTPC (v3) has 37 columns; the other projects have 40.
- All dates are **working-day numbers**, not calendar dates. Day 1 is `cfg.calendar.startDate`, and the project's weekly off days are skipped.

### 2. Recalculating with the project pages' own formulas

The portfolio does not invent its own progress maths. It replays the template's functions over the same rows:

| Figure | Template function | Rule |
|---|---|---|
| Planned % | `planPct()` | baseline dates, weighted by the Weightage field |
| Forecast % | `fcPct()` | forecast dates, same weights |
| Actual % | `actPctAt()` | % complete, capped by elapsed time; finished work counts from its actual finish |
| Weights | `wgt()` | Weightage field; falls back to duration if a set has no weights |
| E / P / C split | `epcCard()` | VisiLean Activity Type: Engineering · Procurement – Supply + Services · Construction |
| S-curve | `scurve()` | the three % figures at each month end; actual stops at the data date |

**Check:** for every project, the recalculated overall planned % and actual % equal the values in the project's `meta.json`, to 0.1 points. `build_portfolio.py` stops with an error if they ever disagree.

### 3. Rolling up to the portfolio

- **Percentages** (progress, E/P/C, S-curve) are **weighted by MW** across the projects in view.
- **Activity counts** are **summed**.
- **The portfolio S-curve** aligns projects by calendar month:
  - before a project starts, it counts as 0%
  - after its last month, it holds its final value
- **The last-6-months figures** are computed in the page from the same monthly series. The window is the 6 month-ends up to and including the data-date month, so Apr–Sep 2026 for this snapshot. These figures are the S-curve's statline, the banner's "Gained · 6 mo" tile and each row's sparkline.
  - **Gain** is the value at the data date minus the value at the end of the month before the window (end of March here).
  - It is calculated for actual and planned separately, and "vs plan" is actual gain minus planned gain.
  - A project that starts inside the window counts from 0%. NTPC Bikaner, which starts in May 2026, is the only one.

### 3a. Weekly S-curve series

The project pages only publish month-end positions, so `scripts/build_portfolio.py` computes the weekly series itself. It is a port of the original `weekly.js`.

How it works:
- It reads each project page's inline `DATA`, meaning its activities, calendar and status working day.
- It replays the template's `planPct()`, `fcPct()`, `actPctAt()` and `wgt()` at every week end.
- It does this for Overall and for E, P and C separately.

Details:
- **Week ends** fall on the data-date weekday and step 7 days at a time. With a data date of Wed 30 Sep 2026, every week ends on a Wednesday, so the last actual point is the data date itself.
- **A date's working-day position** is the count of the project's working days up to and including that date.
- **Actual** stops at the data date.
- **Check:** the working-day position of every month's last calendar day must equal that month's `wd` on the project page. This proves the weekly and monthly series sit on the same axis. The build fails if any month disagrees.
- **Output:** for each project, `weeks` (the week-end ISO dates) and `wsc` (the series, shaped like `sc`).
- **Rolling up:** the portfolio weekly curve combines projects the same way as the monthly one. Weeks are matched by date and weighted by MW. Before a project starts it counts as 0%, and after its last week it keeps its final value.


### 4. Producing the page

| File | Role |
|---|---|
| `scripts/portfolio_template.html` | the page design, with a `__PAYLOAD__` placeholder for the data |
| `scripts/projects/portfolio.json` | the values KP supplied (name, type, MW, location, contract type) and the project order |
| `scripts/build_portfolio.py` | reads the seven project pages, recalculates (sections 1–3a), runs the checks, fills the template and writes `portfolio/index.html`, `meta.json`, `.datahash` and `.tplhash` |

```
python scripts/build_portfolio.py                      # from the project pages in this checkout
python scripts/build_portfolio.py --src DIR --out DIR  # from another copy, e.g. to test
```

Published pages come from the workflow. Discard a local build rather than committing it.

The formulas are replayed exactly as the project pages compute them in the browser: same order of addition, and JavaScript rounding (half up). Built from the 30 Sep pages, the output matches the original snapshot except for 2 values in Adani S6a's Procurement plan for Dec 2026. The snapshot had 99.92 where the project template itself gives 99.93, because the old extractor rounded half to even.

---

## What the page shows

| Section | Contents |
|---|---|
| Header | KP Group · Project Portfolio, data date, light/dark switch |
| Banner | Project count, total MW and activities, plus four tiles: actual progress (with Plan, both computed from the two-decimal values so they match the S-curve), portfolio SPI, progress gained in the last 6 months (Actual, with Plan), projects needing attention (SPI under 0.95) |
| Toolbar | A wider search box (it also matches Solar / Wind); dropdown filters for **Capacity, Location, Type of project**; sort by Needs attention / Healthiest / Largest / A–Z |
| Project rows | One row per project, split into a **Solar** group and a **Wind** group. Each group heading gives its project count and total MW. Sorting applies within each group. |
| EPC-wise bifurcation | Portfolio Engineering, Procurement and Construction tiles, each with every project ranked under it. The headline reads `Actual% / Plan%` with the gap. Each bar is stacked: **green** = actual, **amber** = the shortfall from actual up to plan (rounded end), **grey** = the remainder to 100%. When actual is at or ahead of plan, the bar is green only. The value at the right reads `Actual/Plan`, for example `60.4%/99.6%`. |
| S-curve | One full-width card with Actual, Plan and Forecast over the whole project span. It can show the whole portfolio or one project, All or E / P / C, and has a **Monthly / Weekly** switch.<br>• Above the chart, an **overall progress statline** gives Actual %, Plan % and Gap (points) at the data date, for the same scope and phase.<br>• **Monthly** fits the card width, with month labels.<br>• **Weekly** puts one point per week, 20 px apart, with every week labelled at 45°. When the weeks don't fit, only this chart scrolls sideways. The % axis stays fixed on the left, and the chart opens scrolled to the data date. |

Each **project row** has:
- a **plan vs actual gauge**: a half-circle from 0% on the left to 100% on the right
  - the grey plan arc runs to Plan %, with a rounded end
  - the actual arc runs to Actual % and is coloured by SPI status
  - there is no plan tick
  - actual % is shown in the centre, with an "Actual x% · Plan y%" key underneath
- a title line: project name, then capacity (smaller), then location (smaller still)
- status badges, plus a COD warning when COD is within 90 days
- facts (activities, complete, COD)
- Engineering, Procurement, Construction and Overall bars, each stacked like the gauge:
  - **actual**, in its status colour
  - **grey** from actual up to plan, with a rounded end
  - **light grey** for the rest

  Each bar's value reads `Actual/Plan`.
- a 6-month sparkline of actual progress, captioned "Actual · last 6 months" with no number. Its tooltip gives the Actual and Plan gain and the month-by-month Actual and Plan values.
- a link to the project's own dashboard

**Capacity bands** for the filter are Up to 100 MW, 101–250 MW and Above 250 MW. Every section responds to the filters and search. If nothing matches, the page names the filter that caused it.

**Page height** never shrinks when filters cut down the content. The page keeps the tallest height it has reached, so the layout doesn't jump.

**Status rules:**
- **Project, by SPI:**
  - On track: 0.95 or more
  - Behind: 0.80 to 0.94
  - Critical: under 0.80
- **Phase, by gap between planned and actual:**
  - On plan: within 2 percentage points
  - Behind: 2 to 10 points
  - Well behind: more than 10 points

Each status shows a word and an icon, not colour alone.

---

## Design

**First version** used the VisiLean design system tokens:
- neutral chrome, so colour appears only in data marks and status
- light and dark themes
- `—` for missing values
- tabular numbers
- tooltips on keyboard focus as well as hover
- reduced-motion support

**Current version** follows the layout and colours of the VisiLean LPS portfolio view:

```
https://salesos.visilean.com/lps-maturity/w/CAF1A4DE-9BB7-7E76-6A82-925433623BDE
```

It takes these from that page:
- the white header and navy gradient banner with glass tiles
- the search, dropdown and sort-pill toolbar
- project rows with badges, a 2×2 grid of thin bars and a sparkline. The reference's ring and tag chips have since been replaced: the ring by a plan vs actual gauge, and the tag chips by the title line.
- the reference's own colour values, read from its stylesheet: navy `#002d62` / `#0a2540`, info cyan `#00618a`, blue `#0e8bdf`, and the good, warning and critical status set

The accessibility rules from the first version were kept.

The page works at phone width: the rows stack, and wide tables scroll inside their card. It was checked in headless Chrome at desktop and phone width, in both themes, with no script errors.

---

## Assumptions and known limits

- **Weekly vs monthly at the data date.** Both views give the same value at the data date. Between month ends, the weekly curve shows the movement that the monthly curve smooths over.
- **The 6-month window is in calendar months.** It always ends at the data-date month, so the last point is the data date itself, not a full month-end. The "6 months" of gain runs from the end of the month before the window to the data date.
- **COD slip is always zero.** Baseline and forecast COD are identical for every project in the source data.
- **The gauge shows planned and actual %, not a health score.** SPI is only used for its colour and appears in its tooltip.
- **Weighting.** Portfolio percentages are weighted by MW. Weighting by activity weightage or by cost would give different portfolio figures.

---

## Snapshot figures (data date 30 Sep 2026)

| Project | Planned | Actual | SPI | Eng. actual | Proc. actual | Constr. actual | COD forecast |
|---|---|---|---|---|---|---|---|
| Adani S6a | 35.3% | 30.4% | 0.86 | 98.4% | 39.4% | 7.0% | 24 Jul 2027 |
| Adani S7 | 35.1% | 30.5% | 0.87 | 99.2% | 37.9% | 7.8% | 17 Jun 2027 |
| ABREL Talaja | 97.3% | 56.7% | 0.58 | 100% | 65.0% | 30.0% | 29 Oct 2026 |
| NTPC Bikaner | 9.8% | 6.5% | 0.66 | 18.2% | 0.0% | 0.1% | 11 Nov 2027 |
| SJVN Khavda | 38.5% | 8.5% | 0.22 | 60.4% | 13.3% | 1.1% | 16 Jun 2027 |
| Floating Solar | 33.7% | 10.2% | 0.30 | 36.3% | 14.1% | 1.8% | 3 May 2027 |
| **Portfolio (MW-weighted)** | **35.7%** | **22.3%** | **0.62** | 71.7% | 26.8% | 6.1% | |

Progress gained in the last 6 months (end of Mar 2026 → 30 Sep 2026), in percentage points:

| Project | Actual gained | Planned gain |
|---|---|---|
| Adani S6a | +19.7 | +23.4 |
| Adani S7 | +19.1 | +22.7 |
| ABREL Talaja | +24.0 | +31.3 |
| NTPC Bikaner | +6.5 | +9.8 |
| SJVN Khavda | +5.5 | +35.4 |
| Floating Solar | +6.4 | +31.7 |
| **Portfolio (MW-weighted)** | **+13.7** | **+24.3** |

The portfolio gained 10.7 points less than planned over the 6 months.

---

## Possible next steps

1. Review the layout, wording and status thresholds on the page.
2. Run the rollout checklist in [HOW_TO_INTEGRATE.md](HOW_TO_INTEGRATE.md) §4.
3. Link it from the site and share it, only once KP has approved it.

---

## Change log

**5 Oct 2026: integrated into the repo.**

- Moved the builder into `scripts/` (template, config, `build_portfolio.py`) and added `refresh-portfolio.yml` and the sync health check. See [HOW_TO_INTEGRATE.md](HOW_TO_INTEGRATE.md).
- **Fixed "Plan" at the data date.** In the Monthly view, the S-curve statline, the chart's "Plan x%" label, the banner's "Gained · 6 mo" plan and the row sparkline tooltips used to read plan at the **end** of the data-date month. Actual was read at the data date. The two coincided on 30 Sep, a month end. On 5 Oct the statline read Plan 59.5% (31 Oct) against the banner's 46.3%. All of these now use plan at the data date, the same value as the banner. The month-end points on the curve are unchanged. The 30 Sep figures are unaffected.

**5 Oct 2026: weekly S-curve, overall statline, steady page height.** This was edited by hand in `portfolio/index.html`, with data from `weekly.js`.

- **S-curve statline:** now shows overall progress at the data date (Actual 22.3%, Plan 35.8%, Gap −13.5 pts for the portfolio) instead of the 6-month gain.
- **S-curve switch:** added Monthly / Weekly. Weekly has 45° week labels, scrolls sideways only when needed, keeps the y-axis fixed and opens at the data date. Monthly is unchanged.
- **Weekly data:** added the `weeks` and `wsc` series for every project (see 3a).
- **Banner:** Actual and Plan now use the two-decimal values, so Plan reads 35.8% to match the S-curve. It read 35.7% before, a rounding difference.
- **Page height:** `main` now keeps its tallest height, so applying a filter no longer collapses the page.

**5 Oct 2026: Actual / Plan everywhere, plan segments restyled.** This was edited by hand in `portfolio/index.html`.

- **Gauge:**
  - removed the plan tick
  - the plan arc is now a solid grey with a rounded end
- **Row bars:** the plan tick was replaced by a stacked bar like the gauge. Each bar shows actual in its status colour, grey up to plan with a rounded end, and light grey for the rest. Values read `Actual/Plan`.
- **EPC bars:** the amber shortfall segment now has a rounded end.
- **Wording:** labels and tooltips across the page now use "Actual" and "Plan" consistently. This replaces "actual gained", "planned gain", "of x% planned", "vs plan" and "Planned (baseline)".
  - the S-curve statline now reads Actual / Plan / Gap
  - the EPC headline reads `Actual% / Plan%`
  - the chart tooltips list Actual first
- **Colour:** added a `--plan-seg` colour token, set separately for light and dark themes. The gauge and the row bars share it.
- **Layout:** the row bars column widened from 300 px to 340 px to fit the `Actual/Plan` values.

**5 Oct 2026: layout changes to rows, EPC bars, S-curve and toolbar.** This was edited by hand in `portfolio/index.html`.

- **S-curve:**
  - removed the separate "S-curve · last 6 months" card
  - the full S-curve now spans the full width
  - the 6-month statline (actual gained, planned gain, vs plan) moved above the chart and follows the chart's scope and phase
- **EPC-wise bifurcation:**
  - the planned tick on each bar was replaced by a stacked bar: green actual, amber shortfall to plan, grey remainder
  - values now read `actual/planned`
- **Project rows:**
  - the SPI ring was replaced by a plan vs actual gauge
  - the tag chips were removed
  - capacity and location now follow the project name in the title
  - the sparkline caption no longer shows the points gained
  - rows are grouped into Solar and Wind
- **Toolbar:**
  - removed the Type filter; Solar and Wind are now the row groups
  - the search box is wider

**5 Oct 2026: PPC and KPIs removed, 6-month S-curve added.** This was edited by hand in `portfolio/index.html`, not produced by `build.py`.

Removed:
- the PPC chart, the banner's PPC tile and the per-row PPC sparkline
- the Key performance indicators section: the Design (documents), Procurement (PO) and Execution cards
- the documents and POs counts and the "No design documents" badge from project rows
- the `ppc`, `docs` and `po` fields from the inline data

Added:
- the "S-curve · last 6 months" card
- the "Gained · 6 mo" banner tile
- the 6-month actual-progress sparkline in each row

The full S-curve and the new 6-month card now share one chart-drawing function.
