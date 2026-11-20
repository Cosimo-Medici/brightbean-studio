"""Real HTTP/PostgreSQL scheduling checks, with disposable future-only posts.

Run through manage.py shell in the web container. No provider calls, worker
invocation, actual-account mutations or end-to-end publication tests.
"""
import json
import uuid
from datetime import datetime, timedelta, time
from importlib import import_module
from zoneinfo import ZoneInfo

import requests
from django.conf import settings
from django.contrib.auth import get_user_model, SESSION_KEY, BACKEND_SESSION_KEY, HASH_SESSION_KEY
from django.db import connection
from django.utils import timezone
from apps.api_keys.services import issue_api_key
from apps.calendar.services import _next_slot_datetimes, create_default_queue_and_slots
from apps.composer.models import Post
from apps.members.models import OrgMembership, WorkspaceMembership
from apps.organizations.models import Organization
from apps.publisher.models import PublishLog
from apps.social_accounts.models import SocialAccount
from apps.workspaces.models import Workspace
from providers.linkedin_personal import LinkedInPersonalProvider
from providers.types import PublishContent

assert connection.vendor == "postgresql"
suffix = uuid.uuid4().hex
origin = "http://localhost:8000"
zone = ZoneInfo("America/New_York")
org = user = auth_session = None
auto_org_ids = []
api, native = requests.Session(), requests.Session()
checks = []
log_ids = set(PublishLog.objects.values_list("id", flat=True))


def call(method, route, expected=200, **kwargs):
    r = api.request(method, origin + "/api/v1" + route, timeout=20, **kwargs)
    assert r.status_code == expected, (route, r.status_code)
    return r.json()


try:
    user = get_user_model().objects.create_user(f"schedule-check-{suffix}@localhost")
    user.tos_accepted_at = timezone.now()  # Synthetic fixture only.
    user.save(update_fields=["tos_accepted_at"])
    auto_org_ids = list(user.org_memberships.values_list("organization_id", flat=True))
    org = Organization.objects.create(name=f"Disposable schedule check {suffix}")
    ws = Workspace.objects.create(organization=org, name="Disposable schedule check", timezone=str(zone))
    OrgMembership.objects.create(organization=org, user=user, org_role="owner")
    WorkspaceMembership.objects.create(workspace=ws, user=user, workspace_role="owner")
    account = SocialAccount(workspace=ws, platform="linkedin_personal", account_platform_id=suffix,
                            account_name="DISPOSABLE — NO PROVIDER TOKEN", connection_status="connected")
    account._skip_analytics_backfill = True
    account.save()
    create_default_queue_and_slots(account)  # Same initializer as the OAuth callback.
    assert list(account.posting_slots.values_list("day_of_week", "time")) == [(d, time(12, 15)) for d in range(5)]
    for baseline, offset in [(datetime(2027, 1, 4, 0, tzinfo=zone), -5), (datetime(2027, 7, 5, 0, tzinfo=zone), -4)]:
        slots = _next_slot_datetimes(account, baseline, count=5)
        assert len(slots) == 5 and all(s.hour == 12 and s.minute == 15 and s.utcoffset() == timedelta(hours=offset) for s in slots)
    checks.append("New-account weekday 12:15 defaults and actual slot calculation across winter/summer DST")
    key = issue_api_key(workspace=ws, social_accounts=[account], issued_by=user,
                       name="Disposable schedule", permissions=["create_posts", "publish_directly"])
    api.headers["Authorization"] = "Bearer " + key.plaintext_token
    auth_session = import_module(settings.SESSION_ENGINE).SessionStore()
    auth_session[SESSION_KEY] = str(user.pk)
    auth_session[BACKEND_SESSION_KEY] = "django.contrib.auth.backends.ModelBackend"
    auth_session[HASH_SESSION_KEY] = user.get_session_auth_hash()
    auth_session.save()
    native.cookies.set(settings.SESSION_COOKIE_NAME, auth_session.session_key)
    day = timezone.now().astimezone(zone).date() + timedelta(days=30)
    monday = day + timedelta(days=(-day.weekday()) % 7)
    ids = []
    for index, offset in enumerate([0, 2]):
        item = call("POST", "/posts/", expected=201, json={"social_account_id": str(account.id),
                    "caption": f"Disposable planned-day {index}.", "action": "draft", "idempotency_key": f"{suffix}-{index}"})
        ids.append(item["id"])
        editor_url = f"{origin}/workspace/{ws.id}/compose/{item['id']}/"
        assert native.get(editor_url, timeout=20, allow_redirects=False).status_code == 200
        data = {"caption": item["caption"], "title": "", "first_comment": "", "internal_notes": "",
                "tags": "", "category": "", "selected_accounts": str(account.id), "action": "schedule",
                "scheduled_date": (monday + timedelta(days=offset)).isoformat(), "scheduled_time": "12:15"}
        r = native.post(editor_url + "save/", data=data, headers={"X-CSRFToken": native.cookies.get(settings.CSRF_COOKIE_NAME),
                        "Referer": editor_url, "HX-Request": "true"}, timeout=20, allow_redirects=False)
        assert r.status_code == 204, ("native schedule", r.status_code, r.text[:200])
        post = Post.objects.get(pk=item["id"])
        pp = post.platform_posts.get()
        expected = datetime.combine(monday + timedelta(days=offset), time(12, 15), tzinfo=zone)
        assert post.status == pp.status == "scheduled" and post.scheduled_at == pp.scheduled_at == expected
        assert pp.published_at is None and not pp.platform_post_id
    checks.append("One batch creates distinct planned Monday/Wednesday native schedules at 12:15 Eastern")
    untouched = call("GET", f"/posts/{ids[1]}")
    moved_time = datetime.combine(monday + timedelta(days=4), time(12, 15), tzinfo=zone)
    moved = call("PATCH", f"/posts/{ids[0]}", json={"scheduled_at": moved_time.isoformat()})
    assert datetime.fromisoformat(moved["scheduled_at"]) == moved_time
    assert Post.objects.get(pk=ids[0]).platform_posts.get().scheduled_at == moved_time
    assert call("GET", f"/posts/{ids[1]}")["scheduled_at"] == untouched["scheduled_at"]
    checks.append("Reschedule moves one post and its platform child; sibling keeps its planned day")
    for id in ids:
        cancelled = call("POST", f"/posts/{id}/cancel")
        pp = Post.objects.get(pk=id).platform_posts.get()
        assert cancelled["status"] == pp.status == "draft" and cancelled["scheduled_at"] is None and pp.scheduled_at is None
        assert pp.published_at is None and not pp.platform_post_id
    checks.append("Withdrawal clears parent and child schedules without publication")
    # Request construction only, using the exact saved description of the live
    # approved image. This is not a LinkedIn acceptance claim.
    real_post = Post.objects.get(pk="ab28de8a-fbe8-477c-bafa-ce822ff77987")
    attachment = real_post.media_attachments.select_related("media_asset").get()
    alt = attachment.alt_text or attachment.media_asset.alt_text
    assert alt
    content = PublishContent(text=real_post.caption, media_alt_texts=[alt])
    provider = LinkedInPersonalProvider({})
    body = provider._build_image_post_body("urn:li:person:request-construction-only", content, "urn:li:image:request-construction-only")
    assert body["content"]["media"]["altText"] == alt
    assert "altText" not in provider._build_image_post_body("author", PublishContent(), "image")["content"]["media"]
    checks.append("LinkedIn request preserves saved image description; empty descriptions omitted (no provider call)")
finally:
    if auth_session:
        auth_session.delete()
    if org:
        org_id = org.pk
        org.delete()
        assert not Organization.objects.filter(pk=org_id).exists()
    if user:
        user.delete()
    Organization.objects.filter(id__in=auto_org_ids).delete()
    api.close()
    native.close()
    assert set(PublishLog.objects.values_list("id", flat=True)) == log_ids
print(json.dumps({"status": "passed", "checks": checks, "cleanup": "complete", "platformCalls": 0}, indent=2))
