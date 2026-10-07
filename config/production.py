"""Configuração HTTPS de produção: DJANGO_SETTINGS_MODULE=config.production."""
import os
from .settings import *

DEBUG = False
SECURE_SSL_REDIRECT = True
SESSION_COOKIE_SECURE = True
CSRF_COOKIE_SECURE = True
SECURE_HSTS_SECONDS = int(os.environ.get("SECURE_HSTS_SECONDS", "3600"))
SECURE_HSTS_INCLUDE_SUBDOMAINS = False
SECURE_HSTS_PRELOAD = False
CSRF_TRUSTED_ORIGINS = [v.strip() for v in os.environ.get("CSRF_TRUSTED_ORIGINS", "").split(",") if v.strip()]
# Ativar apenas se o proxy confiável sobrescrever o cabeçalho recebido.
if os.environ.get("TRUST_PROXY_HTTPS", "false").lower() == "true":
    SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")
