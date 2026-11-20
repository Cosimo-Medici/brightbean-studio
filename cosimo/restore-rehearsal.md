# Private backup restore rehearsal

## Hosted backup — 20 November after cutover

The production publisher now runs in its own Railway project. Daily remote capture and actual destination restore passed for `snapshots/20261120T192808Z/`: 95 tables, eight media objects, three encrypted values, matching saved post/slot/log state and rejection of the wrong key. No worker started and disposable containers were removed. The hosted journal origin and all three source IDs survived recovery.

Receipt: `cosimo/private/railway/restore-20261120-remote-v1/verification.json`. See [hosted operation and recovery](railway-cutover.md) for resource IDs, download/restore commands and the 23:30 UTC schedule. The local daily backup job is disabled and unloaded; the local checkpoints below are historical. The tested snapshot is recoverable; future captures still require periodic restore verification.

## Earlier local snapshot — 20 November after publication

`cosimo/private/backups/20261120-published-pre-update` was captured and restored
into isolated PostgreSQL. It recovered the actual published Friday record and
provider ID, both unscheduled drafts, all five 12:15 posting slots, the successful
publish-log entry and eight referenced media files. The probe read 95 tables and
decrypted the saved encrypted values; an incorrect key was rejected. Live state
and snapshot files were unchanged and disposable containers were removed.
Evidence: `publisher-restore/20261120-published-pre-update/verification.json`
under the private content state directory.

Create a new snapshot (never reuse a destination):

```sh
python3 cosimo/backup.py cosimo/private/backups/UNIQUE_SNAPSHOT
python3 cosimo/restore-rehearsal.py cosimo/private/backups/UNIQUE_SNAPSHOT /absolute/private/new-evidence-directory
```

Capture preserves database, media, credentials and handoff files. It records
post/slot/log/media state before and after and refuses a changing snapshot.
Restoration compares with that snapshot's expected state, not a hardcoded
assumption that all posts remain drafts or match today's live database. Capture
manifests must be successful and their file hashes must match before restoring.
The backup remains local; this does not establish off-machine recovery.

## Retired automatic daily local capture

`work.cosimo.publishing.backup` is installed in the operator's LaunchAgents at
18:30 Mac local time (currently Eastern). It runs `backup.py` with a new UTC
snapshot directory, writes private stdout/stderr logs and never deletes old
backups. Docker must be running. First launch invocation exited 0, and its
`20261120T175330Z` snapshot was restored with the current deployed image:
`publisher-restore/20261120-automatic-backup-v3/verification.json`.

The first restore attempt failed before producing restored evidence; its live
state, snapshot and cleanup checks passed. The unchanged snapshot subsequently
restored successfully. The runner now retains failed-command stderr privately
and waits for TCP readiness, avoiding PostgreSQL's temporary init-server socket.
The exact first command failure was not captured and is not claimed diagnosed.
Daily capture does not automatically run a restore or provide off-machine storage.

## Historical 18 November snapshot

The existing 18 November snapshot was actually restored on 20 November into a
fresh PostgreSQL 16 container. The container had `--network none`; the one-off
application probe shared only its isolated network namespace. No web server,
worker, migration, provider request, or production database write was invoked.

```sh
python3 cosimo/restore-rehearsal.py \
  cosimo/private/backups/20261118T232643Z \
  "$HOME/Library/Application Support/cosimo-content/publisher-restore/NEW_RUN"
```

The evidence destination must be new. Use the currently installed Docker app
image, retain the snapshot's runtime encryption keys, and override only the
database/storage locations for the disposable restore. Do not expose or upload
the snapshot: it contains database records, OAuth credentials and private keys.

The script validates archive paths and rejects symlinks/traversal, restores the
dump with `pg_restore --exit-on-error`, checks all database table counts, reads
every referenced original/thumbnail file, and decrypts saved encrypted fields
without printing their contents. A deliberately incorrect key must fail. The
three weekly captions and attached originals must match their saved bundle and
handoff journal; live draft state is read before/after and must remain identical.
Disposable containers and their anonymous database volume are removed in
`finally`. Evidence and extracted media remain in the private evidence directory.

Verified run: `publisher-restore/20261120-v2/verification.json` under the private
content state directory. It restored 95 tables (2,611 rows), six referenced media
files and three encrypted values. All three original draft IDs, captions, media
attachments and unscheduled/unpublished states matched. The snapshot's files
were unchanged and disposable containers were removed.

The deliberately corrupted-dump check in `publisher-restore/corrupt-dump-v1`
also failed as intended: PostgreSQL rejected it, the evidence stayed failed,
disposable containers were removed and live drafts were unchanged. Final status
is assigned only after every isolation check; cleanup is attempted even if
container creation returns an error or timeout.

This proves this particular snapshot can recover those stored records and
assets with the current image. It does not prove recovery of changes made after
18 November, current token validity, publishing, a production cutover, an
off-machine backup, or recovery after losing this Mac. Those remain separate.
