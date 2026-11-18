"""Run with manage.py shell, with operator.env supplied to the container."""
import os

from django.contrib.auth import get_user_model
from django.utils import timezone
from allauth.account.models import EmailAddress
from apps.organizations.models import Organization
from apps.workspaces.models import Workspace
from apps.members.models import OrgMembership, WorkspaceMembership

email = os.environ["DJANGO_SUPERUSER_EMAIL"]
User = get_user_model()
user = User.objects.filter(email=email).first()
if not user:
    user = User.objects.create_superuser(email, os.environ["DJANGO_SUPERUSER_PASSWORD"], name="Cosimo operator")
EmailAddress.objects.get_or_create(user=user, email=email, defaults={"verified": True, "primary": True})
org = Organization.objects.filter(name="Cosimo").first()
if org is None:
    # User creation already provisions a default org/workspace; reuse it.
    org = Organization.objects.get(memberships__user=user, name="My Organization")
    org.name = "Cosimo"
    org.default_timezone = "America/New_York"
    org.save(update_fields=["name", "default_timezone"])
    workspace = org.workspaces.get(name="My Workspace")
    workspace.name = "Publishing"
    workspace.timezone = "America/New_York"
    workspace.save(update_fields=["name", "timezone"])
else:
    workspace, _ = Workspace.objects.get_or_create(
        organization=org, name="Publishing", defaults={"timezone": "America/New_York"}
    )
OrgMembership.objects.get_or_create(user=user, organization=org, defaults={"org_role": "owner", "accepted_at": timezone.now()})
WorkspaceMembership.objects.get_or_create(user=user, workspace=workspace, defaults={"workspace_role": "owner"})
user.last_workspace_id = workspace.id
user.save(update_fields=["last_workspace_id"])
print(f"Workspace ready: http://localhost:4010/workspace/{workspace.id}/calendar/")
