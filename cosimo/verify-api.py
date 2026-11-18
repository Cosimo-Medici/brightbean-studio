"""Local HTTP/PostgreSQL integration check; never calls a social platform.

Run in the web container with `python manage.py shell < cosimo/verify-api.py`.
Creates an isolated temporary workspace and removes all its data in finally.
Requires the real web process and PostgreSQL; no mocked backend.
"""
import concurrent.futures
from datetime import timedelta
import io
import json
import hashlib
from pathlib import Path
import subprocess
import tempfile
import uuid

import requests
from PIL import Image
from django.contrib.auth import get_user_model
from django.db import connection
from django.utils import timezone
from apps.organizations.models import Organization
from apps.workspaces.models import Workspace
from apps.members.models import OrgMembership, WorkspaceMembership
from apps.social_accounts.models import SocialAccount
from apps.api_keys.services import issue_api_key
from apps.composer.models import Post
from apps.media_library.models import MediaAsset

assert connection.vendor == "postgresql", "This check requires real PostgreSQL."
suffix = uuid.uuid4().hex
trigger = f"cosimo_fail_{suffix}"
key = f"cosimo-replay-{suffix}"
org = user = workspace = None
session = requests.Session()
base = "http://localhost:8000/api/v1"

def call(method, route, expected=200, **kwargs):
    result = session.request(method, base + route, timeout=20, **kwargs)
    assert result.status_code == expected, (route, result.status_code, result.text[:400])
    return result.json()

try:
    user = get_user_model().objects.create_user(f"verify-{suffix}@localhost")
    org = Organization.objects.create(name=f"Verification {suffix}")
    workspace = Workspace.objects.create(organization=org, name="Disposable API verification")
    OrgMembership.objects.create(organization=org, user=user, org_role="owner")
    WorkspaceMembership.objects.create(workspace=workspace, user=user, workspace_role="owner")
    account = SocialAccount(workspace=workspace, platform="linkedin_personal", account_platform_id=suffix,
                            account_name="LOCAL FIXTURE — NO LINKEDIN CONNECTION", connection_status="connected")
    account._skip_analytics_backfill = True
    account.save()
    issued = issue_api_key(workspace=workspace, social_accounts=[account], issued_by=user, name="Disposable verification",
                           permissions=["create_posts", "publish_directly", "upload_media"])
    session.headers["Authorization"] = f"Bearer {issued.plaintext_token}"
    assert call("GET", "/accounts/")["accounts"][0]["id"] == str(account.id)

    png = io.BytesIO()
    Image.new("RGB", (100, 100), (220, 220, 220)).save(png, format="PNG")
    media = call("POST", "/media/", expected=201,
                 files={"file": ("local-verification.png", png.getvalue(), "image/png")},
                 data={"alt_text": "Local API verification square", "idempotency_key": f"media-{suffix}"})
    body = {"social_account_id": str(account.id), "caption": "Local verification — never publish.",
            "media_asset_ids": [media["id"]], "action": "draft", "idempotency_key": key}

    # Force the actual database UPDATE of the replay response to fail, after
    # create_post has run. Creation must roll back along with finalization.
    with connection.cursor() as cursor:
        cursor.execute(f"""CREATE FUNCTION {trigger}() RETURNS trigger LANGUAGE plpgsql AS $$
          BEGIN IF NEW.key = '{key}' AND NEW.response_status > 0 THEN
          RAISE EXCEPTION 'intentional local replay-finalization failure'; END IF;
          RETURN NEW; END; $$""")
        cursor.execute(f"CREATE TRIGGER {trigger} BEFORE UPDATE ON agent_api_idempotency FOR EACH ROW EXECUTE FUNCTION {trigger}()")
    failed = session.post(base + "/posts/", json=body, timeout=20)
    assert failed.status_code == 500, failed.status_code
    assert Post.objects.filter(workspace=workspace).count() == 0, "Failed finalization left an orphan post."
    with connection.cursor() as cursor:
        cursor.execute(f"DROP TRIGGER {trigger} ON agent_api_idempotency")
        cursor.execute(f"DROP FUNCTION {trigger}()")

    created = call("POST", "/posts/", expected=201, json=body)
    replay = call("POST", "/posts/", expected=201, json=body)
    assert created["id"] == replay["id"]
    assert Post.objects.filter(workspace=workspace).count() == 1
    assert call("GET", f"/posts/{created['id']}")["caption"] == body["caption"]
    call("POST", "/posts/", expected=422, json={**body, "caption": "Changed copy with reused key"})

    parallel_body = {**body, "idempotency_key": f"parallel-{suffix}"}
    def parallel_create(_):
        r = requests.post(base + "/posts/", json=parallel_body, headers=dict(session.headers), timeout=20)
        return r.status_code, r.json()
    with concurrent.futures.ThreadPoolExecutor(max_workers=3) as pool:
        parallel = list(pool.map(parallel_create, range(3)))
    assert all(status in (201, 409) for status, _ in parallel), parallel
    assert len({data["id"] for status, data in parallel if status == 201}) == 1
    assert Post.objects.filter(workspace=workspace).count() == 2

    scheduled = call("POST", f"/posts/{created['id']}/schedule",
                     json={"scheduled_at": (timezone.now() + timedelta(days=30)).isoformat()})
    assert scheduled["status"] == "scheduled" and scheduled["published_at"] is None
    cancelled = call("POST", f"/posts/{created['id']}/cancel")
    assert cancelled["status"] == "draft" and cancelled["published_at"] is None

    # Run the actual content-engine connector against this real HTTP service.
    # Expire server replay records between runs: its persistent journal must
    # still reuse the original draft rather than creating another one.
    from apps.api.models import IdempotencyRecord
    with tempfile.TemporaryDirectory(prefix="cosimo-handoff-") as temp:
        root = Path(temp)
        caption = "Disposable connector verification.\n"
        (root / "post.txt").write_text(caption)
        (root / "cartoon.png").write_bytes(png.getvalue())
        (root / "token").write_text(issued.plaintext_token)
        (root / "token").chmod(0o600)
        manifest = {"status": "ready", "date": "2026-11-16", "posts": [{
            "pick": 1, "title": "Local connector verification", "altText": "Grey square",
            "text": str(root / "post.txt"), "image": str(root / "cartoon.png"),
            "textSha256": hashlib.sha256(caption.encode()).hexdigest(),
            "imageSha256": hashlib.sha256(png.getvalue()).hexdigest(),
        }]}
        (root / "manifest.json").write_text(json.dumps(manifest))
        subprocess.run(["node", "cosimo/content-handoff.mjs", "prepare", "--manifest", str(root / "manifest.json"),
                        "--speaker", "Local verification", "--out", str(root / "bundle.json")], check=True, capture_output=True)
        command = ["node", "cosimo/content-handoff.mjs", "import", "--bundle", str(root / "bundle.json"),
                   "--url", "http://localhost:8000", "--token-file", str(root / "token"),
                   "--account", str(account.id), "--journal", str(root / "journal.json")]
        first = subprocess.run(command, check=True, capture_output=True, text=True)
        IdempotencyRecord.objects.filter(api_key=issued.api_key).delete()
        second = subprocess.run(command, check=True, capture_output=True, text=True)
        first_result, second_result = json.loads(first.stdout)[0], json.loads(second.stdout)[0]
        assert first_result["id"] == second_result["id"] and second_result["reused"] is True
        assert Post.objects.filter(workspace=workspace).count() == 3
        changed = json.loads((root / "bundle.json").read_text())
        changed["posts"][0]["caption"] = "Changed copy"
        changed["posts"][0]["textSha256"] = hashlib.sha256(b"Changed copy").hexdigest()
        (root / "bundle.json").write_text(json.dumps(changed))
        rejected = subprocess.run(command, capture_output=True, text=True)
        assert rejected.returncode != 0 and "different version" in rejected.stderr
        assert Post.objects.filter(workspace=workspace).count() == 3
    issued.api_key.revoked_at = timezone.now()
    issued.api_key.save(update_fields=["revoked_at"])
    # Auth caches permit up to 30s revocation delay; an invalid token must fail now.
    session.headers["Authorization"] = "Bearer invalid"
    call("GET", "/accounts/", expected=401)
    print(json.dumps({"passed": ["real media upload", "database failure rollback", "retry replay", "changed-body rejection", "concurrent duplicate prevention", "schedule and cancel", "connector import and readback", "connector replay after server cache expiry", "connector changed-version rejection", "invalid auth rejection"], "platform_calls": 0}))
finally:
    with connection.cursor() as cursor:
        cursor.execute(f"DROP TRIGGER IF EXISTS {trigger} ON agent_api_idempotency")
        cursor.execute(f"DROP FUNCTION IF EXISTS {trigger}()")
    if workspace:
        for asset in MediaAsset.objects.filter(workspace=workspace):
            asset.file.delete(save=False)
            if asset.thumbnail:
                asset.thumbnail.delete(save=False)
    if org:
        org.delete()
    if user:
        user.delete()
    session.close()
    print("Temporary verification workspace, account, posts, keys and media removed.")
