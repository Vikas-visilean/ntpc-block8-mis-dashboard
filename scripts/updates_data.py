# -*- coding: utf-8 -*-
"""Who is updating VisiLean, across every project KP runs - data for the Updates report.

    python scripts/updates_data.py            all configured projects
    python scripts/updates_data.py ntpc adani just those

One report, five projects, a project filter on the page. Each project is fetched with its
own token (VisiLean issues one per project and it serves every feed - see vl_token.py) and
parsed by updates_trail.py, the same parsing the NTPC adoption tracker has used since
07-Sep. Every event carries the project it came from, so the page can slice by it.

A project whose token is missing is skipped with a notice rather than failing the run: the
report is still worth publishing for the projects that are configured, and a missing secret
is a setup gap nobody fixes by retrying. A token that exists and is REJECTED does fail the
run, because that is a mistake somebody can fix right now.

Emits scripts/updates_data.json.
"""
import io
import json
import os
import sys
from datetime import datetime, timezone, timedelta

try:
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
except Exception:
    pass

SCR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, SCR)
from vl_token import TokenPool, TokenRejected, fetch_json, missing_message, candidates  # noqa: E402
from updates_trail import build, COLS                                                   # noqa: E402

BASE = "https://app.visilean.net/pb/PowerBiAPI/resource/powerBi/getData/visilean"
IST = timezone(timedelta(hours=5, minutes=30))

# the projects this report covers, in the order KP reads them
PROJECT_KEYS = ["ntpc", "sjvn", "adani", "adanis7", "floating", "talaja", "inox"]

# Why file uploads are missing, checked 28-Sep-2026.
#
# VisiLean's Property Panel shows them ("File 'x.pdf' added to task 'y' by BHAVDIPSINH
# PARMAR") but this API cannot reach them. The PowerBI endpoint serves exactly two types,
# task and resource - every other type= is HTTP 500 - and none of the 14 plausible
# Include* flags for files changes the 7,636 rows it returns by one character.
#
# Those events live on the app's own API, which the web client calls per activity:
#     GET app.visilean.net/sa/VisileanAPI/activity/{activityGuid}/activityHistoryAndComments
#         ?pageIndex=N&pageSize=20&projectGuid={projectGuid}
# with objectEventType ACTIVITY_FILE_ADDED / ACTIVITY_FILE_UPLOADED. It authenticates with
# a logged-in browser session (cookie + X-CSRF-TOKEN); a PowerBI token is bounced to
# /usernameEntry, so a build job cannot call it. It is also per activity at 20 rows a page,
# which across these projects is ~30,000 requests a refresh, and there is no project-wide
# history feed to use instead.
#
# So this needs VisiLean to emit the ACTIVITY_FILE_* events on the PowerBI task feed, the
# same way it already emits status, reschedule and note sentences. The parser in
# updates_trail.py already reads the upload sentence, so the day they appear they count.

# feed -> the flags that select it; both are type=task on the one project token.
# One history request with every Include* flag returns the whole trail - status,
# reschedules, creation, workforce assignment, quantities, constraint notes and the rest
# ("Other": assignments, owner changes, notes) - so it replaces the earlier hist + notes
# pair. The plain task feed stays for the roster and the activity count.
HIST_FLAGS = ("&IncludeStatusChange=true&IncludeReschedule=true&IncludeTaskCreation=true"
              "&IncludeWorkforceAssignment=true&IncludeQuantities=true"
              "&IncludeConstraintNotes=true&IncludeOther=true")
FEEDS = {"task": "", "hist": HIST_FLAGS}

# Accounts left out of the picture entirely.
#
# EXCLUDE_ALL applies to every project: Shreyanshi Jaiswal and Vikas Patel are VisiLean's
# own people rather than KP site teams. They administer the schedules - importing MPP
# files, reassigning owners and dates - which on some projects is most of the trail, and
# counting it as adoption drowns out the teams actually using VisiLean. KP asked for both
# out everywhere on 28-Sep; before that it was NTPC alone.
EXCLUDE_ALL = {"shreyanshi jaiswal", "vikas patel"}
# and these are one project's own call: Vikram Singh is VisiLean's too (18-Sep), monika sen
# owns no task and VisiLean records no department for her (09-Sep).
EXCLUDE = {
    "ntpc": {"monika sen", "vikram singh"},
}


def excluded_for(key):
    return EXCLUDE_ALL | EXCLUDE.get(key, set())
# A last resort, for somebody who owns no task on ANY project and so is unknown to every
# task feed. Taken from Settings -> Users in VisiLean (28-Sep-2026), which the PowerBI API
# does not expose - type=resource comes back empty and the rest 500 - so it is kept by
# hand. Names in lower case. Anything the task feeds know is used ahead of guesswork, so
# an entry is only needed when the pooled lookup below still comes up empty.
USER_ORG = {
    "kevin prajapati": "Procurement - KPI",
}


def load_project(key):
    """(projectId, display name, short name) from the dashboard's own config."""
    path = os.path.join(SCR, "projects", key + ".json")
    cfg = json.load(open(path, encoding="utf-8"))
    name = cfg.get("name") or key
    short = name.split("·")[0].strip() if "·" in name else name
    return cfg["projectId"], name, short, cfg.get("client", "")


# Every project has one token and it serves both feeds. A rejected VL_TOKEN_<KEY> falls
# back to the project's VL_TOKENS_JSON entry inside the pool, as for the dashboards.
_POOLS = {}


def pool_for(key):
    if key not in _POOLS:
        _POOLS[key] = TokenPool(key, "Updates report")
    return _POOLS[key]


def dedupe_tasks(rows):
    """One row per activity.

    VisiLean's task feed can repeat an activity once per history event - NTPC returned
    7,636 rows for 6,840 activities, and ABREL Talaja's former pinned token 1,561 rows for
    897. Counting rows would inflate both the per-user task counts and the project's
    activity total, so collapse them here; a feed that is already one row per activity
    passes through unchanged.
    """
    seen, out = set(), []
    for r in rows:
        tid = str(r.get("taskId") or "")
        if tid and tid in seen:
            continue
        if tid:
            seen.add(tid)
        out.append(r)
    return out


def fetch_project(key, project_id):
    return {kind: fetch_json(
        pool_for(key),
        lambda t, f=kind: "%s?accessToken=%s&projectId=%s&type=task%s" % (BASE, t, project_id, FEEDS[f]),
        attempts=3, label="%s/%s" % (key, kind), agent="VisiLean-Updates", timeout=300)
        for kind in FEEDS}


wanted = [k for k in sys.argv[1:] if not k.startswith("-")] or PROJECT_KEYS
events, projects, skipped, fetched = [], [], [], []

for key in wanted:
    project_id, name, short, client = load_project(key)
    if not candidates(key):
        print("::notice title=Updates report skipped %s::%s" % (name, missing_message(key)))
        skipped.append({"key": key, "name": name, "why": "no token"})
        continue
    print("fetching %s ..." % name)
    try:
        feeds = fetch_project(key, project_id)
    except TokenRejected as e:
        # a wrong credential is not an outage: fail so the run goes red
        print("::error title=Updates report: every %s token rejected::%s" % (name, e))
        sys.exit(1)
    except Exception as e:                                        # noqa: BLE001
        print("SKIP %s this cycle - VisiLean unreachable after retries: %s" % (name, e))
        skipped.append({"key": key, "name": name, "why": "VisiLean unreachable"})
        continue
    feeds["task"] = dedupe_tasks(feeds["task"])
    fetched.append((key, name, short, client, feeds))

# A person's organisation is recorded on the tasks they own, so somebody who owns nothing
# on one project is usually known from another - Fenil Rana owns no Adani task but is
# Project - KPI on NTPC. Pool every project's task feed first and each project can then
# ask who somebody is; its own feed still answers first, this only fills the gaps.
_org = {}
for _k, _n, _s, _c, _f in fetched:
    for r in _f["task"]:
        who = " ".join(str(r.get("owner") or "").split()).lower()
        org = " ".join(str(r.get("organisation") or "").split())
        if who and org:
            _org.setdefault(who, {})
            _org[who][org] = _org[who].get(org, 0) + 1
ORG_FROM_TASKS = {w: max(o.items(), key=lambda kv: kv[1])[0] for w, o in _org.items()}
print("organisations known from the task feeds: %d people" % len(ORG_FROM_TASKS))
KNOWN_ORG = dict(ORG_FROM_TASKS)
KNOWN_ORG.update(USER_ORG)              # a checked answer beats a pooled one

for key, name, short, client, feeds in fetched:
    rows, facts = build(key, feeds, exclude=excluded_for(key), manual_depts=KNOWN_ORG)
    events.extend(rows)
    projects.append({
        "key": key, "name": name, "short": short, "client": client,
        "events": len(rows), "actors": len(facts["actors"]),
        "tasks": len({r[3] for r in rows}), "tasksInProject": facts["tasksInProject"],
        "rosterSize": facts["rosterSize"], "deptByUser": facts["deptByUser"],
        "deptManual": facts["deptManual"], "assignees": facts["assignees"],
        "excluded": sorted(excluded_for(key)),
        "firstEvent": facts["firstEvent"], "lastEvent": facts["lastEvent"],
        "locFilled": facts["locFilled"],
    })
    print("  %s: %d events, %d users, %d of %d activities touched, %s -> %s"
          % (short, len(rows), len(facts["actors"]), len({r[3] for r in rows}),
             facts["tasksInProject"], facts["firstEvent"], facts["lastEvent"]))

if not projects:
    print("::error title=Updates report has no projects::no project could be fetched")
    sys.exit(1)

events.sort(key=lambda e: (e[0] or "", e[15]))
uploads = sum(1 for e in events if e[COLS.index("action")] == "upload")
now = datetime.now(IST)
firsts = [p["firstEvent"] for p in projects if p["firstEvent"]]
lasts = [p["lastEvent"] for p in projects if p["lastEvent"]]
meta = {
    "title": "User Updates Report",
    "client": projects[0]["client"] if len(projects) == 1 else "KP Group",
    "generatedAt": now.strftime("%d-%b-%Y %H:%M") + " IST",
    "generatedAtEpoch": int(now.timestamp()),
    "projects": projects,
    "skipped": skipped,
    "events": len(events),
    "actors": len({e[1] for e in events}),
    "tasks": len({(e[15], e[3]) for e in events}),
    "firstEvent": min(firsts) if firsts else "",
    "lastEvent": max(lasts) if lasts else "",
    "source": ("VisiLean PowerBI API · type=task with IncludeStatusChange / IncludeReschedule / "
               "IncludeTaskCreation / IncludeQuantities / IncludeConstraintNotes / IncludeOther"),
    "noAttachments": uploads == 0,
}
out = {"meta": meta, "cols": COLS, "events": events}
dst = os.path.join(SCR, "updates_data.json")
with open(dst, "w", encoding="utf-8") as fh:
    json.dump(out, fh, ensure_ascii=False, separators=(",", ":"))
print("wrote %s | %d projects, %d events, %d users, window %s -> %s"
      % (dst, len(projects), len(events), meta["actors"], meta["firstEvent"], meta["lastEvent"]))
print("file uploads in the feed: %d%s"
      % (uploads, "" if uploads else "  (VisiLean does not send them - see the note above)"))
if skipped:
    print("skipped: " + ", ".join("%s (%s)" % (s["name"], s["why"]) for s in skipped))
