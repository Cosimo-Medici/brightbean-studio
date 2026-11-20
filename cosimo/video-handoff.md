# Local video draft handoff — ENG-1000

This extends the existing BrightBean handoff with a small video adapter. The
PNG bridge, native publisher, worker and schedules are unchanged. It only calls
the local native media/post API and always creates `action: draft`.

## Prepare

Use Node 22. The sibling `cosimo-content-engine` checkout supplies the existing
`lib/media-clip.cjs` verifier; FFmpeg/ffprobe must be available. The verifier
reopens the episode, clip request, source film/captions, output media and embedded
caption timing before preparation and before import.

```sh
node cosimo/video-handoff.mjs prepare \
  --clip /absolute/path/clip.json \
  --caption /absolute/path/caption.txt \
  --title 'Clip title' --speaker company \
  --out /absolute/private/path/video-bundle.json
```

The caption must include the exact fictional/source disclosure from the clip.
This retains an explicit `draft_only_unreviewed` status and the clip's outstanding
sound/style/tone/editorial checks. Preparation is technical verification, not
creative approval. No model or new narration is invoked.

## Native handoff

```sh
node --dns-result-order=ipv4first cosimo/video-handoff.mjs import \
  --bundle /absolute/private/path/video-bundle.json \
  --url http://127.0.0.1:4010 \
  --token-file /absolute/private/path/api-token \
  --account ACCOUNT_UUID \
  --journal /absolute/private/path/video-journal.json
```

Use a key with `upload_media` and `create_posts`, without `publish_directly`,
allowlisted to the intended account. This adapter currently permits local
loopback origins and native LinkedIn personal/company draft accounts only.
YouTube, external object-storage validation and platform publication are not
verified by this component.

The adapter checks the account's actual native caption budget, uploads the MP4
through BrightBean, waits at most 30 observations for native processing, verifies
media dimensions/duration, downloads the original stored file and checks its
SHA-256. It then creates a draft and reads back caption, source metadata and
unscheduled state. H.264/AAC is the current verified media contract.

Original parent episode/source IDs, source/clip/video/caption hashes, disclosure
and review state are retained in private notes and the journal. Selectable MP4
captions stay in the byte-identical uploaded asset. The SRT sidecar is recorded
as provenance; no platform sidecar-caption upload is implemented.

## Replay and edits

Keep one persistent journal per hub/account. Same-source replay reads the saved
post ID even after native idempotency records expire. Native caption edits are
reported and retained, never overwritten. Changed input versions are rejected.
A missing saved draft stops on 404; it is never recreated automatically. An
unresolved operation over 23 hours old or using a changed key requires explicit
reconciliation. Leftover operation locks require checking the recorded PID
before removal. Preserve journals with deployment backups.

The Cosimo Post REST response now includes ordered `media_asset_ids`. Draft
creation and replay verify that the post still has exactly the journaled video.
A detached or replaced attachment stops replay without overwriting native edits.
Returned `attachmentVerification` says `native_rest_media_ids`; PostgreSQL and
stored-byte checks independently verify this in the disposable component check.

## Verification performed

```sh
python3 cosimo/verify-video-handoff.py
```

This bounded check used the actual verified 20.1-second Chianti technical clip,
the running local HTTP service/PostgreSQL and a disposable credentialless account.
Nine checks passed:

1. Existing clip verifier reopened actual inputs/output/captions.
2. Native upload processed at 1920×1080 and downloaded bytes matched SHA-256.
3. Draft caption/source identity and unscheduled state matched.
4. PostgreSQL contained exactly the correct video attachment; storage hash matched.
5. Persistent journal reused post/media IDs after native replay-cache expiry.
6. Native caption edits survived replay.
7. Changed source versions were rejected.
8. Native attachment IDs matched; detaching the video stopped replay without restoration.
9. Deleted saved draft stopped on 404 after cache expiry without recreation.

All fixture posts, media files/thumbnails, organizations, users, account and keys
were removed. No real Friday draft, provider token, OAuth flow, scheduling or
platform API was touched. No end-to-end platform test ran.

Private evidence:
`~/Library/Application Support/cosimo-content/publisher-video/verification.json`.

Remaining: editorial/sound/style/full playback, actual account video permission,
authorized platform upload/publication/permalink, company/YouTube/RSS acceptance,
and real metrics. A native draft or source-inspected provider method is not proof
that any of those outcomes occurred.
