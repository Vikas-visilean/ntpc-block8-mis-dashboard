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
except Exception as e:
    # transient VisiLean outage: skip this cycle cleanly; the next run recovers
    print(f"SKIP this cycle - VisiLean API unreachable after retries: {e}")
    sys.exit(0)
print("tasks:", len(TASKS), "| constraints:", len(CONS))
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
for t in TASKS:
    try: uid = int(t.get("externalId"))
    except Exception: continue
    cf = t.get("customField") or {}
    L = [cf.get(f"Level {i}", "") or "" for i in range(1, 8)]
    bs, bf = pdate(t.get("baselineStartDate")), pdate(t.get("baselineEndDate"))
    if bs is None or bf is None:
        bs2, bf2 = pdate(t.get("plannedStartDate")), pdate(t.get("plannedEndDate"))
        bs, bf = bs or bs2, bf or bf2
    if bs is None or bf is None: continue
    r = {"uid": uid, "name": t.get("taskName") or "", "parent": bool(t.get("parent")),
         "L": L, "atype": cf.get("Activity Type", ""), "pkgcf": cf.get("Package", ""),
         "owner": cf.get("Owner.", "") or cf.get("Owner", ""),
         "assignee": t.get("owner") or "", "loc": t.get("location") or "Off-site / Office",
         "bES": wd_s(bs), "bEF": wd_f(bf),
         "pES": (wd_s(pdate(t.get("plannedStartDate"))) if pdate(t.get("plannedStartDate")) else None),
         "pEF": (wd_f(pdate(t.get("plannedEndDate"))) if pdate(t.get("plannedEndDate")) else None),
         "aS": pdate(t.get("actualStartDate")), "aF": pdate(t.get("actualEndDate")),
         "pct": float(t.get("percentComplete") or 0),
         "vls": t.get("status") or "Not Committed",
         "qty": t.get("totalQuantity"), "uom": t.get("quantityUnits") or "",
         "cost": money(cf.get("Cost")), }
    try: r["dur"] = max(0.0, float(t.get("baselineDuration") or t.get("plannedDuration") or 0))
    except Exception: r["dur"] = max(0.0, float(r["bEF"] - r["bES"]))
    if r["dur"] == 0 and not r["parent"]:
        r["dur"] = max(0.0, float(r["bEF"] - r["bES"]))
    if (L[0] or "").startswith("Key Milestones") or re.match(r"^MS-\d", r["name"]):
        if not r["parent"]: milestones_raw.append(r)
        continue
    recs[uid] = r

leafs = {u: r for u, r in recs.items() if not r["parent"]}
print("usable leaves:", len(leafs), "| milestones:", len(milestones_raw))

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

# ---------- classification ----------
DEPTS = [("initiation", "Project Initiation"), ("engineering", "Design & Engineering"),
         ("quality", "Quality Assurance"), ("supply", "Procurement - Supply"),
         ("services", "Procurement - Services"),
         ("regulatory", "Regulatory & Statutory"), ("execution", "Execution & Construction"),
         ("tnc", "Testing & Commissioning"), ("hoto", "HOTO (Handover)")]
def dept_of(r):
    l1, l2 = norm(r["L"][0]), norm(r["L"][1])
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
rows = []
for r in sorted(leafs.values(), key=lambda x: x["uid"]):
    u = r["uid"]; dept = dept_of(r); ln = norm(r["name"]); L = r["L"]
    area = r["loc"] or "Off-site / Office"
    if dept in ("supply", "services"):
        pkg = r["pkgcf"] or L[2] or L[1]; sec = "Supply" if dept == "supply" else "EPCC & I&C Services"
    elif dept == "engineering":
        pkg = r["pkgcf"] or (L[3] or L[2] or L[1]); sec = L[2] or L[1]
    elif dept in ("execution", "tnc"):
        cand = [x for x in L[2:6] if x and not BLOCK_RE.match(x) and norm(x) != "construction"]
        pkg = cand[-1] if cand else (L[3] or L[2] or L[1]); sec = L[2] or L[1]
    else:
        pkg = L[1] or L[0]; sec = L[1] or L[0]
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
    if r["pct"] >= 100 or vs == "Complete": state = "done"
    elif r["pct"] > 0 or vs in ("Started", "Warning", "Stopped"): state = "inprog"
    elif r["bES"] < STATUS_WD: state = "late"
    else: state = "future"
    rows.append([dept, r["atype"], area, str(pkg)[:70], str(sec)[:60], stage,
                 r["name"][:70], int(r["bES"]), int(r["bEF"]), int(round(fES[u])), int(round(fEF[u])),
                 round(r["pct"]), round(r["dur"], 1), r["qty"], r["uom"][:14],
                 int(round(TF.get(u, 0))), state,
                 (r["assignee"] or r["owner"] or "")[:24], sub, round(r["cost"]), len(rows), vs])
n_crit = sum(1 for x in rows if x[15] <= 5 and x[16] != "done")

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

def w_of(x): return x[19] if x[19] and x[19] > 0 else 0.0
WSUM = sum(w_of(x) for x in rows)
W = (lambda x: w_of(x)) if WSUM > 0 else (lambda x: x[12])
WT = sum(W(x) for x in rows) or 1.0
plan_pct = sum(min(1.0, max(0.0, (STATUS_WD - x[7]) / max(0.5, x[12]))) * W(x) for x in rows) / WT
act_pct = sum(x[11] / 100.0 * W(x) for x in rows) / WT
bfin = max(x[8] for x in rows); ffin = max(x[10] for x in rows)
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
        "done": sum(1 for x in rows if x[16] == "done"), "inprog": sum(1 for x in rows if x[16] == "inprog"),
        "late": sum(1 for x in rows if x[16] == "late"), "total": len(rows),
        "source": "VisiLean live API",
        "generatedAt": datetime.datetime.utcnow().strftime("%d-%b-%Y %H:%M UTC")}

cons = []
for c in CONS:
    cons.append({"id": c.get("constrainId"), "title": c.get("title") or "", "desc": (c.get("discription") or "")[:200],
                 "author": c.get("author") or "", "owner": c.get("owner") or "",
                 "cat": (c.get("category") or "").strip() or "Uncategorised",
                 "pri": c.get("priority") or "—",
                 "created": c.get("creationDate") or "", "target": c.get("targetDate") or "",
                 "committed": c.get("commitmentDate") or "", "completed": (c.get("completionDate") or "").strip(),
                 "open": not (c.get("completionDate") or "").strip()})

DATA = {"meta": meta, "months": months, "depts": [{"key": k, "name": n} for k, n in DEPTS],
        "milestones": ms, "constraints": cons,
        "cols": ["dept", "type", "area", "pkg", "sec", "stage", "name", "bES", "bEF", "fES", "fEF",
                 "pct", "dur", "qty", "uom", "tf", "state", "owner", "sub", "cost", "seq", "vls"],
        "leaves": rows}
out = os.path.join(SCR, "ntpc_dashboard_data_v2.json")
json.dump(DATA, open(out, "w", encoding="utf-8"), ensure_ascii=False, separators=(",", ":"))
print(f"meta: plan={meta['plan']}% act={meta['act']}% finish {meta['forecastFinish']} (+{meta['delayDays']}d) crit={n_crit}")
print("json ->", out)
