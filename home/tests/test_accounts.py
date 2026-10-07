from datetime import timedelta
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.contrib.auth.tokens import default_token_generator
from django.core import mail, signing
from django.test import Client, TestCase, override_settings
from django.urls import reverse
from django.utils import timezone
from django.utils.encoding import force_bytes
from django.utils.http import urlsafe_base64_encode

from ..account_views import CONFIRMATION_SALT
from ..models import Collaborator


@override_settings(EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend")
class AccountTests(TestCase):
    def register(self, **extra):
        data = dict(public_name="Pessoa", email="Pessoa@Example.com", password1="safe-password-123", password2="safe-password-123", contact_preference="none")
        data.update(extra)
        return self.client.post(reverse("register"), data)

    def account(self, *, confirmed=True, blocked=False):
        user = get_user_model().objects.create_user(username="internal", email="person@example.com", password="safe-password-123", is_active=confirmed)
        collaborator = Collaborator.objects.create(user=user, email=user.email, public_name="Pessoa", is_blocked=blocked, email_confirmed_at=timezone.now() if confirmed else None)
        return user, collaborator

    def token_url(self, collaborator):
        token = signing.dumps({"collaborator_id": collaborator.pk, "email": collaborator.email}, salt=CONFIRMATION_SALT)
        return reverse("confirm_email", args=[token])

    def test_registration_normalizes_email_and_waits_for_confirmation(self):
        self.register()
        collaborator = Collaborator.objects.select_related("user").get()
        self.assertEqual(collaborator.email, "pessoa@example.com")
        self.assertFalse(collaborator.user.is_active)
        self.assertIsNone(collaborator.email_confirmed_at)
        self.assertEqual(len(mail.outbox), 1)
        self.assertTrue(collaborator.user.check_password("safe-password-123"))

    def test_duplicate_registration_creates_no_second_account(self):
        self.register()
        self.register(email="PESSOA@example.com")
        self.assertEqual(Collaborator.objects.count(), 1)
        self.assertEqual(get_user_model().objects.count(), 1)

    def test_invalid_password_and_contact_do_not_create_account(self):
        response = self.register(password2="different", contact_preference="whatsapp", contact_authorized=True)
        self.assertIn("password2", response.context["form"].errors)
        self.assertIn("whatsapp", response.context["form"].errors)
        self.assertFalse(Collaborator.objects.exists())

    @patch("home.account_views.send_mail", side_effect=OSError("SMTP unavailable"))
    def test_failed_email_preserves_pending_registration(self, send):
        with self.assertLogs("home.account_views", level="ERROR"):
            self.register()
        self.assertFalse(Collaborator.objects.get().user.is_active)

    def test_confirmation_requires_post(self):
        user, collaborator = self.account(confirmed=False)
        url = self.token_url(collaborator)
        self.client.get(url)
        user.refresh_from_db()
        self.assertFalse(user.is_active)
        self.client.post(url)
        user.refresh_from_db()
        collaborator.refresh_from_db()
        self.assertTrue(user.is_active)
        self.assertIsNotNone(collaborator.email_confirmed_at)

    def test_reused_confirmation_does_not_reactivate_disabled_account(self):
        user, collaborator = self.account()
        user.is_active = False
        user.save()
        self.client.post(self.token_url(collaborator))
        user.refresh_from_db()
        self.assertFalse(user.is_active)

    def test_invalid_and_expired_confirmation_do_not_activate(self):
        user, collaborator = self.account(confirmed=False)
        self.client.post(reverse("confirm_email", args=["invalid"]))
        with patch("django.core.signing.time.time", return_value=(timezone.now()-timedelta(days=2)).timestamp()):
            expired = self.token_url(collaborator)
        self.client.post(expired)
        user.refresh_from_db()
        self.assertFalse(user.is_active)

    def test_blocked_confirmation_does_not_activate(self):
        user, collaborator = self.account(confirmed=False, blocked=True)
        self.client.post(self.token_url(collaborator))
        user.refresh_from_db()
        self.assertFalse(user.is_active)

    def test_resend_has_five_minute_interval(self):
        user, collaborator = self.account(confirmed=False)
        url = reverse("resend_confirmation")
        self.client.post(url, {"email": user.email})
        self.client.post(url, {"email": user.email})
        self.assertEqual(len(mail.outbox), 1)
        Collaborator.objects.filter(pk=collaborator.pk).update(confirmation_sent_at=timezone.now()-timedelta(minutes=6))
        self.client.post(url, {"email": user.email})
        self.assertEqual(len(mail.outbox), 2)

    def test_login_uses_email(self):
        user, collaborator = self.account()
        self.client.post(reverse("login"), {"username": "PERSON@example.com", "password": "safe-password-123"})
        self.assertEqual(int(self.client.session["_auth_user_id"]), user.pk)

    def test_confirmation_hint_requires_correct_password(self):
        user, collaborator = self.account(confirmed=False)
        for password, expected in (("wrong", False), ("safe-password-123", True)):
            response = self.client.post(reverse("login"), {"username": user.email, "password": password})
            self.assertEqual(response.context["form"].needs_email_confirmation, expected)
            self.assertNotIn("_auth_user_id", self.client.session)

    def test_blocked_login_is_rejected(self):
        user, collaborator = self.account(blocked=True)
        self.client.post(reverse("login"), {"username": user.email, "password": "safe-password-123"})
        self.assertNotIn("_auth_user_id", self.client.session)

    def test_password_reset_sends_only_to_enabled_account(self):
        user, collaborator = self.account()
        url = reverse("password_reset")
        self.client.post(url, {"email": user.email})
        self.assertEqual(len(mail.outbox), 1)
        collaborator.is_blocked = True
        collaborator.save()
        self.client.post(url, {"email": user.email})
        self.client.post(url, {"email": "unknown@example.com"})
        self.assertEqual(len(mail.outbox), 1)

    def test_password_reset_token_changes_password_and_cannot_be_reused(self):
        user, collaborator = self.account()
        token = default_token_generator.make_token(user)
        uid = urlsafe_base64_encode(force_bytes(user.pk))
        response = self.client.get(reverse("password_reset_confirm", args=[uid, token]))
        self.assertEqual(response.status_code, 302)
        response = self.client.post(response.url, {"new_password1": "new-safe-password-456", "new_password2": "new-safe-password-456"})
        self.assertRedirects(response, reverse("password_reset_complete"))
        user.refresh_from_db()
        self.assertTrue(user.check_password("new-safe-password-456"))
        self.assertFalse(default_token_generator.check_token(user, token))

    def test_registration_and_confirmation_require_csrf(self):
        user, collaborator = self.account(confirmed=False)
        client = Client(enforce_csrf_checks=True)
        self.assertEqual(client.post(reverse("register"), {}).status_code, 403)
        self.assertEqual(client.post(self.token_url(collaborator)).status_code, 403)
