# -*- coding: utf-8 -*-
"""NTPC dashboard data v2 — LIVE from the VisiLean PowerBI APIs.
   Tokens come from env (VL_TOKEN_TASK / VL_TOKEN_HISTORY / VL_TOKEN_CONSTRAINTS,
   set as GitHub Actions secrets) or a local vl_tokens.json next to this script
   (never committed). Pure Python. Emits scripts/ntpc_dashboard_data_v2.json."""
import sys, io, json, os, re, datetime, urllib.request
from collections import defaultdict, deque, Counter
try:
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
except Exception:
    pass
SCR = os.path.dirname(os.path.abspath(__file__))

BASE = "https://app.visilean.net/pb/PowerBiAPI/resource/powerBi/getData/visilean"
PROJECT = "7A2842F6-7E5F-DB7C-3E7F-0EE7EF60698F"

def _tokens():
    t = {"task": os.environ.get("VL_TOKEN_TASK", ""),
         "history": os.environ.get("VL_TOKEN_HISTORY", ""),
         "constraintLog": os.environ.get("VL_TOKEN_CONSTRAINTS", "")}
    if not t["task"]:
        f = os.path.join(SCR, "vl_tokens.json")
        if os.path.exists(f):
            t.update(json.load(open(f, encoding="utf-8")))
    if not t["task"]:
        raise SystemExit("no VisiLean tokens: set VL_TOKEN_* env vars or scripts/vl_tokens.json")
    return t

TOKENS = _tokens()

def fetch(kind, attempts=3):
    tp = "task" if kind == "history" else kind
    url = f"{BASE}?accessToken={TOKENS[kind]}&projectId={PROJECT}&type={tp}"
    if kind == "history":
        # these flags are what make activityHistory come back populated - it is the
        # audit trail the variance reasons are written into
        url += ("&IncludeStatusChange=true&IncludeReschedule=true"
                "&IncludeQuantities=true&IncludeConstraintNotes=true")
    last = None
    for i in range(attempts):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "VisiLean-MIS-v2"})
            return json.loads(urllib.request.urlopen(req, timeout=120).read().decode("utf-8", errors="replace"))
        except Exception as e:
            last = e
            print(f"fetch {kind} attempt {i+1}/{attempts} failed: {e}")
            if i + 1 < attempts:
                import time as _t; _t.sleep(15 * (i + 1))
    raise last

print("fetching VisiLean APIs...")
try:
    TASKS = fetch("task")
    CONS = fetch("constraintLog")
    try:
        HIST = fetch("history")
    except Exception as he:
        print("history feed unavailable, variance reasons will be empty:", he)
        HIST = []
except Exception as e:
    # transient VisiLean outage: skip this cycle cleanly; the next run recovers
    print(f"SKIP this cycle - VisiLean API unreachable after retries: {e}")
    sys.exit(0)
print("tasks:", len(TASKS), "| constraints:", len(CONS), "| history:", len(HIST))
RELS = json.load(open(os.path.join(SCR, "vl_relations.json"), encoding="utf-8"))

# ---------- calendar ----------
START = datetime.date(2026, 5, 7)
TODAY = datetime.date.today()
TARGET_WD = 470
wdates = []
d = START
while len(wdates) < 1200:
    if d.weekday() != 6:
        wdates.append(d)
    d += datetime.timedelta(days=1)
STATUS_WD = max(i for i, dt in enumerate(wdates) if dt <= TODAY) + 1

def pdate(s):
    s = (s or "").strip()
    if not s: return None
    try: return datetime.datetime.strptime(s.split(" ")[0], "%d/%m/%Y").date()
    except Exception: return None

def wd_s(dt_): return next((i for i, x in enumerate(wdates) if x >= dt_), 0)
def wd_f(dt_): return max((i for i, x in enumerate(wdates) if x <= dt_), default=0) + 1
norm = lambda s: re.sub(r"[^a-z0-9]", "", str(s or "").lower())

def money(s):
    try: return float(re.sub(r"[^\d.]", "", s or "")) if s and re.search(r"\d", s) else 0.0
    except Exception: return 0.0

recs = {}
milestones_raw = []
NA_SKIPPED = []
GUID = {t.get("guid"): t for t in TASKS if t.get("guid")}
_synth = [0]
for t in TASKS:
    try: uid = int(t.get("externalId"))
    except Exception:
        # Created directly in VisiLean, so no MSP UniqueID (drawing-revision rows
        # R0/R1/R2 etc). VisiLean counts these in "All Tasks" -> so do we.
        _synth[0] += 1
        uid = -_synth[0]
    cf = t.get("customField") or {}
    L = [cf.get(f"Level {i}", "") or "" for i in range(1, 8)]
    bs, bf = pdate(t.get("baselineStartDate")), pdate(t.get("baselineEndDate"))
    # "not baselined": VisiLean counts these in All Tasks but leaves them out of
    # Completed / Delayed, because there is no baseline to measure them against.
    # Rows created straight in VisiLean (drawing revisions R0/R1/R2) look like this.
    nodate = 1 if (bs is None or bf is None) else 0
    if bs is None or bf is None:
        bs2, bf2 = pdate(t.get("plannedStartDate")), pdate(t.get("plannedEndDate"))
        bs, bf = bs or bs2, bf or bf2
    if bs is None or bf is None:
        # Undated row: inherit the parent's window so it can be placed, and flag it
        # so every date-driven metric skips it. VisiLean does the same - such rows
        # appear in All Tasks but not in Completed / Delayed.
        p = GUID.get(t.get("parentGUID"))
        pbs = pbf = None
        if p is not None:
            pbs = pdate(p.get("baselineStartDate")) or pdate(p.get("plannedStartDate"))
            pbf = pdate(p.get("baselineEndDate")) or pdate(p.get("plannedEndDate"))
        bs = bs or pbs or START
        bf = bf or pbf or bs
    r = {"uid": uid, "name": t.get("taskName") or "", "parent": bool(t.get("parent")),
         "L": L, "atype": cf.get("Activity Type", ""), "pkgcf": cf.get("Package", ""),
         "deptcf": cf.get("Department", ""),
         "owner": cf.get("Owner.", "") or cf.get("Owner", ""),
         "assignee": t.get("owner") or "", "loc": t.get("location") or "Off-site / Office",
         "bES": wd_s(bs), "bEF": wd_f(bf),
         "pES": (wd_s(pdate(t.get("plannedStartDate"))) if pdate(t.get("plannedStartDate")) else None),
         "pEF": (wd_f(pdate(t.get("plannedEndDate"))) if pdate(t.get("plannedEndDate")) else None),
         "aS": pdate(t.get("actualStartDate")), "aF": pdate(t.get("actualEndDate")),
         "pct": float(t.get("percentComplete") or 0),
         "vls": t.get("status") or "Not Committed",
         "qty": t.get("totalQuantity"), "uom": t.get("quantityUnits") or "",
         "cost": money(cf.get("Cost")),
         # KP 26-Aug: progress weight comes from VisiLean's own "Weightage" custom
         # field - the approved Rev-2 model, which sums to ~100 across the project.
         # Cost is kept only for the budget card.
         "wt": money(cf.get("Weightage")), "nd": nodate,
         "note": t.get("notes") or "", "desc": t.get("description") or "",
         "crit": (cf.get("Critical Activity") or ""),
         "psd": (pdate(t.get("plannedStartDate")) or bs),
         "ped": (pdate(t.get("plannedEndDate")) or bf), }
    try: r["dur"] = max(0.0, float(t.get("baselineDuration") or t.get("plannedDuration") or 0))
    except Exception: r["dur"] = max(0.0, float(r["bEF"] - r["bES"]))
    if r["dur"] == 0 and not r["parent"]:
        r["dur"] = max(0.0, float(r["bEF"] - r["bES"]))
    if (L[0] or "").startswith("Key Milestones") or re.match(r"^MS-\d", r["name"]):
        if not r["parent"]: milestones_raw.append(r)
        continue
    # KP rule 26-Aug: an activity whose trade is "Not Applicable" is out of scope for
    # this project. Dropping it here removes it from every count, every progress and
    # weightage calculation, and every table - not just from the views.
    if norm(t.get("trade")) in ("notapplicable", "na"):
        NA_SKIPPED.append(r["name"])
        continue
    recs[uid] = r

leafs = {u: r for u, r in recs.items() if not r["parent"]}
print("usable leaves:", len(leafs), "| milestones:", len(milestones_raw),
      "| excluded (trade = Not Applicable):", len(NA_SKIPPED))

# ---------- forecast = VisiLean PLANNED dates, verbatim (KP rule 17-Aug-2026) ----------
# No dashboard-side re-forecasting: VisiLean owns scheduling. Planned start/end
# from the API ARE the forecast; baseline start/end are the baseline.
succ = defaultdict(list)
for pu, su, code, lag in RELS:
    if pu in leafs and su in leafs:
        succ[pu].append((su, code, lag))
fES, fEF = {}, {}
for u, r in leafs.items():
    fES[u] = float(r["pES"] if r["pES"] is not None else r["bES"])
    fEF[u] = float(r["pEF"] if r["pEF"] is not None else r["bEF"])
    if fEF[u] < fES[u]:
        fEF[u] = fES[u]
print(f"forecast = VisiLean planned dates; finish {max(fEF.values()):.0f} wd = {wdates[int(round(max(fEF.values())))-1]}")

# ---------- total float, computed on VisiLean planned dates ----------
END = max(fEF.values())
LF = {u: float(END) for u in leafs}
order = sorted(leafs, key=lambda u: -fEF[u])
for _ in range(3):
    for u in order:
        for (v, code, lag) in succ[u]:
            dv = leafs[v]["dur"]
            if code == "SS": cand = LF[v] - dv - lag + leafs[u]["dur"]
            elif code == "FF": cand = LF[v] - lag
            else: cand = LF[v] - dv - lag
            if cand < LF[u]: LF[u] = cand
TF = {u: max(0.0, LF[u] - fEF[u]) for u in leafs}
# How much of the schedule is actually wired into the logic network. The relations
# sidecar is a static capture; when activities are deleted in VisiLean the chains
# break and float stops being meaningful, so publish the coverage alongside it.
_inlogic = set()
for pu, su, code, lag in RELS:
    if pu in leafs and su in leafs: _inlogic.add(pu); _inlogic.add(su)
LOGIC_COV = round(100.0 * len(_inlogic) / max(1, len(leafs)), 1)
print(f"logic coverage: {LOGIC_COV}% of leaves are in the relation network")

# ---------- classification ----------
DEPTS = [("initiation", "Project Initiation"), ("engineering", "Design & Engineering"),
         ("quality", "Quality Assurance"), ("supply", "Procurement - Supply"),
         ("services", "Procurement - Services"),
         ("regulatory", "Regulatory & Statutory"), ("execution", "Execution & Construction"),
         ("tnc", "Testing & Commissioning"), ("hoto", "HOTO (Handover)")]
def dept_of(r):
    dcf = norm(re.sub(r"^\s*\d+\s*", "", r.get("deptcf") or ""))
    l1 = dcf if dcf else norm(r["L"][0])
    l2 = norm(r["L"][1])
    if l1.startswith("testing"): return "tnc"
    if l1.startswith("projectinitiation"): return "initiation"
    if l1.startswith("design"): return "engineering"
    if l1.startswith("quality"): return "quality"
    if l1.startswith("procurement"): return "services" if "services" in l2 else "supply"
    if l1.startswith("regulatory") or l1.startswith("liaisoning"): return "regulatory"
    if l1.startswith("hoto"): return "hoto"
    if l1.startswith("execution"):
        return "tnc" if (r["L"][2] or "").startswith("Testing & Commissioning") else "execution"
    return "initiation"

ENG_STAGE = [("asbuilt", "As-Built"), ("gfcissuance", "GFC"), ("finalacceptance", "Acceptance"),
             ("submissiontoclient", "Submission"), ("internalapproval", "Int. Approval"),
             ("internalchecking", "Int. Check"), ("drafting", "Drafting"), ("finalreport", "Acceptance")]
PROC_STAGE = [
    (("rfppreparation", "fqap", "mqap", "additionalvendor", "vendorapprovalfromclient", "prfraising",
      "floatingofrfp", "vendorproposal", "technicalbid", "commercialbid", "cspreparation", "eauction"), "Tender"),
    (("managementapproval", "pqplacement", "poplacement", "abg", "advancepayment"), "Order & Advance"),
    (("designdocument",), "Vendor Docs"),
    (("manufacturingclearance", "stageinspection", "predispatch", "assigninspector", "collectshare",
      "inspectionreport", "submitquality", "compliancereport", "mdccissuance", "sharemdcc"), "Mfg & Quality"),
    (("jmsabstract", "dispatchofmaterial", "incomingmaterial", "grnatsite"), "Delivery / JMS"),
    (("paymentprocess", "invoicebooking", "finalpaymentprocess"), "Payments"),
]
EXEC_STAGE = [
    (("boundaryfencing", "roadconstruction", "drainage", "landallocation", "siteclearance",
      "civilworks", "platformconstruction", "foundation", "watchtower", "securit"), "Civil & Foundations"),
    (("pilefoundation", "pile"), "Civil & Foundations"),
    (("modulemountingstructureinstallation", "mmsinstallation", "mms"), "MMS & Module"),
    (("moduleinstallation", "module"), "MMS & Module"),
    (("dcstring", "dcpower", "dccable", "scb", "stringcombiner"), "DC Works"),
    (("htcable", "accable", "acht", "jointing", "termination"), "AC / HT Works"),
    (("earthing", "lainstallation", "lightning"), "Earthing & LA"),
    (("equipmentinstallation", "wmsinstallation", "abtmeter", "peripherylight",
      "icrlights", "nomenclature", "idtfoundation"), "Equipment"),
    (("poolingsubstation", "pss", "switchyard", "bay"), "PSS & Switchyard"),
    (("rfi", "ncr", "siteobservation", "sitestorage", "testingwitness", "verificationofchecklist"), "Quality Process"),
]
SUB_MAP = [
    (("rfppreparation", "draftingconceptual", "internalcheckingof", "internalapproval",
      "submissiontocustomer", "finalacceptanceof"), "Design"),
    (("additionalvendorapprovallist", "vendorapprovalfromclient", "prfraising", "floatingofrfp",
      "vendorproposalcollection", "technicalbidevaluation", "commercialbidevaluation",
      "cspreparation", "eauction"), "Tender"),
    (("managementapproval", "pqplacement", "poplacement"), "PO"),
    (("abg", "advancepaymentrelease"), "Advance"),
    (("designdocumentreview", "designdocumentapproval", "fqapreview", "mqapreview",
      "fqapapproval", "mqapapproval"), "Vendor Docs"),
    (("manufacturingclearance", "stageinspection"), "Mfg"),
    (("predispatch", "assigninspector", "collectshare", "inspectionreport", "submitquality",
      "compliancereport", "mdccissuance", "sharemdcc", "jmsabstract"), "Inspection / MDCC-JMS"),
    (("dispatchofmaterial", "incomingmaterialinspection"), "Dispatch"),
    (("grnatsite",), "At Site"),
    (("paymentprocess", "invoicebooking", "finalpaymentprocess"), "Payment"),
]
BLOCK_RE = re.compile(r"(?i)^block[\s-]*(no)?\d+")
# A Level-4 value that appears under many different Packages is a process step,
# not a deliverable - "MQAP" sits under 32 supply packages, "Field Quality Plan &
# HSE" under 4. Only a Level 4 that belongs to a single Package is a real package
# item; anything shared falls back to the Package field so stages never surface as
# packages in the pipeline table.
L4_SPAN = defaultdict(set)
for _r in leafs.values():
    if _r["L"][3] and _r["pkgcf"]: L4_SPAN[_r["L"][3]].add(_r["pkgcf"])
rows = []
for r in sorted(leafs.values(), key=lambda x: x["uid"]):
    u = r["uid"]; dept = dept_of(r); ln = norm(r["name"]); L = r["L"]
    area = r["loc"] or "Off-site / Office"
    # Package = VisiLean 'Package' custom field VERBATIM (KP field-match rule 18-Aug);
    # Level-derived fallback only for rows where the field is empty in VisiLean.
    # Section = WBS Level 2, i.e. the level directly under the department, for every
    # department. The department page's section dropdown then sits one level above its
    # package dropdown (Level 3 / the Package field) instead of both listing Level 3.
    # For Supply and Services, Level 2 already reads "Supply" / "EPCC & I&C Services".
    sec = L[1] or L[0]
    if dept in ("supply", "services"):
        fb = L[2] or L[1]
    elif dept == "engineering":
        fb = L[3] or L[2] or L[1]
    elif dept in ("execution", "tnc"):
        cand = [x for x in L[2:6] if x and not BLOCK_RE.match(x) and norm(x) != "construction"]
        fb = cand[-1] if cand else (L[3] or L[2] or L[1])
    else:
        fb = L[1] or L[0]
    pkg = r["pkgcf"] or fb
    # Deepest WBS level that exists for this row. In Design & Engineering the Package
    # field carries the Level-3 group, so the Level-4 deliverable is the real package;
    # where Level 4 is blank this falls back to the Package field unchanged.
    item = L[3] if (L[3] and len(L4_SPAN.get(L[3], ())) == 1) else pkg
    stage = ""
    if dept == "engineering":
        stage = next((v for kk, v in ENG_STAGE if kk in ln), "Drafting" if "drafting" in ln else "")
    elif dept in ("supply", "services"):
        for keys, v in PROC_STAGE:
            if any(k in ln for k in keys): stage = v; break
    elif dept in ("execution", "tnc"):
        full = norm(pkg) + ln
        for keys, v in EXEC_STAGE:
            if any(k in full for k in keys): stage = v; break
        stage = stage or ("T&C" if dept == "tnc" else "Other Site Works")
        if dept == "tnc": stage = "T&C"
    sub = ""
    if dept in ("supply", "services"):
        sub = next((v for keys, v in SUB_MAP if any(k in ln for k in keys)), "Design")
    elif dept == "engineering":
        sub = stage
    vs = r["vls"]
    # Delayed (VisiLean-equivalent): not complete, and it should have started or
    # finished by today. Matches VisiLean's "Delayed Tasks" counter. The old test
    # (forecast finish >= 4 days past baseline) always read 0, because VisiLean's
    # planned dates equal the baseline until the schedule is actually rescheduled.
    dly = 0
    if not r["nd"] and r["pct"] < 100:
        if r["ped"] < TODAY or (r["psd"] < TODAY and r["pct"] == 0): dly = 1
    if r["pct"] >= 100 or vs == "Complete": state = "done"
    elif r["pct"] > 0 or vs in ("Started", "Warning", "Stopped"): state = "inprog"
    elif r["bES"] < STATUS_WD: state = "late"
    else: state = "future"
    rows.append([dept, r["atype"], area, str(pkg)[:70], str(sec)[:60], stage,
                 r["name"][:70], int(r["bES"]), int(r["bEF"]), int(round(fES[u])), int(round(fEF[u])),
                 round(r["pct"]), round(r["dur"], 1), r["qty"], r["uom"][:14],
                 int(round(TF.get(u, 0))), state,
                 (r["assignee"] or "")[:30], sub, round(r["cost"]), len(rows), vs,
                 (r["owner"] or "")[:40], r["nd"], dly, str(item)[:80], round(r["wt"], 6)])
n_crit = sum(1 for x in rows if x[15] <= 5 and x[16] != "done" and not x[23])

ms = []
for m in sorted(milestones_raw, key=lambda x: x["name"]):
    bw = m["bEF"]; fw = bw + max(0, STATUS_WD - 78)
    ms.append({"name": m["name"], "b": bw, "f": fw, "slip": fw - bw,
               "status": "done" if m["pct"] >= 100 else ("ontrack" if fw - bw <= 6 else ("watch" if fw - bw <= 15 else "late"))})

months = []
m0 = datetime.date(2026, 5, 31)
while m0 <= datetime.date(2027, 12, 31):
    months.append({"label": m0.strftime("%b-%y"), "wd": max((i for i, dt in enumerate(wdates) if dt <= m0), default=0) + 1})
    m0 = (m0 + datetime.timedelta(days=46)).replace(day=1) - datetime.timedelta(days=1)

WT_I = 26   # "wt" column - VisiLean's Weightage custom field (asserted below)
def w_of(x): return x[WT_I] if x[WT_I] and x[WT_I] > 0 else 0.0
WSUM = sum(w_of(x) for x in rows)
W = (lambda x: w_of(x)) if WSUM > 0 else (lambda x: x[12])
WT = sum(W(x) for x in rows) or 1.0
plan_pct = sum(min(1.0, max(0.0, (STATUS_WD - x[7]) / max(0.5, x[12]))) * W(x) for x in rows) / WT
act_pct = sum(x[11] / 100.0 * W(x) for x in rows) / WT
bfin = max(x[8] for x in rows); ffin = max(x[10] for x in rows)
NOW_UTC = datetime.datetime.now(datetime.timezone.utc)
IST_NOW = NOW_UTC.astimezone(datetime.timezone(datetime.timedelta(hours=5, minutes=30)))

meta = {"statusDate": TODAY.strftime("%d-%b-%Y"), "statusWd": STATUS_WD, "startDate": "07-May-2026",
        "project": "KPIGEL-NTPC Bikaner Block 8 · 200 MW",
        "baselineFinishWd": bfin, "forecastFinishWd": ffin,
        "baselineFinish": wdates[bfin - 1].strftime("%d-%b-%y"),
        "forecastFinish": wdates[ffin - 1].strftime("%d-%b-%y"),
        "codBaseline": wdates[bfin - 1].isoformat(), "codForecast": wdates[ffin - 1].isoformat(),
        "statusIso": TODAY.isoformat(),
        "plan": round(100 * plan_pct, 1), "act": round(100 * act_pct, 1),
        "spi": round(act_pct / plan_pct, 2) if plan_pct > 0.0005 else 0,
        "svPts": round(100 * (act_pct - plan_pct), 1),
        "svPct": round(100 * (act_pct - plan_pct) / plan_pct, 1) if plan_pct > 0.0005 else 0,
        "delayDays": ffin - bfin, "critical": n_crit,
        "done": sum(1 for x in rows if x[16] == "done" and not x[23]),
        "inprog": sum(1 for x in rows if x[16] == "inprog" and not x[23]),
        "late": sum(1 for x in rows if x[16] == "late" and not x[23]),
        "delayed": sum(1 for x in rows if x[24]), "logicCoverage": LOGIC_COV,
        "wtSum": round(sum(w_of(x) for x in rows), 3),
        "wtCoverage": round(100.0 * sum(1 for x in rows if w_of(x) > 0) / max(1, len(rows)), 1),
        "wtMissing": sum(1 for x in rows if not w_of(x)),
        "naExcluded": len(NA_SKIPPED),
        "total": len(rows), "totalTasks": len(rows) + len(ms),
        "undated": sum(1 for x in rows if x[23]),
        "source": "VisiLean live API",
        # KP reads this in India, so the stamp is IST. generatedAtEpoch is the same
        # instant in unix seconds, used by the page to work out how old the data is.
        "generatedAt": IST_NOW.strftime("%d-%b-%Y %H:%M IST"),
        "generatedAtEpoch": int(NOW_UTC.timestamp())}

# ---------- supply package delivery, straight off VisiLean's summary rows -------
# KP rule 25-Aug: the Long Lead table's Baseline / Forecast delivery must equal the
# dates VisiLean shows on the package summary row under Procurement > Supply.
_kids = defaultdict(list)
for t in TASKS:
    if t.get("parentGUID"): _kids[t["parentGUID"]].append(t)

def _descendants(t, depth=0):
    if depth > 6: return
    for c in _kids.get(t.get("guid"), []):
        yield c
        for g in _descendants(c, depth + 1): yield g

SUPPLY_DELIV = {}
for t in TASKS:
    cfx = t.get("customField") or {}
    if not t.get("parent"): continue
    if (cfx.get("Level 1") or "").strip() != "Procurement & Vendor Documents": continue
    if (cfx.get("Level 2") or "").strip() != "Supply": continue
    # Level 3 is set on the nested MQAP sub-summaries; the package summary leaves it blank
    if (cfx.get("Level 3") or "").strip(): continue
    if (t.get("taskName") or "").strip() in ("", "Supply"): continue
    pkgs = Counter()
    for d in _descendants(t):
        p = ((d.get("customField") or {}).get("Package") or "").strip()
        if p: pkgs[p] += 1
    if not pkgs: continue
    pkg = pkgs.most_common(1)[0][0]
    be, pe = pdate(t.get("baselineEndDate")), pdate(t.get("plannedEndDate"))
    if be is None and pe is None: continue
    # key must match the row's pkg column, which is truncated the same way
    SUPPLY_DELIV[str(pkg)[:70]] = {"b": wd_f(be or pe), "f": wd_f(pe or be)}
print("supply package delivery dates from VisiLean summaries:", len(SUPPLY_DELIV))

cons = []
for c in CONS:
    cons.append({"id": c.get("constrainId"), "title": c.get("title") or "", "desc": (c.get("discription") or "")[:200],
                 "author": c.get("author") or "", "owner": c.get("owner") or "",
                 "cat": (c.get("category") or "").strip() or "Uncategorised",
                 "pri": c.get("priority") or "—",
                 "created": c.get("creationDate") or "", "target": c.get("targetDate") or "",
                 "committed": c.get("commitmentDate") or "", "completed": (c.get("completionDate") or "").strip(),
                 "open": not (c.get("completionDate") or "").strip()})

# ---------- variance reasons (from the task-history audit trail) ----------
# Event phrasings VisiLean writes into activityHistory. The first four are the ones
# that represent a schedule variance.
EVENTS = [
    (r"started late",            "latestart",  "Started late"),
    (r"completed late",          "latefinish", "Completed late"),
    (r"(?:Start|End) Date changed", "resched", "Rescheduled"),
    (r"set to 'Not Ready'",      "notready",   "Set to Not Ready"),
    (r"started early",           "startearly", "Started early"),
    (r"completed early",         "finishearly","Completed early"),
    (r"started on time",         "startontime","Started on time"),
    (r"completed on time",       "finishontime","Completed on time"),
    (r"bulk completed",          "bulk",       "Bulk completed"),
    (r"was forced ready",        "forcedready","Forced ready"),
    (r"Constraint '",            "constraint", "Constraint raised"),
]
VARIANCE_KINDS = {"latestart", "latefinish", "resched", "notready"}

# VisiLean wraps the text the user typed with the note type; strip it before the
# category is read, or "Late completion note" is mistaken for a party.
NOTE_PREFIX_RE = re.compile(
    r"\b(late start note|late completion note|completion note|start note|"
    r"stopped note|rejection note|note added to task[^:]*|note added|note)\s*:\s*", re.I)

# The team writes reasons as "<Responsible party>: <Category>".
PARTIES = ["KP", "Client", "Vendor", "NTPC", "External", "Consultant",
           "Contractor", "Sub-contractor", "Subcontractor", "PMC", "Site", "Store"]
PARTY_RE = re.compile(r"\b(" + "|".join(PARTIES) + r")\s*:\s*([A-Za-z][A-Za-z&/ -]{1,24})", re.I)
# VisiLean also defines reasons with no responsible party, listed on their own in
# Project Settings > Custom Reasons.
STANDALONE = ["Predecessor", "Weather", "Rework", "Design Change", "Statutory"]
STANDALONE_RE = re.compile(r"^\s*(" + "|".join(STANDALONE) + r")\s*\.?\s*$", re.I)
CAT_CANON = {"machinery": "Machine", "machines": "Machine", "machine": "Machine",
             "materials": "Material", "material": "Material",
             "manpower": "Manpower", "labour": "Manpower", "labor": "Manpower",
             "approval": "Approval", "approvals": "Approval",
             "external": "External", "design": "Design", "drawing": "Design",
             "weather": "Weather", "payment": "Payment", "permit": "Statutory"}

def strip_html(x):
    x = re.sub(r"<br\s*/?>", " ", x or "")
    x = re.sub(r"</p>", " ", x)
    x = re.sub(r"<[^>]+>", "", x)
    for a, b in (("&amp;", "&"), ("&nbsp;", " "), ("&lt;", "<"), ("&gt;", ">"),
                 ("&quot;", '"'), ("&#39;", "'")):
        x = x.replace(a, b)
    return re.sub(r"\s+", " ", x).strip()

def canon_cat(c):
    c = re.sub(r"\s+", " ", (c or "").strip(" .,-")).strip()
    return CAT_CANON.get(c.lower(), c[:24].title() if c else "")

def split_events(hist):
    """Cut the audit trail into one chunk per event, keeping the note with it."""
    txt = strip_html(hist)
    if not txt: return []
    idx = [m.start() for m in re.finditer(r"(?=Task '|Note added to task '|Constraint ')", txt)]
    if not idx: idx = [0]
    chunks = [txt[a:b] for a, b in zip(idx, idx[1:] + [len(txt)])]
    out = []
    for ch in chunks:
        kind, label = "other", "Other"
        for pat, k, lab in EVENTS:
            if re.search(pat, ch, re.I): kind, label = k, lab; break
        m = re.search(r"Note added:\s*(.*)$", ch, re.I) or \
            re.search(r"Note:\s*(.*)$", ch, re.I) or \
            re.search(r"by [^:]+:\s*(.*)$", ch, re.I)
        note = NOTE_PREFIX_RE.sub("", (m.group(1).strip() if m else "")).strip()
        who = ""
        w = re.search(r"\bby ([A-Za-z][\w.\- ]{1,30}?)(?=[.:,]|$)", ch)
        if w: who = w.group(1).strip()
        out.append({"kind": kind, "label": label, "note": note, "by": who})
    return out

# history rows are snapshots; keep the richest trail seen per activity
hist_by_uid = {}
for h in HIST:
    try: hu = int(h.get("externalId"))
    except Exception: continue
    a = strip_html(str(h.get("activityHistory") or ""))
    if not a: continue
    if len(a) > len(hist_by_uid.get(hu, "")): hist_by_uid[hu] = a

reasons = []
cat_tally = Counter()
for r in sorted(leafs.values(), key=lambda x: x["uid"]):
    u = r["uid"]
    evs = split_events(hist_by_uid.get(u, ""))
    if not evs: continue
    cats, seen = [], set()
    for e in evs:
        if not e["note"]: continue
        hits = PARTY_RE.findall(e["note"])
        solo = STANDALONE_RE.match(e["note"])
        if hits:
            for party, cat in hits:
                cc = canon_cat(cat)
                if not cc: continue
                pty = party.upper() if party.upper() == "KP" else party.title()
                # the reason is the whole "<party>: <category>" string, exactly as it
                # reads in VisiLean's Custom Reasons list - one consolidated label
                full = pty + ": " + cc
                if full in seen: continue
                seen.add(full)
                cats.append({"party": pty, "cat": full, "kind": e["kind"],
                             "label": e["label"], "text": e["note"][:300]})
        elif solo:
            full = solo.group(1).title()
            if full not in seen:
                seen.add(full)
                cats.append({"party": "", "cat": full, "kind": e["kind"],
                             "label": e["label"], "text": e["note"][:300]})
        elif e["kind"] in VARIANCE_KINDS:
            if "Uncategorised" not in seen:
                seen.add("Uncategorised")
                cats.append({"party": "", "cat": "Uncategorised", "kind": e["kind"],
                             "label": e["label"], "text": e["note"][:300]})
    var = [e for e in evs if e["kind"] in VARIANCE_KINDS]
    if not cats and not var: continue          # nothing variance-related to report
    if not cats:
        # A real variance the team has not explained yet. Worth its own slice - the
        # unexplained share is the actionable part of the chart.
        e0 = var[0]
        cats = [{"party": "", "cat": "No reason recorded", "kind": e0["kind"],
                 "label": e0["label"], "text": ""}]
    for c in cats: cat_tally[c["cat"]] += 1
    wbs = " > ".join([x for x in r["L"][:5] if x])
    reasons.append({
        "uid": u, "name": r["name"][:110], "dept": dept_of(r),
        "type": r["atype"], "pkg": str(r["pkgcf"] or "")[:70],
        "wbs": wbs[:170], "area": r["loc"],
        "owner": (r["assignee"] or "")[:40], "ownship": (r["owner"] or "")[:60],
        "vls": r["vls"], "pct": round(r["pct"]),
        "bES": int(r["bES"]), "bEF": int(r["bEF"]),
        "fES": int(round(fES[u])), "fEF": int(round(fEF[u])),
        "aES": (wd_s(r["aS"]) if r["aS"] else None),
        "aEF": (wd_f(r["aF"]) if r["aF"] else None),
        "sSlip": (wd_s(r["aS"]) if r["aS"] else int(round(fES[u]))) - int(r["bES"]),
        "fSlip": (wd_f(r["aF"]) if r["aF"] else int(round(fEF[u]))) - int(r["bEF"]),
        "tf": int(round(TF.get(u, 0))),
        "crit": str(r.get("crit") or "").strip().lower().startswith("y"),
        "cats": cats,
        "events": [{"label": e["label"], "kind": e["kind"], "by": e["by"], "text": e["note"][:300]}
                   for e in evs if e["kind"] in VARIANCE_KINDS or e["note"]][:8],
        "desc": strip_html(r["desc"])[:400],
    })
print("variance reasons:", len(reasons), "activities | categories:", dict(cat_tally))

DATA = {"meta": meta, "months": months, "reasons": reasons, "depts": [{"key": k, "name": n} for k, n in DEPTS],
        "milestones": ms, "constraints": cons, "supplyDeliv": SUPPLY_DELIV,
        "cols": ["dept", "type", "area", "pkg", "sec", "stage", "name", "bES", "bEF", "fES", "fEF",
                 "pct", "dur", "qty", "uom", "tf", "state", "owner", "sub", "cost", "seq", "vls",
                 "ownship", "nd", "dly", "item", "wt"],
        "leaves": rows}
assert DATA["cols"][WT_I] == "wt", f"WT_I points at {DATA['cols'][WT_I]!r}, not 'wt'"
out = os.path.join(SCR, "ntpc_dashboard_data_v2.json")
json.dump(DATA, open(out, "w", encoding="utf-8"), ensure_ascii=False, separators=(",", ":"))
print(f"meta: plan={meta['plan']}% act={meta['act']}% finish {meta['forecastFinish']} (+{meta['delayDays']}d) crit={n_crit}")
print("json ->", out)
