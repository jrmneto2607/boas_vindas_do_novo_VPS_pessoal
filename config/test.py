from .settings import *
# Invoke explicitly for tests; production settings are never changed.
EMAIL_BACKEND = "django.core.mail.backends.locmem.EmailBackend"
