# -*- coding: utf-8 -*-
"""One project's VisiLean audit trail, parsed into update events.

Lifted out of adoption_data.py so the Updates report can read five projects with the
same parsing the NTPC adoption tracker has been using since 07-Sep. Nothing here talks
to the network: give it the three feeds and it gives you the events and the project's
own facts (who updates, which department they belong to, who has work assigned).

Where the events come from
--------------------------
VisiLean returns the audit trail on the task endpoint as one row per (task, event), with
the event written as an English sentence in `activityHistory` and its timestamp in
`historyDateTime`:

    Task 'KP to EPC PO Placement' set to 'Not Ready' as a result of action by Fenil Rana
    Task 'Support Installation at IDT side' imported from file '....mpp' by Shreyanshi Jaiswal.

So the acting user has to be parsed out of the sentence. To keep that honest a roster is
built first - the project's own assignees, plus anyone the trail credits three times, plus
anyone named in a sentence VisiLean writes itself - and an event is only ever attributed to
a name on that roster. A loose "by (.+)" capture would invent users out of note text.
"""
import re
from datetime import datetime

# Only person-shaped names, so note text can never masquerade as a user.
PERSON = re.compile(r"^[A-Za-z][A-Za-z'\-]*(?:\s+[A-Za-z][A-Za-z'\-]*){1,3}$")
NOT_PERSON = re.compile(r"^(target date|for action|the designated|action by)", re.I)
BY = re.compile(r"\bby\s+([A-Za-z][^\.,:;\r\n]{2,40})")
# Sentences VisiLean writes itself: a name in one of these positions is a real user on
# their first action, so a new joiner is credited rather than read as "Unattributed".
STRICT_BY = re.compile(
    r"(?:was forced ready to start by|as a result of action by|bulk completed by"
    r"|imported from file[^.]{0,160}?by|created by|completed on time by|started on time by"
    r"|rescheduled by|assigned to [^.]{1,80}?by"
    r"|added to task[^.]{0,160}?by)\s+([A-Za-z][^\.,:;\r\n]{2,40})", re.I)
# a sentence, not a stray field value ("Construction" arrives in IncludeOther rows)
SENTENCE = re.compile(r"\bby\b|Task '|Note|note|\s:\s")

ACTIONS = (
    ("import", re.compile(r"imported from file")),
    # "File 'S1BY-...-0002_R1.pdf' added to task 'Equipment Layout Of IDT Station Type Bb
    # (33Kv Switchgear)' by BHAVDIPSINH PARMAR" - VisiLean's ACTIVITY_FILE_ADDED /
    # ACTIVITY_FILE_UPLOADED. The PowerBI feed does not carry these (see the note in
    # updates_data.py), so this matches nothing today and starts crediting the people who
    # only ever upload drawings on the day it does.
    ("upload", re.compile(r"\bFiles?\s+'[^']*'\s+(?:added|uploaded)"
                          r"|(?:added|uploaded) to task '")),
    ("bulk", re.compile(r"bulk completed")),
    ("forced", re.compile(r"was forced ready")),
    ("assign", re.compile(r"assigned to")),
    ("ownerchg", re.compile(r"Owner\.? changed|changed for Task")),
    ("fieldchg", re.compile(r"Trade set to|Task type is now set|Make Ready Date changed")),
    ("pct", re.compile(r"New completion percentage")),
    ("status", re.compile(r"set to '")),
    ("resched", re.compile(r"rescheduled|date changed")),
    ("actionitem", re.compile(r"To be acted upon by")),
    ("constraint", re.compile(r"constraint")),
    ("note", re.compile(r"Note added|Note:|note:|Updated content|\s:\s")),
)

COLS = ["ts", "actor", "action", "tid", "task", "dept", "atype", "loc", "pkg",
        "owner", "ownship", "detail", "status", "trade", "crit", "proj"]


def _clean(name):
    n = " ".join(str(name or "").split())
    return re.sub(r"\s+for action$", "", n).strip()


def build(key, feeds, exclude=(), manual_depts=None):
    """feeds: {"task": [...], "hist": [...], "notes": [...]} -> (events, facts)."""
    exclude = {e.lower() for e in exclude}
    task, hist, notes = feeds["task"], feeds["hist"], feeds["notes"]

    # ---------- roster ----------
    owners = {}
    for r in task:
        n = " ".join(str(r.get("owner") or "").split())
        if n:
            owners[n.lower()] = n

    cand, strict = {}, set()
    for feed in (hist, notes):
        for r in feed:
            txt = str(r.get("activityHistory") or "")
            if not txt:
                continue
            for m in BY.finditer(txt):
                n = _clean(m.group(1))
                if not PERSON.match(n) or NOT_PERSON.match(n):
                    continue
                cand.setdefault(n.lower(), [n, 0])
                cand[n.lower()][1] += 1
            for m in STRICT_BY.finditer(txt):
                n = _clean(m.group(1))
                if PERSON.match(n) and not NOT_PERSON.match(n):
                    strict.add(n.lower())

    roster = list(owners.values())
    for k, (n, c) in cand.items():
        if k not in owners and (c >= 3 or k in strict):
            roster.append(n)
    roster = sorted(set(roster))          # parsing vocabulary: keeps excluded names so
    if not roster:                        # their events are recognised, then dropped
        return [], {"roster": [], "actors": [], "tasksInProject": len(task),
                    "deptByUser": {}, "assignees": [], "deptManual": {},
                    "firstEvent": "", "lastEvent": "", "locFilled": 0}

    alt = "(" + "|".join(re.escape(n) for n in sorted(roster, key=len, reverse=True)) + ")"
    # VisiLean spells one person differently depending on which screen wrote the event
    # - "BHAVDIPSINH PARMAR" in an upload sentence, "Bhavdipsinh Parmar" on the task he
    # owns - so match regardless of case and then spell them the roster's way, or the
    # same user lands in the report twice.
    lead = re.compile(r"^" + alt + r"\s*[:\.]", re.I)
    result_of = re.compile(r"as a result of action by\s+" + alt, re.I)
    by_roster = re.compile(r"\bby\s+" + alt, re.I)
    any_roster = re.compile(alt, re.I)
    roster_spelling = {n.lower(): n for n in roster}

    def actor(sentence):
        s = " ".join(sentence.split())
        m = lead.match(s)                 # "NUR ISLAM : ...", "Sabir Ahmed. Note added: ..."
        if m:
            return m.group(1)
        m = result_of.search(s)           # explicit attribution
        if m:
            return m.group(1)
        hits = by_roster.findall(s)       # "assigned to X by Y" -> Y acts
        if hits:
            return hits[-1]
        m = any_roster.search(s)
        return m.group(1) if m else "Unattributed"

    def action(sentence):
        for name, rx in ACTIONS:
            if rx.search(sentence):
                return name
        return "other"

    canon = {}

    def canonical(name):
        k = " ".join(name.split())
        return roster_spelling.get(k.lower()) or canon.setdefault(k.lower(), k)

    # ---------- department of each user ----------
    # On the plain type=task feed VisiLean carries the user in `owner` and that user's
    # department in `organisation`, so this is recorded rather than inferred.
    by_user = {}
    tasks_owned = {}
    for r in task:
        who = " ".join(str(r.get("owner") or "").split())
        if not who:
            continue
        tasks_owned[who] = tasks_owned.get(who, 0) + 1
        org = " ".join(str(r.get("organisation") or "").split())
        if org:
            by_user.setdefault(who, {})
            by_user[who][org] = by_user[who].get(org, 0) + 1
    dept_by_user = {w: max(o.items(), key=lambda kv: kv[1])[0] for w, o in by_user.items()}
    manual = {k: v for k, v in (manual_depts or {}).items()
              if not any(k.lower() == w.lower() for w in dept_by_user)}
    assignees = [{"name": w, "tasks": n, "dept": dept_by_user.get(w, "")}
                 for w, n in sorted(tasks_owned.items(), key=lambda kv: -kv[1])
                 if w.lower() not in exclude]

    # ---------- events ----------
    seen, events = set(), []
    lo = hi = None
    for feed in (hist, notes):
        for r in feed:
            txt = str(r.get("activityHistory") or "").strip()
            if len(txt) < 8 or not SENTENCE.search(txt):
                continue
            sig = (str(r.get("taskId")), str(r.get("historyDateTime")), txt)
            if sig in seen:
                continue
            seen.add(sig)

            ts, d = "", None
            raw = str(r.get("historyDateTime") or "")
            if raw:
                try:
                    d = datetime.strptime(raw, "%d/%m/%Y %H:%M:%S")
                    ts = d.strftime("%Y-%m-%dT%H:%M:%S")
                except ValueError:
                    ts, d = "", None

            who = canonical(actor(txt))
            if who.lower() in exclude:
                continue
            # the window belongs to the events the report keeps: counting an excluded
            # account's imports would have the header claim months the page cannot show
            if d is not None:
                lo = d if lo is None or d < lo else lo
                hi = d if hi is None or d > hi else hi
            cf = r.get("customField") or {}
            events.append([
                ts,
                who,
                action(txt),
                str(r.get("taskId") or ""),
                str(r.get("taskName") or ""),
                str(cf.get("Department") or "").strip(),
                str(cf.get("Activity Type") or r.get("taskType") or "").strip(),
                str(r.get("location") or r.get("zoneName") or "").strip(),
                str(cf.get("Package") or "").strip(),
                str(cf.get("Owner.") or r.get("owner") or "").strip(),
                str(r.get("organisation") or "").strip(),
                " ".join(txt.split()),
                str(r.get("status") or "").strip(),
                str(r.get("trade") or "").strip(),
                1 if str(cf.get("Critical Activity") or "").strip().lower() == "yes" else 0,
                key,
            ])

    facts = {
        "roster": roster,
        "actors": sorted({e[1] for e in events}),
        "tasksInProject": len(task),
        "rosterSize": len([n for n in roster if n.lower() not in exclude]),
        "deptByUser": dept_by_user,
        "deptManual": manual,
        "assignees": assignees,
        "firstEvent": lo.strftime("%Y-%m-%d") if lo else "",
        "lastEvent": hi.strftime("%Y-%m-%d") if hi else "",
        "locFilled": sum(1 for e in events if e[7]),
    }
    return events, facts
