# Request to VisiLean: file events on the PowerBI task feed

*Raised 29-Sep-2026, from building the User Updates Report.*

## The ask

Issue PowerBI API tokens for the five projects below whose `type=task` feed includes
**file and attachment events** in `activityHistory`, alongside the status, reschedule,
import and note sentences it already carries.

| project | projectId |
| --- | --- |
| NTPC Bikaner Block 8 · 200 MW | `7A2842F6-7E5F-DB7C-3E7F-0EE7EF60698F` |
| Adani Green Energy S6a · 234 MW | `8E1DC8F3-B98D-7466-372B-A885DE53F1BB` |
| Adani Green Energy S7 · 300 MW | `11127A8C-E796-06BF-8B4A-82CF074A6C4E` |
| ABREL Talaja 83.7 MW | `2F7F0BA6-2345-C92E-81E8-C034D1E9848D` |
| Floating Solar · Kadana Dam · 110 MW | `A52816EA-1EA7-A978-EEEA-29A0D775CD7F` |

The event types wanted are the ones VisiLean's own web client names:

    ACTIVITY_FILE_ADDED
    ACTIVITY_FILE_UPLOADED
    ACTIVITY_MULTIPLE_FILE_UPLOADED

No new endpoint, field or format is needed. One more sentence kind in `activityHistory`,
in the shape the Property Panel already writes, is enough:

    File 'S1BY-KPIG-IDT-STR-DE-L-0002_R1_EQUIPMENT LAYOUT.pdf' added to task
    'Equipment Layout Of IDT Station Type Bb (33Kv Switchgear)' by BHAVDIPSINH PARMAR

## Why it matters

The User Updates Report measures who is actually using VisiLean on each project. It
counts every kind of update the API exposes — status changes, reschedules, quantities,
notes, imports — but it cannot see a document being uploaded.

On projects where the site team's main contribution is uploading drawings, that makes
the report wrong in a way that looks like a finding rather than a gap. Adani S6a reads
**2 updates against 2,558 activities** and Adani S7 **2 against 3,062**. Those numbers
are accurate for what the API returns and misleading about the teams.

The page carries a "file uploads are not counted" note so nobody reads those figures as
the whole story. The note is derived from the data and removes itself automatically the
first time an upload event arrives.

## The events exist, but not where a report can reach them

They are in the app's own API, which the web client calls once per activity:

    GET app.visilean.net/sa/VisileanAPI/activity/{activityGuid}/activityHistoryAndComments
        ?pageIndex=N&pageSize=20&projectGuid={projectGuid}

That is not usable from a scheduled build:

1. **It authenticates with a logged-in browser session** — cookie plus `X-CSRF-TOKEN`.
   A PowerBI token presented as a query parameter, a Bearer header or an `X-Auth-Token`
   header is bounced to `/usernameEntry` with HTTP 406 in all three cases.
2. **It is per activity, 20 rows a page.** NTPC alone has 6,840 activities; across these
   five projects a single refresh would be roughly 30,000 requests, twice a day.
3. **There is no project-wide history feed.** Only per-activity and per-constraint
   endpoints exist in the web client.

## What the PowerBI API returns today

Checked 29-Sep-2026 against three tokens on two projects. The API serves nine types —
its own error message lists them — and none carries a file:

| type | NTPC | Talaja (token 1) | Talaja (token 2) | any file data |
| --- | --- | --- | --- | --- |
| `task` | 7,639 | 1,561 | 1,287 | no |
| `constraintLog` | 7 | 20 | 20 | no |
| `workForce` | 0 | 59 | 59 | no |
| `attendance` | 0 | 0 | 0 | no |
| `criticalTask` | 0 | 0 | 0 | no |
| `resource` | 0 | 0 | 0 | no |
| `dailyQuantity` | 0 | 0 | 0 | no |
| `committedTask` | not JSON | not JSON | not JSON | no |
| `checklist` | HTTP 400 | HTTP 400 | HTTP 400 | — |

No field on any row holds a filename. The only filenames anywhere in the payload belong
to MPP schedule imports, which the report already counts.

Passing flags in the URL does not help, because **a token's payload is fixed when the
token is issued** — which is why ABREL Talaja's two tokens return different halves of
the same trail whatever flags the URL asks for. That is why this is a request for new
tokens rather than a change we can make from our side.

*Update 30-Sep-2026:* VisiLean has since issued Talaja one standard token, like every
other project, so it now runs on `VL_TOKEN_TALAJA` alone. The table above records the
two pinned tokens it replaced.

## Nothing is needed from us afterwards

`scripts/updates_trail.py` already classifies the upload sentence as its own `upload`
action and credits the uploader on their first one, even if they have never touched the
project otherwise. The moment a feed carries these events they are counted, the page's
"not counted" note disappears, and no code changes.
