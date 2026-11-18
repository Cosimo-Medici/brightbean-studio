"""Create private local configuration once. Never print credentials."""
import os
from pathlib import Path
import secrets

root = Path(__file__).resolve().parent / "private"
root.mkdir(mode=0o700, exist_ok=True)
os.chmod(root, 0o700)
if any(root.iterdir()):
    raise SystemExit("Private configuration already exists; leaving it unchanged.")

password = secrets.token_urlsafe(36)
values = {
    "database.env": f"POSTGRES_DB=brightbean\nPOSTGRES_USER=brightbean\nPOSTGRES_PASSWORD={password}\n",
    "runtime.env": "\n".join([
        "DJANGO_SETTINGS_MODULE=config.settings.cosimo_local",
        f"SECRET_KEY={secrets.token_urlsafe(64)}",
        f"ENCRYPTION_KEY_SALT={secrets.token_urlsafe(48)}",
        f"DATABASE_URL=postgres://brightbean:{password}@database:5432/brightbean",
        "DEBUG=false", "ALLOWED_HOSTS=localhost,127.0.0.1",
        "APP_URL=http://localhost:4010", "SIGNUP_MODE=closed",
        "STORAGE_BACKEND=local", "MEDIA_ROOT=/app/media",
        "EMAIL_SENDING_ENABLED=false", "INTELLIGENCE_ENABLED=false", "",
    ]),
    "operator.env": f"DJANGO_SUPERUSER_EMAIL=operator@localhost\nDJANGO_SUPERUSER_PASSWORD={secrets.token_urlsafe(32)}\n",
}
for name, value in values.items():
    with os.fdopen(os.open(root / name, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600), "w") as out:
        out.write(value)
print("Created private configuration (mode 0600). No credentials printed.")
