from tempfile import TemporaryDirectory

from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from ..models import Collaborator, Comment, CommentReport, IdeaSubmission
from ..idea_submission import DRAFT_KEY


from .helpers import ContributorFixtures


class IdeasTests(ContributorFixtures, TestCase):
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


    def test_csrf_required(self):
        from django.test import Client
        client = Client(enforce_csrf_checks=True)
        client.force_login(self.user)
        self.assertEqual(client.post(reverse("idea_remove", args=[self.idea().pk])).status_code, 403)

