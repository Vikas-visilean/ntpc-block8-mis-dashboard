# Repo rules

## Logic changelog

Every change to dashboard logic, calculations, counts, classification, or any rule or
fact behind them (e.g. "KP rule 26-Aug") is listed in [CHANGELOG.md](CHANGELOG.md).
`.github/workflows/changelog.yml` writes the entry when the commit reaches `master`,
using the commit's time (IST), its GitHub user and its message. So:

- Never edit `CHANGELOG.md` by hand; the workflow owns it.
- When a commit changes logic in `scripts/*.py`, a `scripts/*_template*.html` page or
  `scripts/projects/*.json`, its message IS the changelog entry:
  - subject: the rule in one line, with its source if it has one ("... (KP 07-Oct)")
  - body: what changed (before → after), why, and the check behind it
    (e.g. "VisiLean export 06-Oct: 571 = 571"), and which projects it applies to
- A logic change and an unrelated change go in separate commits, so each entry says
  one thing.
