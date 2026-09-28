# -*- coding: utf-8 -*-
"""Assemble the User Updates report: template + every project's trail + logo -> ../updates/

Shares scripts/adoption_data.json with the fuller adoption report - same audit trail,
a simpler view of it (who updated what, when, and what kind of action), modelled on the
Power BI "User Updates Report" KP referenced. Writes index.html, meta.json and
.datahash so an unchanged trail does not produce a commit.
"""
import hashlib
import json
import os

SCR = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(SCR)

tpl = open(os.path.join(SCR, "updates_template.html"), encoding="utf-8").read()
data_txt = open(os.path.join(SCR, "updates_data.json"), encoding="utf-8").read()
logo = "data:image/png;base64," + open(os.path.join(SCR, "kp_logo.b64"), encoding="ascii").read().strip()

html = tpl.replace("__LOGO__", logo).replace("__DATA__", data_txt)
assert "accessToken" not in html, "token leak!"

outdir = os.path.join(ROOT, "updates")
os.makedirs(outdir, exist_ok=True)
open(os.path.join(outdir, "index.html"), "w", encoding="utf-8").write(html)

data = json.loads(data_txt)
open(os.path.join(outdir, "meta.json"), "w", encoding="utf-8").write(json.dumps(dict(data["meta"])))

d2 = json.loads(data_txt)
d2["meta"].pop("generatedAt", None)
d2["meta"].pop("generatedAtEpoch", None)
h = hashlib.sha256(json.dumps(d2, sort_keys=True).encode()).hexdigest()
open(os.path.join(outdir, ".datahash"), "w").write(h)
# second guard: the TEMPLATE alone. .datahash only moves when VisiLean data moves, so
# without this a template change never reaches the published page on its own - the same
# guard build_dash.py keeps for the project dashboards.
th = hashlib.sha256((tpl + "\x00" + logo).encode("utf-8")).hexdigest()
open(os.path.join(outdir, ".tplhash"), "w").write(th)

print("built updates/index.html %d bytes | %d updates | datahash %s"
      % (os.path.getsize(os.path.join(outdir, "index.html")), len(data["events"]), h[:12]))
