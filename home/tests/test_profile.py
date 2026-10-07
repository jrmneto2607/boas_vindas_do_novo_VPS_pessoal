from tempfile import TemporaryDirectory

from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from ..models import Collaborator, Comment, CommentReport, IdeaSubmission
from ..idea_submission import DRAFT_KEY


from .helpers import ContributorFixtures


class ProfileTests(ContributorFixtures, TestCase):
    def test_profile_only_shows_own_records(self):
        mine = self.idea()
        IdeaSubmission.objects.create(is_approved=True, owner=self.other, idea_title="Segredo de outro", author_name="Outro")
        self.client.force_login(self.user)
        response = self.client.get(reverse("profile"))
        self.assertContains(response, mine.idea_title)
        self.assertNotContains(response, "Segredo de outro")


    def test_profile_contact_validation_and_consent(self):
        self.client.force_login(self.user)
        url = reverse("profile")
        response = self.client.post(url, {"public_name": "Novo", "contact_preference": "whatsapp", "contact_authorized": True})
        self.assertFormError(response.context["form"], "whatsapp", "Informe o WhatsApp para escolher esse canal.")
        self.client.post(url, {"public_name": "Novo", "contact_preference": "email", "contact_authorized": True})
        self.author.refresh_from_db()
        self.assertEqual(self.author.public_name, "Novo")
        self.assertIsNotNone(self.author.contact_consent_at)
        self.client.post(url, {"public_name": "Novo", "contact_preference": "none"})
        self.author.refresh_from_db()
        self.assertFalse(self.author.contact_authorized)
        self.assertIsNone(self.author.contact_consent_at)


    def test_password_change_keeps_session(self):
        self.client.force_login(self.user)
        response = self.client.post(reverse("password_change"), {"old_password": "safe-password-123", "new_password1": "another-safe-password-456", "new_password2": "another-safe-password-456"})
        self.assertRedirects(response, reverse("profile"))
        self.user.refresh_from_db()
        self.assertTrue(self.user.check_password("another-safe-password-456"))

