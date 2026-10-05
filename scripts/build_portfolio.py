# -*- coding: utf-8 -*-
"""Build portfolio/index.html from the project pages already in the repo.

    python scripts/build_portfolio.py                 # reads ./<id>/, writes ./portfolio/
    python scripts/build_portfolio.py --src DIR --out DIR

No VisiLean call and no token: every figure is replayed from the inline DATA of the
published project pages (scripts/projects/portfolio.json lists them), using the
project template's own formulas - wgt / planPct / fcPct / actPctAt from
scripts/ntpc_dash_template_v3.html. See portfolio/PORTFOLIO_README.md for the maths
and portfolio/HOW_TO_INTEGRATE.md for the wiring.

Fails the build if the recalculated overall plan / actual drift from a project's own
meta.json by more than 0.1 points, or if the working-day calendar does not land on the
project's month ends - both mean the project template changed under us.
"""
import bisect, datetime as dt, hashlib, json, math, os, re, sys, time

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(HERE)


def arg(name, default):
    return sys.argv[sys.argv.index(name) + 1] if name in sys.argv else default


SRC = arg("--src", REPO)
OUT = arg("--out", os.path.join(REPO, "portfolio"))

AT = {"ENG": "Engineering", "SUP": "Procurement - Supply", "SVC": "Procurement - Services",
      "CON": "Construction"}
MONS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]


def r2(v):
    """JS Math.round(v*100)/100 - half rounds up, not to even."""
    return math.floor(v * 100 + 0.5) / 100


def num(x):
    """JS arithmetic treats null as 0."""
    return 0 if x is None else x


def tidy(o):
    """Write 28.0 as 28, the way JSON.stringify does, so the payload is stable."""
    if isinstance(o, float) and o.is_integer():
        return int(o)
    if isinstance(o, list):
        return [tidy(x) for x in o]
    if isinstance(o, dict):
        return {k: tidy(v) for k, v in o.items()}
    return o


def jsum(xs):
    """Plain left-to-right addition like JS reduce. Python 3.12+ sum() compensates float
    error, which moves values that sit on a rounding boundary by 0.01."""
    t = 0
    for x in xs:
        t += x
    return t


def parse_iso(s):
    y, m, d = (int(x) for x in s.split("-"))
    return dt.date(y, m, d)


def read_data(pid):
    src = open(os.path.join(SRC, pid, "index.html"), encoding="utf-8").read()
    m = re.search(r"const DATA = (\{.*?\});\n", src, re.S)
    if not m:
        sys.exit(f"{pid}/index.html: no inline DATA")
    meta = json.load(open(os.path.join(SRC, pid, "meta.json"), encoding="utf-8"))
    return json.loads(m.group(1)), meta


class Project:
    """One project page's rows, calendar and the template's formulas over them."""

    def __init__(self, D):
        self.C = {c: i for i, c in enumerate(D["cols"])}
        for need in ("type", "wt", "dur", "bES", "fES", "fEF", "pct"):
            if need not in self.C:
                sys.exit(f"column '{need}' missing from DATA.cols - the project template changed")
        self.L, self.SW = D["leaves"], D["meta"]["statusWd"]
        cal = (D.get("cfg") or {}).get("calendar") or {}
        off = set(cal["weeklyOff"]) if isinstance(cal.get("weeklyOff"), list) else {6}
        d = parse_iso(str(cal.get("startDate") or "2026-05-07"))
        self.WD = []
        while len(self.WD) < 1200:  # same length as the template's axis
            if d.weekday() not in off:
                self.WD.append(d)
            d += dt.timedelta(days=1)

    def wd_at(self, date):
        """Working-day position at the end of a date = working days up to and including it."""
        return bisect.bisect_right(self.WD, date)

    def phase(self, ph):
        t = self.C["type"]
        keep = {"all": lambda r: True,
                "E": lambda r: r[t] == AT["ENG"],
                "P": lambda r: r[t] in (AT["SUP"], AT["SVC"]),
                "C": lambda r: r[t] == AT["CON"]}[ph]
        return [r for r in self.L if keep(r)]

    # -- the template's formulas, line for line --
    def wgt(self, rows):
        wt, dur = self.C["wt"], self.C["dur"]
        c = jsum((r[wt] if num(r[wt]) > 0 else 0) for r in rows)
        if c > 0:
            return lambda r: r[wt] if num(r[wt]) > 0 else 0
        return lambda r: num(r[dur])

    def wsum(self, rows):
        w = self.wgt(rows)
        return jsum(w(r) for r in rows) or 1

    def _ramp(self, rows, at, start):
        s, dur = self.C[start], self.C["dur"]
        w, W = self.wgt(rows), self.wsum(rows)
        return 100 * jsum(min(1, max(0, (at - num(r[s])) / max(.5, num(r[dur])))) * w(r)
                         for r in rows) / W

    def plan_pct(self, rows, at):
        return self._ramp(rows, at, "bES")

    def fc_pct(self, rows, at):
        return self._ramp(rows, at, "fES")

    def elapsed_of(self, r, at):
        C = self.C
        if num(r[C["pct"]]) >= 100:
            fin = r[C["aef"]] if ("aef" in C and r[C["aef"]] is not None) else r[C["fEF"]]
            return 1 if at >= num(fin) else 0
        return max(0, (at - num(r[C["fES"]])) / max(.5, num(r[C["dur"]])))

    def act_pct_at(self, rows, at):
        pct = self.C["pct"]
        w, W = self.wgt(rows), self.wsum(rows)
        return 100 * jsum(min(num(r[pct]) / 100, self.elapsed_of(r, at)) * w(r) for r in rows) / W


def month_end(label):
    """'Aug-27' -> 2027-08-31"""
    y, m = 2000 + int(label[4:]), MONS.index(label[:3]) + 1
    return dt.date(y + (m == 12), m % 12 + 1, 1) - dt.timedelta(days=1)


def main():
    cfg = json.load(open(os.path.join(HERE, "projects", "portfolio.json"), encoding="utf-8"))
    loaded = []
    for pc in cfg["projects"]:
        D, meta = read_data(pc["id"])
        loaded.append((pc, D, meta, Project(D)))

    # week ends fall on the latest data date's weekday, 7 days apart
    status_iso = max(meta["statusIso"] for _, _, meta, _ in loaded)
    sd = parse_iso(status_iso)

    out, errors = [], []
    for pc, D, meta, P in loaded:
        pid, SW = pc["id"], P.SW
        phases = {ph: P.phase(ph) for ph in ("all", "E", "P", "C")}

        # check 1: overall figures match what the project page itself shows
        for key, val in (("plan", P.plan_pct(P.L, SW)), ("act", P.act_pct_at(P.L, SW))):
            if abs(val - meta[key]) > 0.1 + 1e-9:
                errors.append(f"{pid}: recalculated {key} {val:.2f} vs meta.json {meta[key]}")

        # check 2: the calendar lands on the page's month ends, so weekly and monthly agree
        for m in D["months"]:
            if P.wd_at(month_end(m["label"])) != m["wd"]:
                errors.append(f"{pid}: {m['label']} month end is working day "
                              f"{P.wd_at(month_end(m['label']))}, page says {m['wd']}")

        # monthly: actual at every month end passed, plus the data date inside the current month
        months = D["months"]
        n_past = sum(1 for m in months if m["wd"] <= SW)
        tail = n_past < len(months) and (n_past == 0 or months[n_past - 1]["wd"] < SW)
        sc = {}
        for ph, rows in phases.items():
            act = [r2(P.act_pct_at(rows, m["wd"])) for m in months[:n_past]]
            if tail:
                act.append(r2(P.act_pct_at(rows, SW)))
            sc[ph] = {"plan": [r2(P.plan_pct(rows, m["wd"])) for m in months],
                      "fc": [r2(P.fc_pct(rows, m["wd"])) for m in months],
                      "act": act + [None] * (len(months) - len(act))}

        # weekly: first week end on/after day 1, through the first on/after the last month end
        first, last_end = P.WD[0], month_end(months[-1]["label"])
        w = sd
        while w > first:
            w -= dt.timedelta(days=7)
        if w < first:
            w += dt.timedelta(days=7)
        weeks = [w]
        while weeks[-1] < last_end:
            weeks.append(weeks[-1] + dt.timedelta(days=7))
        wsc = {}
        for ph, rows in phases.items():
            wsc[ph] = {"plan": [r2(P.plan_pct(rows, P.wd_at(d))) for d in weeks],
                       "fc": [r2(P.fc_pct(rows, P.wd_at(d))) for d in weeks],
                       "act": [r2(P.act_pct_at(rows, min(P.wd_at(d), SW))) if d <= sd else None
                               for d in weeks]}

        epc = {ph: {"n": len(rows), "plan": r2(P.plan_pct(rows, SW)),
                    "act": r2(P.act_pct_at(rows, SW))} for ph, rows in phases.items()}

        rec = {"id": pid, "name": pc["name"], "full": meta["project"]}
        rec.update({k: pc[k] for k in ("type", "mw", "site", "state", "contract")})
        rec.update({k: meta[k] for k in ("statusIso", "generatedAt", "startDate", "plan", "act",
                                         "spi", "codBaseline", "codForecast", "baselineFinish",
                                         "forecastFinish")})
        rec.update({"total": len(P.L), "done": meta["done"], "late": meta["late"], "epc": epc,
                    "months": [f"{month_end(m['label']):%Y-%m}" for m in months], "sc": sc,
                    "href": f"../{pid}/index.html",
                    "weeks": [d.isoformat() for d in weeks], "wsc": wsc})
        out.append(rec)
        print(f"{pid:<9} {meta['statusIso']}  plan {epc['all']['plan']:6.2f}  act "
              f"{epc['all']['act']:6.2f}  {len(months)} months  {len(weeks)} weeks")

    if errors:
        print("\n".join("ERROR " + e for e in errors), file=sys.stderr)
        sys.exit("self-check failed - not writing (fix the builder, do not loosen the check)")

    payload = json.dumps(tidy({"projects": out}), separators=(",", ":"), ensure_ascii=True)
    tpl = open(os.path.join(HERE, "portfolio_template.html"), encoding="utf-8").read()
    assert tpl.count("__PAYLOAD__") == 1, "template must hold exactly one __PAYLOAD__"
    html = tpl.replace("__PAYLOAD__", payload)
    assert "accessToken" not in html, "token leak!"

    os.makedirs(OUT, exist_ok=True)
    open(os.path.join(OUT, "index.html"), "w", encoding="utf-8", newline="").write(html)
    now = time.time()
    ist = dt.datetime.fromtimestamp(now, dt.timezone(dt.timedelta(hours=5, minutes=30)))
    json.dump({"generatedAt": ist.strftime("%d-%b-%Y %H:%M IST"),
               "generatedAtEpoch": int(now),
               "statusDate": sd.strftime("%d-%b-%Y"),
               "statusIso": status_iso,
               "projects": [p["id"] for p in out]},
              open(os.path.join(OUT, "meta.json"), "w", encoding="utf-8"))
    open(os.path.join(OUT, ".datahash"), "w").write(hashlib.sha256(payload.encode()).hexdigest())
    open(os.path.join(OUT, ".tplhash"), "w").write(hashlib.sha256(tpl.encode("utf-8")).hexdigest())

    spread = sorted({p["statusIso"] for p in out})
    if len(spread) > 1:
        print(f"note: projects have different data dates {spread[0]} .. {spread[-1]}")
    print(f"built {os.path.join(OUT, 'index.html')} {len(html)} bytes | "
          f"payload {len(payload)} bytes | {len(out)} projects")


if __name__ == "__main__":
    main()
