# Cosimo Publishing — hosted operation and recovery

Phase 1 of the [Linear completion checklist](https://linear.app/cosimo-medici/document/marketing-and-sales-ten-system-completion-checklist-3793d765b85a).
Updated 20 November 2026.

## Separate repository and hosting project

Source: [Cosimo-Medici/brightbean-studio](https://github.com/Cosimo-Medici/brightbean-studio), branch `cosimo/adoption`, local checkout `/Users/eliotpuplett/Documents/Cosimo/cosimo-publishing`.
This checkout is outside the Cosimo product monorepo. Preserve the BrightBean upstream remote for future updates.

Hosting: [Cosimo Publishing](https://railway.com/project/7c928eae-6186-412e-b796-902471261595), production environment `dd59b099-d182-454c-839b-d5c1d1ffe77e`, in the existing Medici workspace. No publisher resources were added to the product's Cosimo project, and its services were not changed.

Hub: https://publisher-web-production-e78fb5fd.up.railway.app

| Resource | ID | Purpose |
| --- | --- | --- |
| publisher-web | 359b1b4e-2beb-4788-ac19-def35eb1406f | Production Django web/API, one process with four threads |
| publisher-worker | 969adf73-b5da-4962-b1a3-d993c6721613 | One continuous native publishing worker |
| Postgres | c5fd8fed-0ef4-4187-9d72-a39508dafa56 | Dedicated PostgreSQL 18 database and volume, private network |
| publisher-backup | d9a8a6ec-8fff-4710-a120-90729dc2097b | Daily backup cron, no restart after completion |
| publishing-media | 2e096255-df84-43cd-a3ad-bd94997800f0 | Private S3-compatible media bucket |
| publishing-backups | 34856046-9ba7-4994-a676-72aec9c499e1 | Separate private recovery bucket |

## Operator sign-in

Use **Log in with Google** on the hosted `/accounts/login/` page with `ecp@medici.ai`. On 20 November the actual Google OAuth flow reached the existing calendar; provider-verified email, SocialAccount and OAuthConnection readback all matched the original user. One user and one workspace remain. Public signup stays closed. The original `operator@localhost` password fallback remains usable; its credential is stored only in ignored `cosimo/private/operator.env`.

Google login uses the dedicated Google Cloud project **Cosimo Publishing** (`cosimo-publishing`), under the medici.ai organization, with an Internal audience and the web client **Cosimo Publishing - production web**. Its sole callback is `https://publisher-web-production-e78fb5fd.up.railway.app/accounts/google/login/callback/`. Login requests only profile/email access. Client credentials are installed as `GOOGLE_AUTH_CLIENT_ID` and `GOOGLE_AUTH_CLIENT_SECRET`; both are included in the backup runtime allowlist. No product/outreach OAuth client was reused.

The original upstream settings registered an empty Google APP, making a broken button appear and producing Google's `Missing required parameter: client_id` error. The repaired settings register the app only when both credentials exist, preserving provider options and any legitimately database-configured app. Recovery must preserve both credentials, the exact callback and existing allauth identity records. Never create a replacement user/workspace to repair sign-in. Private evidence: `cosimo/private/railway/google-login-verification.json`; web deployment `d4770b3d-76b8-4c9a-9273-bf598796e893`.

## Verified cutover

CLI authorization completed after Eliot's confirmation. The local worker was stopped and its Docker restart policy set to `no` before the final snapshot `cosimo/private/backups/20261120T191301Z`. The compose worker now requires the explicit `local-publisher` profile; a routine compose up cannot restart it.

The remote database restored from that snapshot. The isolated readback matched all post/slot/publish-log state, enumerated 95 restored tables and decrypted three saved encrypted values; the wrong key was rejected. All eight media objects were copied with byte-count and SHA-256 readback. Hosted HTTPS health/login and authenticated API reads passed. A read-only LinkedIn profile request from the hosted web service matched the saved identity; the existing token expires 17 January 2027.

The live inventory is three published records and zero queued/draft posts. Two records were reconciled to already-live external history before cutover; exact external timestamps and source-copy equality remain qualified. No new provider publication occurred during migration. Preserve all source IDs and existing post IDs.

ALLOWED_HOSTS includes the actual public hostname plus the exact `healthcheck.railway.app` hostname used by Railway health probes. Omitting the latter causes replacement deployments to fail their health gate even while public HTTPS health works; no wildcard host allowance is used.

Signup is closed; optional hosted Intelligence and email delivery remain disabled. Existing encryption keys are preserved privately. LinkedIn app 266747924 now contains both callback URLs, saved and read back in the provider UI:

- `https://publisher-web-production-e78fb5fd.up.railway.app/social-accounts/callback/linkedin_personal/`
- `http://localhost:4010/social-accounts/callback/linkedin_personal/` (rollback)

The private handoff journal now points to the HTTPS hub. Do not reimport the existing source IDs. The remote worker's native publishing cycles completed successfully after the local worker was stopped.

## Deployments

CLI: `~/.local/share/cosimo-publishing-tools/node_modules/.bin/railway`.
Use explicit project, environment and service IDs for mutations. Keep credentials, runtime env, backups, media and private evidence out of source uploads.

Web and worker use the upstream Dockerfile and native production settings. Backup uses `cosimo/Dockerfile.backup` and `python cosimo/remote-backup.py`. Service settings are configured through Railway's native API. The sanitized upload excludes upstream `railway.toml`; that unused template is not the production configuration. The local CLI may warn about its deprecation when run from the checkout.

Private deployment inputs and verification receipts are under `cosimo/private/railway/`; never commit them. Current local source changes are not yet a committed release. Readback confirmed six publishing implementation files match the local source in both hosted web and worker; receipt: `deployed-source-readback.json` in that private folder.

## Backup and recovery

Cron: `30 23 * * *` (daily 23:30 UTC; 18:30 EST / 19:30 EDT).
The job exports PostgreSQL, every referenced media object, runtime encryption/configuration and the handoff journal into the separate private bucket. A manifest is uploaded last, and `latest.json` advances only after the complete upload. A capture is explicitly not marked restore-verified.

Verified 20 November: actual hosted cron run `1bbfc389-17e8-48ee-b122-9a06f4581d86` completed successfully, creating `snapshots/20261120T192808Z/`. Downloaded all eight recovery files from the private bucket, verified manifest byte counts/SHA-256 hashes, and restored into network-isolated PostgreSQL 18. The snapshot state matched; 95 tables, eight media objects and three encrypted values were recovered, the wrong key was rejected, and disposable containers were removed. The restored journal retains the hosted origin and all three source IDs.

Receipt: `cosimo/private/railway/restore-20261120-remote-v1/verification.json`. The snapshot remains marked capture-only in storage; this separate receipt certifies the tested snapshot, not every future capture. The old Mac daily backup LaunchAgent is now disabled and unloaded to prevent stale local snapshots being mistaken for hosted backups. Its plist is retained privately.

After Google sign-in was verified, cron run `ee3d29c8-7051-450d-8e1a-227880aabf5a` captured `snapshots/20261120T203304Z/`. All eight recovery files were downloaded and hash-verified, and the recovered runtime contains both exact Google login credentials. This latest capture has not been separately restore-rehearsed. Receipt: `cosimo/private/railway/google-login-backup-verification.json`.

The failed initial runs created no committed backup. The exporter now parses the database URL with the installed psycopg 3 library and passes explicit libpq environment fields, keeping credentials out of process arguments. Secret-safe stage diagnostics make future export/probe failures distinguishable.

To download with boto3 installed: `python cosimo/download-backup.py PRIVATE_BUCKET_CREDENTIALS_JSON NEW_PRIVATE_DOWNLOAD_DIRECTORY`. The downloader rejects incomplete captures/unsafe filenames and verifies every downloaded file before writing the local manifest.

To trigger a real capture: `railway cron run --service publisher-backup --environment production --yes`.
Download the prefix named by the bucket's `latest.json` into a new mode-0700 directory, verify every manifest hash, then run:

```sh
python3 cosimo/restore-rehearsal.py PRIVATE_DOWNLOADED_BACKUP NEW_PRIVATE_EVIDENCE_DIRECTORY
```

The rehearsal uses disposable network-isolated PostgreSQL 18, starts no publisher, checks saved records/media and key decryption, and removes the disposable containers. It requires the retained local web image/container for a comparison baseline. Retention/expiry of remote snapshots is not yet configured.

## Rollback and remaining event

Never run two publishing workers. Stop the remote worker and verify it is stopped before enabling any local worker. After any hosted edit or publication, first recover/reconcile the current hosted database and actual provider outcome; the old local queue is stale. Merely changing the journal back is not a safe rollback.

Monday batch approval remains the rule. Schedule each approved piece for its planned day at 12:15 p.m. America/New_York. The next actual approved timed post must still demonstrate copy, image, alt text, identity, timestamp and permalink. Never repost Friday to satisfy acceptance. Whole Phase 1 remains open until that event is verified.
