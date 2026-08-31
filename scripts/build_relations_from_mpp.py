# -*- coding: utf-8 -*-
"""Rebuild scripts/vl_relations.json - the activity logic network - from an MSP file.

VisiLean's PowerBI task endpoint always returns `prerequisites` empty, so the only
place the schedule logic exists is the MSP file KP maintains. This script reads ONLY
the predecessor links out of it. Nothing else from the .mpp reaches the dashboard:
every date, percentage, status, owner, weightage and reason stays VisiLean's.

MSP **Unique ID** is VisiLean **externalId** - verified 1:1 against the 27-Aug-2026
file: 7,101 tasks on both sides, every id present on both, every task name identical.

Output: a list of [predecessorUid, successorUid, type, lagDays], the shape
ntpc_dash_data_v2.py already consumes.

    python scripts/build_relations_from_mpp.py "<path to .mpp>"
"""
import sys, os, json
from collections import defaultdict

SCR = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(SCR, "vl_relations.json")

if len(sys.argv) < 2:
    raise SystemExit("usage: build_relations_from_mpp.py <schedule.mpp>")
MPP = sys.argv[1]

import mpxj, jpype                                  # noqa: E402  (adds the jars first)
if not jpype.isJVMStarted():
    jpype.startJVM()
try:
    from net.sf.mpxj.reader import UniversalProjectReader
except ImportError:                                  # mpxj >= 14 renamed the package
    from org.mpxj.reader import UniversalProjectReader

proj = UniversalProjectReader().read(MPP)
tasks = list(proj.getTasks())

summary, name_of, rels = set(), {}, []
for t in tasks:
    uid = t.getUniqueID()
    if uid is None:
        continue
    uid = int(uid)
    name_of[uid] = str(t.getName() or "")
    if t.getSummary():
        summary.add(uid)
    for r in (t.getPredecessors() or []):
        src = r.getPredecessorTask()
        if src is None or src.getUniqueID() is None:
            continue
        lag = r.getLag()
        try:
            lagd = float(lag.getDuration()) if lag is not None else 0.0
        except Exception:
            lagd = 0.0
        rels.append([int(src.getUniqueID()), uid, str(r.getType()), lagd])

print("tasks: %d (%d summary) | links: %d" % (len(name_of), len(summary), len(rels)))

# A handful of links hang off a summary task ("Block-1 17.6 MW" in the 27-Aug file).
# The adapter only keeps links whose two ends are both leaves, so those would be
# dropped - and for 48 activities that link is their ONLY predecessor. Expand a
# summary endpoint into the leaves beneath it instead, which is what the link means.
child = defaultdict(list)
for t in tasks:
    uid, par = t.getUniqueID(), t.getParentTask()
    if uid is not None and par is not None and par.getUniqueID() is not None:
        child[int(par.getUniqueID())].append(int(uid))

_leafmemo = {}
def leaves(u):
    if u in _leafmemo:
        return _leafmemo[u]
    _leafmemo[u] = [u]                       # guards against a cycle mid-walk
    out = [u] if u not in child else [x for k in child[u] for x in leaves(k)]
    _leafmemo[u] = out
    return out

expanded, seen = [], set()
for pu, su, code, lag in rels:
    for a in (leaves(pu) if pu in summary else [pu]):
        for b in (leaves(su) if su in summary else [su]):
            if a == b:
                continue
            k = (a, b, code, lag)
            if k in seen:
                continue
            seen.add(k)
            expanded.append([a, b, code, lag])

print("links after expanding summary endpoints: %d" % len(expanded))
json.dump(expanded, open(OUT, "w"), separators=(",", ":"))
print("-> %s" % OUT)
