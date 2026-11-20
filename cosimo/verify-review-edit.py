"""Bounded live HTTP/PostgreSQL draft edit/withdraw verification.

Run: docker compose -f cosimo/compose.yaml exec -T web python manage.py shell
     < cosimo/verify-review-edit.py

Only a disposable workspace, synthetic account without provider credentials,
and draft-only API key are used. No schedule, publish or provider calls.
"""
import json
import uuid
from importlib import import_module

import requests
from django.conf import settings
from django.contrib.auth import get_user_model, SESSION_KEY, BACKEND_SESSION_KEY, HASH_SESSION_KEY
from django.db import connection
from django.utils import timezone

from apps.api.models import IdempotencyRecord
from apps.api_keys.services import issue_api_key
from apps.composer.models import Post
from apps.members.models import OrgMembership, WorkspaceMembership
from apps.organizations.models import Organization
from apps.social_accounts.models import SocialAccount
from apps.workspaces.models import Workspace

assert connection.vendor == "postgresql", "Requires the actual PostgreSQL service."
suffix = uuid.uuid4().hex
origin = "http://localhost:8000"
org = user = workspace = auth_session = None
auto_org_ids = []
api = requests.Session()
native = requests.Session()
evidence = {"checked_at": timezone.now().isoformat(), "checks": [], "gaps": [], "platform_calls": 0}


def api_call(method, route, expected=200, **kwargs):
    response = api.request(method, origin + "/api/v1" + route, timeout=20, allow_redirects=False, **kwargs)
    assert response.status_code == expected, (method, route, response.status_code, response.text[:200])
    return response.json()


try:
    # Terms/session values below belong only to synthetic test data, never the
    # operator account. No user is signed up and no real terms are accepted.
    user = get_user_model().objects.create_user(f"review-component-{suffix}@localhost")
    user.tos_accepted_at = timezone.now()
    user.save(update_fields=["tos_accepted_at"])
    auto_org_ids = list(user.org_memberships.values_list("organization_id", flat=True))
    org = Organization.objects.create(name=f"Disposable review component {suffix}")
    workspace = Workspace.objects.create(organization=org, name="Disposable review verification")
    OrgMembership.objects.create(organization=org, user=user, org_role="owner")
    WorkspaceMembership.objects.create(workspace=workspace, user=user, workspace_role="owner")
    account = SocialAccount(workspace=workspace, platform="linkedin_personal", account_platform_id=suffix,
                            account_name="LOCAL FIXTURE — NO PROVIDER CREDENTIALS", connection_status="connected")
    account._skip_analytics_backfill = True
    account.save()
    issued = issue_api_key(workspace=workspace, social_accounts=[account], issued_by=user,
                           name="Disposable draft review", permissions=["create_posts"])
    api.headers["Authorization"] = f"Bearer {issued.plaintext_token}"
    source_id = f"component-review:{suffix}:company:linkedin-text"
    notes = json.dumps({"sourceId": source_id, "speaker": "Synthetic verification"})
    body = {"social_account_id": str(account.id), "caption": "Disposable original draft.",
            "title": "Disposable review", "internal_notes": notes, "action": "draft",
            "idempotency_key": f"review-{suffix}"}
    created = api_call("POST", "/posts/", expected=201, json=body)
    post_id = created["id"]
    route = f"/posts/{post_id}"
    edited = api_call("PATCH", route, json={"caption": "Disposable edited draft."})
    observed = api_call("GET", route)
    assert edited["id"] == post_id == observed["id"]
    assert observed["caption"] == "Disposable edited draft."
    assert observed["internal_notes"] == notes
    assert observed["status"] == "draft"
    assert observed["scheduled_at"] is None and observed["published_at"] is None
    assert Post.objects.filter(workspace=workspace).count() == 1
    evidence["checks"].append("PATCH/readback retains one draft, original ID and source identity")

    replay = api_call("POST", "/posts/", expected=201, json=body)
    assert replay["id"] == post_id
    assert Post.objects.filter(workspace=workspace).count() == 1
    assert api_call("GET", route)["caption"] == "Disposable edited draft."
    evidence["checks"].append("Create replay after edit does not overwrite current copy or create a duplicate")
    evidence["replay_response_contains_original_caption"] = replay["caption"] == body["caption"]

    # Real native HTTP endpoint with an authenticated fixture session and CSRF.
    auth_session = import_module(settings.SESSION_ENGINE).SessionStore()
    auth_session[SESSION_KEY] = str(user.pk)
    auth_session[BACKEND_SESSION_KEY] = "django.contrib.auth.backends.ModelBackend"
    auth_session[HASH_SESSION_KEY] = user.get_session_auth_hash()
    auth_session.save()
    native.cookies.set(settings.SESSION_COOKIE_NAME, auth_session.session_key)
    editor_url = f"{origin}/workspace/{workspace.id}/compose/{post_id}/"
    editor = native.get(editor_url, timeout=20, allow_redirects=False)
    assert editor.status_code == 200, ("native editor", editor.status_code, editor.headers.get("Location"))
    csrf = native.cookies.get(settings.CSRF_COOKIE_NAME)
    assert csrf, "Native composer did not supply a CSRF cookie."
    removed = native.post(editor_url + "delete/", headers={"X-CSRFToken": csrf, "Referer": editor_url},
                          timeout=20, allow_redirects=False)
    assert removed.status_code == 204, ("native delete", removed.status_code, removed.text[:200])
    assert not Post.objects.filter(workspace=workspace).exists()
    api_call("GET", route, expected=404)
    evidence["checks"].append("Native authenticated deletion removes only disposable draft; DB empty and GET 404")

    withdrawn_replay = api_call("POST", "/posts/", expected=201, json=body)
    assert withdrawn_replay["id"] == post_id
    assert not Post.objects.filter(workspace=workspace).exists()
    api_call("GET", route, expected=404)
    evidence["checks"].append("Replay while cache exists does not recreate withdrawn draft; GET still 404")

    # Bound the replay-cache guarantee explicitly. This deletes only this
    # fixture key's replay row, simulating expiry without waiting or sleeping.
    IdempotencyRecord.objects.filter(api_key=issued.api_key).delete()
    after_expiry = api_call("POST", "/posts/", expected=201, json=body)
    assert after_expiry["id"] != post_id
    assert Post.objects.filter(workspace=workspace).count() == 1
    assert after_expiry["status"] == "draft" and after_expiry["scheduled_at"] is None
    evidence["gaps"].append("Native backend recreates a deleted draft after its idempotency cache expires. Keep the persistent source-ID journal; never blindly recreate a missing saved draft.")
    evidence["status"] = "component_checks_passed_with_documented_native_replay_limit"
finally:
    if auth_session:
        auth_session.delete()
    if org:
        org_id = org.pk
        org.delete()
        assert not Organization.objects.filter(pk=org_id).exists()
    if user:
        user_id = user.pk
        user.delete()
        assert not get_user_model().objects.filter(pk=user_id).exists()
    Organization.objects.filter(id__in=auto_org_ids).delete()
    api.close()
    native.close()
    evidence["cleanup"] = "Disposable user, session, organizations, workspace, account, key, posts and replay records removed."
    print(json.dumps(evidence, indent=2))
