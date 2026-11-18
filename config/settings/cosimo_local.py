"""Cosimo's loopback-only installation; use production settings behind HTTPS remotely."""

from .production import *  # noqa: F401, F403

SECURE_SSL_REDIRECT = False
SECURE_HSTS_SECONDS = 0
SESSION_COOKIE_SECURE = False
CSRF_COOKIE_SECURE = False
SECURE_PROXY_SSL_HEADER = None
COSIMO_LOOPBACK_API = True
EMAIL_SENDING_ENABLED = False
INTELLIGENCE_ENABLED = False
