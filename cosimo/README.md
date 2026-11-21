# Cosimo publishing hub

Selected 18 November 2026: **BrightBean Studio**. This folder contains the small
deployment and content-handoff additions; BrightBean supplies the composer,
calendar, media library, scheduler, provider adapters, analytics and inbox.

Fork: https://github.com/Cosimo-Medici/brightbean-studio

Upstream revision: `14b92fc18549de47d42e62054215b38b4d994449`.
Postiz comparison revision: `2f24e10f2204295f66a1999679e9896db3cb2094`.

## Decision

| Requirement | BrightBean | Postiz |
|---|---|---|
| Fork, self-host, modify | AGPL-3.0 | AGPL-3.0 |
| Written posts and PNG cartoons | LinkedIn personal and company adapters | LinkedIn personal and company adapters |
| Personal LinkedIn starting access | Separate OIDC + Share path | Current adapter requires organization/Advertising scopes too |
| Native calendar and scheduling | Yes | Yes |
| Incoming social comments | Inbox, threads, assignments and reply API; permission-dependent | No comparable incoming inbox verified in inspected code |
| Personal LinkedIn analytics | Not implemented | Not implemented |
| Company LinkedIn analytics | Implemented; platform approval required | Implemented; platform approval required |
| Integration retries | Explicit request-key replay; Cosimo adds atomic creation/finalization | Durable Temporal publishing; no comparable creation request-key contract found |
| Local infrastructure | Web, worker, PostgreSQL | App, PostgreSQL, Redis and Temporal stack |
| X / LinkedIn PDF documents | Gaps in inspected providers | Broader coverage, including X and PDF |

BrightBean removes more of the initial LinkedIn content/inbox integration work
and has the simpler deployment. Postiz remains a good alternative if X or PDF
publishing becomes an immediate requirement. This was a source comparison and
a live BrightBean local evaluation, **not** a live platform benchmark of both.
Neither product makes platform approvals disappear.

### Evidence

- [BrightBean personal provider](https://github.com/brightbeanxyz/brightbean-studio/blob/14b92fc18549de47d42e62054215b38b4d994449/providers/linkedin_personal.py)
- [BrightBean inbox API](https://github.com/brightbeanxyz/brightbean-studio/blob/14b92fc18549de47d42e62054215b38b4d994449/apps/api/routers/inbox.py)
- [BrightBean post API](https://github.com/brightbeanxyz/brightbean-studio/blob/14b92fc18549de47d42e62054215b38b4d994449/apps/api/routers/posts.py)
- [Postiz personal provider](https://github.com/gitroomhq/postiz-app/blob/2f24e10f2204295f66a1999679e9896db3cb2094/libraries/nestjs-libraries/src/integrations/social/linkedin.provider.ts)
- [Postiz OAuth setup](https://docs.postiz.com/self-host/providers/linkedin)
- [LinkedIn Share permissions](https://learn.microsoft.com/en-us/linkedin/consumer/integrations/self-serve/share-on-linkedin)
- [LinkedIn approved API access](https://learn.microsoft.com/en-us/linkedin/marketing/increasing-access?view=li-lms-2026-03)

The BrightBean personal-provider error text says personal analytics do not
exist. Treat that explanation as outdated: LinkedIn documents approved member
analytics permissions. The implementation gap in this provider remains real.

## Current operating checkpoint — 20 November 2026

**Later Phase 1 reconciliation:** authenticated LinkedIn history shows Monday's
Anthropic piece (`urn:li:activity:7528153226517475329`) and Wednesday's Sequoia
piece (`urn:li:activity:7528864795358429184`) already live outside this hub.
Their existing native records are now published history, preserving source IDs,
captions and assets; zero drafts/queued posts remain. No provider call or synthetic
PublishLog was made. Exact external publication timestamps remain null, and saved
internal notes explicitly distinguish imported source copy from published copy.
Native UI readback shows **Sent 3** and **No queued posts**. This supersedes the
one-published/two-draft inventory recorded below.

Three historical unknown references now have observed published versions
(reporting efficiency, Power by the Hour and Sequoia); seven remain unresolved.
Exact historical copy/media equality and full account-export coverage are not
claimed. Receipts: `cosimo/private/history-2026-11-20/`. Existing pre-repair backup:
`cosimo/private/backups/20261120T185509Z`.

The publisher now runs in its own [Cosimo Publishing Railway project](https://railway.com/project/7c928eae-6186-412e-b796-902471261595), separate from the product. [Open the hosted hub](https://publisher-web-production-e78fb5fd.up.railway.app). Web, one worker, dedicated PostgreSQL and private media storage are deployed; state/media/key and real LinkedIn identity checks passed. The local worker is stopped and requires an explicit compose profile to restart. The hosted OAuth callback is registered and the journal destination is migrated. Daily remote backup and an isolated restore from the actual private backup bucket also passed: 95 tables, eight media objects and three encrypted values recovered. The old local backup LaunchAgent is disabled. See [hosted operation and recovery](railway-cutover.md) for exact resources and receipts.

Google sign-in is verified on the hosted hub: use **Log in with Google** as `ecp@medici.ai`. The dedicated internal Google Cloud project is `cosimo-publishing`; actual OAuth returned to the original account/calendar without creating another workspace. Public signup remains closed, the original password fallback is preserved, and Google credentials are included in hosted recovery configuration. Details and private verification receipt are in [hosted operation and recovery](railway-cutover.md).

Friday revision 4 was published once through the native worker at 11:58 a.m.
Eastern, before the subsequent lunchtime scheduling instruction:
https://www.linkedin.com/feed/update/urn:li:share:7529588949397422080/.
The earlier inventory at publication was one published post and two unscheduled
drafts; the later reconciliation above supersedes it. All three source IDs match their existing journal records; none was
recreated. Historical permalink records and ten unresolved historical publication
states remain reference evidence, never input to draft creation.

The web and worker now run the same rebuilt image. Deployed source hashes were
read back from both services. The LinkedIn image adapter now forwards the saved
post/media description as `content.media.altText`, per the [LinkedIn schema](https://learn.microsoft.com/en-us/linkedin/marketing/community-management/shares/post-api-schema).
Request construction was checked against the actual saved Friday image description;
provider acceptance awaits a subsequent approved post. Friday was not edited or
republished. The native recurring publishing task is running without recorded
failure in the observed cycles.

Real HTTP/PostgreSQL checks in `verify-publishing-operations.py` passed for native
planned-day batch scheduling, isolated rescheduling, withdrawal, new-account
12:15 defaults and winter/summer timezone calculation. Disposable records were
removed; no provider calls or new publication occurred. Current posts, slots,
media hashes and publish logs matched before and after. Private receipts live in
`cosimo/private/operations-2026-11-20/verification.json`.

A fresh snapshot including the published post, both drafts, five lunchtime slots
and eight media files restored successfully across 95 tables, with saved-key
decryption and unchanged live state. See `restore-rehearsal.md`. Local source
changes remain uncommitted. Always-on hosting is now deployed. Off-machine recovery
is verified for the 20 November hosted snapshot. Company/inbox access and actual timed platform publication remain outstanding. The older dated
sections below are historical setup evidence, superseded by this checkpoint.

## Local operation (retained recovery environment)

### Standing publishing time

Eliot's clarification of 20 November 2026: approve the whole week's batch in
one go on Monday, then schedule each approved post for its own planned day.
No repeat approval is needed on publication day. Slots must be after noon for
the lunch crowd: configured at **12:15 p.m. America/New_York**. Approval time
does not determine publication time; preserve the planned cadence rather than
moving the batch into the next available slot. The connected account has
Monday–Friday lunchtime slots; availability does not require daily posting.
Keep this workspace in America/New_York for DST handling. New-channel source
defaults in `apps/calendar/services.py` also use weekday 12:15 p.m.
Existing published posts are unchanged.

Run from the repository root:

```sh
python3 cosimo/init-local.py
docker compose -f cosimo/compose.yaml up -d --build
docker compose -f cosimo/compose.yaml ps
```

`init-local.py` runs once and refuses to overwrite existing configuration.
Secrets live in ignored `cosimo/private/` (directory 0700, files 0600), excluded
from the Docker image. PostgreSQL has no published host port. The app listens
only at http://localhost:4010. Email delivery and optional hosted Intelligence
are disabled, registration is closed, and no social credentials ship with it.

Bootstrap the local operator and workspace once (safe to repeat):

```sh
set -a
. cosimo/private/operator.env
set +a
docker compose -f cosimo/compose.yaml exec -T \
  -e DJANGO_SUPERUSER_EMAIL -e DJANGO_SUPERUSER_PASSWORD \
  web python manage.py shell < cosimo/bootstrap.py
unset DJANGO_SUPERUSER_EMAIL DJANGO_SUPERUSER_PASSWORD
```

The local operator login is stored in `cosimo/private/operator.env`. Bootstrap
does not accept terms on anyone's behalf. Use the workspace's native calendar
for edits and scheduling. Dates are displayed in America/New_York; API times
are UTC.

```sh
docker compose -f cosimo/compose.yaml logs --tail 50 web worker
docker compose -f cosimo/compose.yaml stop
docker compose -f cosimo/compose.yaml up -d
```

Keep this deployment loopback-only. An always-on remote installation needs
the upstream production HTTPS configuration, a stable hostname, backups and
the matching OAuth callbacks. Do not expose `cosimo_local` settings publicly.
Mac scheduling depends on Docker running and the Mac remaining awake.

## Connect LinkedIn

The Cosimo Publishing LinkedIn app (266747924) was created on 18 November
2026 using the existing company page and approved logo. Share on LinkedIn and
OIDC sign-in are enabled; the callback below is registered and credentials
are saved in the private runtime configuration. Web and worker were recreated.
The first-login terms step is complete (observed in the local account record
and the browser on 18 November). Eliot Puplett’s personal profile is now
connected; the provider’s live profile endpoint independently matched the saved
identity. The token currently expires on 17 January 2027 at 23:22 UTC.

Personal posting uses the app's OIDC and Share products, with:

```text
PLATFORM_LINKEDIN_PERSONAL_CLIENT_ID=...
PLATFORM_LINKEDIN_PERSONAL_CLIENT_SECRET=...
http://localhost:4010/social-accounts/callback/linkedin_personal/
```

Put credentials in `cosimo/private/runtime.env`, register the exact callback
in the LinkedIn developer app, recreate web/worker, and connect through Social
Accounts. Verify the resulting identity. Do not infer comments or analytics
access from successful sign-in. The basic personal mode requires manual token
reconnection when it expires; it does not support the incoming inbox.

Company publishing/comments and expanded personal comments need the relevant
approved LinkedIn app and scopes. Its provider credentials use
`PLATFORM_LINKEDIN_COMPANY_CLIENT_ID` / `...CLIENT_SECRET`, with the additional
`/social-accounts/callback/linkedin_company/` callback. Validate granted scopes
in the actual app; record each account's usable capabilities separately.

Create a workspace API key allowlisted to the intended account with
`create_posts` and `upload_media`. Save the token in a private file. The handoff
does not require `publish_directly` and cannot schedule or publish.

## Content-engine handoff

```sh
node cosimo/content-handoff.mjs prepare \
  --manifest /absolute/path/to/delivery.json \
  --speaker 'Speaker name' --out cosimo/private/bundle.json

node --dns-result-order=ipv4first cosimo/content-handoff.mjs import \
  --bundle cosimo/private/bundle.json --url http://localhost:4010 \
  --token-file cosimo/private/api-token --account ACCOUNT_UUID \
  --journal cosimo/private/handoff-journal.json
```

Preparation verifies the original text/cartoon hashes and preserves the source
ID, speaker, title, caption, links and alt text. Import creates **drafts only**.
It uploads media through the native API, reads back the saved draft, and stores
the resulting IDs in an atomic local journal. Repeat imports reuse those IDs;
changed source versions require editing the existing draft rather than making
a duplicate. Preserve the journal in backups. Use one journal per hub/account.

Preparation also assigns each pick its planned publishing day: picks in order
go to Tuesday, Wednesday and Thursday of the delivery week at 12:15 p.m.
America/New_York (DST-aware). Override the weekday offsets with `--days 1,2,4`
(0 is Monday). The planned time is stored in the bundle, the draft's internal
notes and the journal entry. Import still creates drafts only; after Eliot's
Monday batch approval, schedule each draft natively for its recorded `plannedAt`.
A replayed import of an existing source ID reuses its draft. A changed source
version returns `source_changed` for that ID and continues with the others; it
never overwrites the native draft or creates a second one. Version identity
uses the text, image and visible fields, not local file paths or planning fields.

An unresolved request older than 23 hours, a changed credential during an
unresolved import, or a missing saved draft stops the bridge for reconciliation.
Upstream's replay cache expires after 24 hours. A leftover `.lock` file must be
removed only after confirming the recorded process is no longer running.

Calendar migration is a separate next step. Do not import already-published
history as new drafts. Current weekly production and manual posting continue
until the real account and publishing path are verified.

## Verification and remaining work

The local HTTP/PostgreSQL integration check ran successfully on 18 November:

```sh
docker compose -f cosimo/compose.yaml exec -T web python manage.py check
docker compose -f cosimo/compose.yaml exec -T web python manage.py shell < cosimo/verify-api.py
```

Verified: media upload, forced database-finalization failure rollback, replay,
concurrent duplicate prevention, changed-body rejection, native schedule and
cancel, real connector import/readback, persistent-journal reuse after server
cache expiry, changed-version rejection, and invalid authentication rejection.
It uses a disposable workspace against the running service and real PostgreSQL,
cleans its data, and makes no social platform calls. No end-to-end platform
tests were run. Browser visual verification was unavailable.

Completed since the initial integration check: personal OAuth connection, live
profile identity verification, and the real-account written/still draft import.
The requested OAuth scope set is `openid profile email w_member_social`; the
connection record reports no missing scopes, which is not proof of every
LinkedIn capability.

Remaining: actual timed publication, always-on hosting and off-machine backup;
complete historical platform reconciliation; comments/analytics capability verification.
The first approved immediate publication and current three-post queue reconciliation
are complete (see the current checkpoint above). Selection and local
installation do not establish that those steps work.

## Ownership, costs and updates

Both evaluated cores use AGPL-3.0. Keep [LICENSE](../LICENSE) and notices. When
running a modified version for network users, provide the corresponding source
as required by AGPL. The public Cosimo fork can carry our modifications;
deployment secrets and private content do not belong in it. No mandatory
vendor software subscription is required for the selected core capabilities.
Optional hosted Intelligence is disabled. Hosting/storage, external models and
platform services may have separate costs; no paid services were purchased.

Keep `upstream` pointing at BrightBean and `origin` at the Cosimo fork. Changes
are on `cosimo/adoption`. Before upgrading, back up the database, media and
private configuration/journals, fetch upstream, review migrations and merge on
a new branch. Rebuild and run the integration check before switching the
running instance. Keep the old image and backup until the upgrade is verified;
schema changes may require restoring the database, not merely an old image.
The source revision is pinned here; upstream's base-image tags and Python
dependency ranges can change on rebuild. Record the installed image/dependency
snapshot separately when promoting to remote production.

There is no second scheduler or inbox in this fork. The custom additions are
the local deployment, draft bridge, integration check, and transactional fix
that commits post creation and its replay response together.

## Cosimo interface — 18 November 2026

The local fork now uses the website’s light theme: warm cream, Cosimo purple,
Space Grotesk body type, EB Garamond headings, IBM Plex Mono labels, and the
orbital mark. The shared shell, login, page titles and calendar controls are
branded Cosimo Publishing. The theme lives in `static/cosimo/publishing.css`;
upstream styles remain separate. Website fonts are bundled with their OFL
licences. Source/licence attribution remains visible in the application.

This is the AGPL-3.0 self-hosted code, not a signup to BrightBean’s hosted
service. The upstream first-login service-terms screen links directly to the
vendor’s terms; that UI is distinct from the software licence. Its wording now
identifies that distinction. This change did not accept or bypass any terms,
change posting permissions, or connect/publish to a social account.

Verification: Docker/Tailwind/static-assets build, Django system check and all
250 templates compiled. The real publishing workspace was inspected in Chrome.
Further visual checks stopped when the browser switched to Eliot’s meeting;
no meeting controls were touched. Dark-theme adaptation and deeper workflow
redesign are not part of this first visual pass.


## Connected account and draft handoff — 18 November 2026

The native OAuth flow returned “Connected Eliot Puplett successfully.” A later
read-only call to LinkedIn’s profile endpoint confirmed the same name and
platform ID as the saved account. Account UUID:
`b31e1e8c-9d30-4307-8462-968d66ba7b9c`.

Historical 18 November import: the three weekly outputs entered as unscheduled drafts.
Current state: pick 3 is published; picks 1 and 2 remain drafts.

| Source ID | Hub draft ID |
|---|---|
| `weekly:2026-11-16:1` | `1d7d7aea-00c4-4577-8fa5-95cd8761f3e0` |
| `weekly:2026-11-16:2` | `cb1658bd-60fc-41c9-99f6-4c4caf00f376` |
| `weekly:2026-11-16:3` | `ab28de8a-fbe8-477c-bafa-ce822ff77987` |

Saved captions and original PNG files match their source SHA-256 hashes. All
three media assets finished processing at 1254×1254. Every platform record
remains a draft, with no scheduled or published timestamp. Repeating the import
returned all three existing IDs without creating duplicates. This is a data
handoff verification, not editorial approval or evidence of public publication.

The private handoff key grants only `create_posts` and `upload_media` for this
account. Its token and replay journal remain in `cosimo/private/`. The Mac’s
Node resolver selected IPv6 for `localhost`, while Docker binds IPv4 only;
use the documented `--dns-result-order=ipv4first` option. The first failed
connection occurred before any import write.

A private local snapshot of PostgreSQL, media, runtime configuration and the
handoff files is in `cosimo/private/backups/20261118T232643Z`. Both archive
indexes were readable. The [restore rehearsal](restore-rehearsal.md) subsequently
passed on 20 November: a disposable, externally disconnected PostgreSQL restored
95 tables, six media files and three encrypted values; all three weekly drafts
matched the saved source and stayed unchanged in the live instance. Off-machine
backup and recovery of later changes remain outstanding. Do not commit or upload
this snapshot to the public fork.

### Always-on deployment preparation

The website checkout contains a Railway deployment configuration, and this
fork includes an upstream `railway.toml` and `render.yaml`. That does not prove
access to an existing hosting account or spare hosting capacity. No new cloud
resources or paid plan were created during local setup.

For a remote deployment, reuse the production Django settings, run migrations,
run web and worker continuously against one PostgreSQL database, and configure
shared object storage for media. Keep email delivery and hosted Intelligence
disabled until deliberately configured. Preserve the existing encryption keys
when migrating the database so stored OAuth tokens remain readable. Disable
public signup, set the exact allowed HTTPS hostname/CSRF origin, and register
its LinkedIn callback before switching the content handoff. Keep the local
instance unscheduled during migration so only one worker owns live publishing.

The upstream Render blueprint’s `plan: free` is not a verified current hosting
quote. Railway’s current pricing is usage-based; its free plan has sleeping
services and limited monthly credit. Confirm account access, an agreed spending
limit, persistent storage and backups before choosing a production deployment.
References: https://docs.railway.com/pricing and
https://docs.railway.com/pricing/free-plan.
