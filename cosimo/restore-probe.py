"""Read-only restore evidence; invoked by restore-rehearsal.py, never a worker."""
import hashlib
import json
import os
import sys
from pathlib import Path

sys.path.insert(0, "/app")
import django

django.setup()
from django.apps import apps
from django.db import connection, transaction
from apps.common.encryption import EncryptedJSONField, EncryptedTextField, decrypt_value
from apps.composer.models import Post
from apps.calendar.models import PostingSlot
from apps.publisher.models import PublishLog
from apps.media_library.models import MediaAsset




def digest(data):
    return hashlib.sha256(data).hexdigest()


with transaction.atomic():
    with connection.cursor() as cursor:
        cursor.execute("SET TRANSACTION READ ONLY")
    posts = []
    for post in Post.objects.all().order_by("id"):
        posts.append({
            "id": str(post.id), "captionSha256": digest(post.caption.encode()),
            "status": post.status, "scheduledAt": post.scheduled_at,
            "publishedAt": post.published_at,
            "platforms": list(post.platform_posts.order_by("id").values(
                "id", "social_account_id", "status", "scheduled_at", "published_at", "platform_post_id")),
            "mediaIds": [str(x) for x in post.media_attachments.order_by("position").values_list("media_asset_id", flat=True)],
        })
    slots = list(PostingSlot.objects.order_by("social_account_id", "day_of_week", "time").values(
        "id", "social_account_id", "day_of_week", "time", "is_active"))
    logs = list(PublishLog.objects.order_by("id").values(
        "id", "platform_post_id", "attempt_number", "status_code", "created_at"))
    files = []
    for asset in MediaAsset.objects.order_by("id"):
        for field in [asset.file, asset.thumbnail]:
            if field:
                # Use Django's storage interface for local files and private S3.
                size = 0
                checksum = hashlib.sha256()
                with field.open("rb") as source:
                    for chunk in iter(lambda: source.read(1024 * 1024), b""):
                        size += len(chunk)
                        checksum.update(chunk)
                files.append({"path": field.name, "bytes": size, "sha256": checksum.hexdigest()})
    result = {"posts": posts, "slots": slots, "publishLogs": logs, "mediaFiles": files}
    if os.environ.get("COSIMO_RESTORE_PROBE") == "1":
        backup = Path(os.environ.get("COSIMO_RESTORE_DIRECTORY", "/backup"))
        expected_path = backup / "expected-state.json"
        if expected_path.exists():
            expected = json.loads(expected_path.read_text())
            assert json.loads(json.dumps(result, default=str)) == expected, "Restored state differs from saved snapshot"
        else:
            # Original 18 November snapshot predates publication. Its own bundle,
            # not today's live state, remains the historical acceptance source.
            bundle = json.loads((backup / "weekly-bundle.json").read_text())
            journal = json.loads((backup / "handoff-journal.json").read_text())
        by_id = {p["id"]: p for p in posts}
        for item in ([] if expected_path.exists() else bundle["posts"]):
            entry = journal["posts"][item["sourceId"]]
            post = by_id[entry["postId"]]
            assert post["captionSha256"] == item["textSha256"] == digest(item["caption"].encode())
            assert post["mediaIds"] == [entry["mediaId"]]
            asset = MediaAsset.objects.get(pk=entry["mediaId"])
            data = Path(asset.file.path).read_bytes()
            assert digest(data) == item["imageSha256"]
            assert len(data) == asset.file_size
        encrypted_count = 0
        with connection.cursor() as cursor:
            tables = connection.introspection.table_names(cursor)
            table_counts = {}
            for table in sorted(tables):
                cursor.execute(f"SELECT count(*) FROM {connection.ops.quote_name(table)}")
                table_counts[table] = cursor.fetchone()[0]
            first_encrypted = None
            for model in apps.get_models():
                if model._meta.db_table not in tables:
                    continue
                for field in model._meta.fields:
                    if isinstance(field, (EncryptedTextField, EncryptedJSONField)):
                        cursor.execute(f"SELECT {connection.ops.quote_name(field.column)} FROM {connection.ops.quote_name(model._meta.db_table)} WHERE {connection.ops.quote_name(field.column)} IS NOT NULL")
                        for (ciphertext,) in cursor.fetchall():
                            decrypt_value(ciphertext)
                            encrypted_count += 1
                            first_encrypted = first_encrypted or ciphertext
        assert encrypted_count > 0, "No encrypted fields tested"
        from django.test.utils import override_settings
        wrong_key_rejected = False
        try:
            with override_settings(SECRET_KEY="restore-rehearsal-intentionally-wrong-key"):
                decrypt_value(first_encrypted)
        except Exception as exc:
            from cryptography.exceptions import InvalidTag
            if not isinstance(exc, InvalidTag):
                raise
            wrong_key_rejected = True
        assert wrong_key_rejected
        result.update({"tableCounts": table_counts, "mediaFiles": files,
                       "encryptedValuesDecrypted": encrypted_count,
                       "wrongKeyRejected": wrong_key_rejected,
                       "snapshotStateMatched": expected_path.exists(),
                       "legacyBundleAndJournalMatched": not expected_path.exists()})
print(json.dumps(result, default=str))
