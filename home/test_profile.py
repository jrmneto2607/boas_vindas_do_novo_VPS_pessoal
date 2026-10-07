from datetime import timedelta
from tempfile import TemporaryDirectory

from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from .models import Collaborator, Comment, CommentReport, IdeaSubmission
from .idea_submission import DRAFT_KEY


class ProfileAndIdeaTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.user = get_user_model().objects.create_user(username="owner", password="safe-password-123")
        cls.author = Collaborator.objects.create(user=cls.user, public_name="Autor", email="owner@example.com", email_confirmed_at=timezone.now())
        cls.other = get_user_model().objects.create_user(username="other")
        cls.other_author = Collaborator.objects.create(user=cls.other, public_name="Outro", email="other@example.com", email_confirmed_at=timezone.now())

    def payload(self, **extra):
        return dict(author_name="Nome público", idea_title="Nova ideia", idea_github="https://github.com/user/repo", idea_consent=True, **extra)

    def idea(self, **extra):
        return IdeaSubmission.objects.create(owner=self.user, author_name="Autor", idea_title="Minha ideia", **extra)

    def test_logged_submission_ignores_forged_owner(self):
        self.client.force_login(self.user)
        self.client.post(reverse("home"), self.payload(owner=self.other.pk))
        self.assertEqual(IdeaSubmission.objects.get().owner, self.user)

    def test_anonymous_must_choose_and_can_submit_without_account(self):
        response = self.client.post(reverse("home"), self.payload())
        self.assertContains(response, "Entrar e vincular")
        self.assertFalse(IdeaSubmission.objects.exists())
        self.client.post(reverse("home"), {"submission_choice": "anonymous"})
        self.assertIsNone(IdeaSubmission.objects.get().owner)
        self.assertNotIn(DRAFT_KEY, self.client.session)

    def test_pdf_and_fields_survive_login(self):
        with TemporaryDirectory() as directory, override_settings(MEDIA_ROOT=directory):
            pdf = SimpleUploadedFile("proposta.pdf", b"%PDF-1.4 test", content_type="application/pdf")
            self.client.post(reverse("home"), self.payload(idea_pdf=pdf))
            response = self.client.post(reverse("home"), {"submission_choice": "login"})
            self.assertIn(reverse("login"), response.url)
            self.client.force_login(self.user)
            response = self.client.get(reverse("home"))
            self.assertContains(response, "proposta.pdf")
            self.assertEqual(response.context["form"]["idea_title"].value(), "Nova ideia")
            self.client.post(reverse("home"), self.payload())
            idea = IdeaSubmission.objects.get()
            self.assertEqual(idea.owner, self.user)
            with idea.idea_pdf.open("rb") as saved:
                self.assertEqual(saved.read(), b"%PDF-1.4 test")

    def test_expired_draft_cannot_be_submitted(self):
        self.client.post(reverse("home"), self.payload())
        session = self.client.session
        draft = session[DRAFT_KEY]
        draft["expires"] = 0
        session[DRAFT_KEY] = draft
        session.save()
        self.client.post(reverse("home"), {"submission_choice": "anonymous"})
        self.assertFalse(IdeaSubmission.objects.exists())

    def test_profile_only_shows_own_records(self):
        mine = self.idea()
        IdeaSubmission.objects.create(owner=self.other, idea_title="Segredo de outro", author_name="Outro")
        self.client.force_login(self.user)
        response = self.client.get(reverse("profile"))
        self.assertContains(response, mine.idea_title)
        self.assertNotContains(response, "Segredo de outro")

    def test_owner_can_delete_only_uncommented_pending_idea(self):
        idea = self.idea()
        self.client.force_login(self.user)
        self.assertEqual(self.client.get(reverse("idea_remove", args=[idea.pk])).status_code, 405)
        self.client.post(reverse("idea_remove", args=[idea.pk]))
        self.assertFalse(IdeaSubmission.objects.filter(pk=idea.pk).exists())

    def test_all_comment_states_prevent_deletion(self):
        self.client.force_login(self.user)
        for status in Comment.Status.values:
            for removed in (None, timezone.now()):
                idea = self.idea()
                Comment.objects.create(idea=idea, author=self.other_author, message="Comentário", status=status, removed_at=removed)
                self.client.post(reverse("idea_remove", args=[idea.pk]))
                self.assertTrue(IdeaSubmission.objects.filter(pk=idea.pk).exists())

    def test_other_owner_and_changed_status_prevent_deletion(self):
        idea = self.idea(status=IdeaSubmission.Status.EM_DESENVOLVIMENTO)
        self.client.force_login(self.user)
        self.client.post(reverse("idea_remove", args=[idea.pk]))
        self.assertTrue(IdeaSubmission.objects.filter(pk=idea.pk).exists())
        self.client.force_login(self.other)
        self.assertEqual(self.client.post(reverse("idea_remove", args=[idea.pk])).status_code, 404)

    def test_blocked_user_cannot_send_or_delete(self):
        idea = self.idea()
        Collaborator.objects.filter(pk=self.author.pk).update(is_blocked=True)
        self.client.force_login(self.user)
        self.assertEqual(self.client.post(reverse("idea_remove", args=[idea.pk])).status_code, 403)
        response = self.client.post(reverse("home"), self.payload())
        self.assertContains(response, "não está habilitada")
        self.assertEqual(IdeaSubmission.objects.count(), 1)

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

    def test_csrf_required(self):
        from django.test import Client
        client = Client(enforce_csrf_checks=True)
        client.force_login(self.user)
        self.assertEqual(client.post(reverse("idea_remove", args=[self.idea().pk])).status_code, 403)

    def test_organizer_cards_and_permissions(self):
        from django.contrib.auth.models import Permission
        self.user.is_staff = True
        self.user.save()
        self.idea()
        self.client.force_login(self.user)
        response = self.client.get(reverse("admin:index"))
        self.assertNotContains(response, "Ideias em análise")
        self.user.user_permissions.add(Permission.objects.get(codename="view_ideasubmission"))
        response = self.client.get(reverse("admin:index"))
        self.assertContains(response, "Ideias em análise")
        self.assertEqual(response.context["organizer_cards"][0]["count"], 1)
        self.assertNotContains(response, "Denúncias pendentes")
        self.assertEqual(self.client.get(response.context["organizer_cards"][0]["url"]).status_code, 200)
