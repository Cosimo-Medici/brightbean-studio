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

## Local operation

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

No real LinkedIn account was connected during adoption. Browser access was
unavailable and no app credentials were found in the marketing configuration.

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

node cosimo/content-handoff.mjs import \
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

Remaining: OAuth identity/scopes; real-account written/still draft import;
one specifically approved publication with actual permalink, copy, image and
timestamp reconciliation; always-on hosting choice; native calendar/history
migration; comments/analytics capability verification. Selection and local
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
