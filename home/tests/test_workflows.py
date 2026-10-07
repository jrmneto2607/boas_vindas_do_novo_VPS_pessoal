from tempfile import TemporaryDirectory
from django.core.files.uploadedfile import SimpleUploadedFile
from django.core.exceptions import PermissionDenied, ValidationError
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone
from django.core import signing
from .helpers import ContributorFixtures
from ..models import IdeaSubmission, Collaborator, Comment, CommentReport
from ..moderation_services import dismiss_report
from ..account_views import CONFIRMATION_SALT
from ..idea_submission import DRAFT_KEY


@override_settings(EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend")
class WorkflowTests(ContributorFixtures, TestCase):
    def test_new_idea_waits_for_publication(self):
        self.client.force_login(self.user)
        self.client.post(reverse("home"), self.payload())
        idea = IdeaSubmission.objects.get()
        self.assertFalse(idea.is_approved)
        self.assertNotContains(self.client.get(reverse("idea_list")), idea.idea_title)
        self.assertEqual(self.client.get(reverse("idea_detail", args=[idea.pk])).status_code, 404)
        self.assertEqual(self.client.post(reverse("comment_create", args=[idea.pk]), {"message": "Teste"}).status_code, 404)
        self.assertContains(self.client.get(reverse("profile")), "Aguardando aprovação")
        idea.is_approved = True
        idea.save()
        self.assertEqual(self.client.get(reverse("idea_detail", args=[idea.pk])).status_code, 200)

    def test_signup_confirmation_login_returns_to_draft(self):
        self.client.post(reverse("home"), self.payload())
        self.client.post(reverse("register"), {"public_name": "Nova pessoa", "email": "new@example.com", "password1": "safe-password-123", "password2": "safe-password-123", "contact_preference": "none"})
        collaborator = Collaborator.objects.get(email="new@example.com")
        token = signing.dumps({"collaborator_id": collaborator.pk, "email": collaborator.email}, salt=CONFIRMATION_SALT)
        response = self.client.post(reverse("confirm_email", args=[token]))
        self.assertIn("next=", response.url)
        self.client.post(response.url, {"username": collaborator.email, "password": "safe-password-123", "next": reverse("home") + "#enviar-ideia"})
        self.assertContains(self.client.get(reverse("home")), "Nova ideia")
        self.client.post(reverse("home"), self.payload())
        self.assertEqual(IdeaSubmission.objects.get().owner, collaborator.user)
        self.assertNotIn(DRAFT_KEY, self.client.session)

    def test_pdf_removed_after_commit(self):
        with TemporaryDirectory() as directory, override_settings(MEDIA_ROOT=directory):
            idea = self.idea(idea_pdf=SimpleUploadedFile("test.pdf", b"%PDF-1.4"))
            storage, name = idea.idea_pdf.storage, idea.idea_pdf.name
            with self.captureOnCommitCallbacks(execute=True):
                idea.delete()
                self.assertTrue(storage.exists(name))
            self.assertFalse(storage.exists(name))

    def test_report_dismissal(self):
        comment = Comment.objects.create(idea=self.idea(), author=self.author, message="Texto", status=Comment.Status.REPORTED)
        report = CommentReport.objects.create(comment=comment, reporter=self.other_author, reason="spam")
        with self.assertRaises(PermissionDenied):
            dismiss_report(user=self.other, report_id=report.pk, note="Sem permissão")
        self.user.is_staff = self.user.is_superuser = True
        self.user.save()
        with self.assertRaises(ValidationError):
            dismiss_report(user=self.user, report_id=report.pk, note=" ")
        self.client.force_login(self.user)
        url = reverse("admin:home_commentreport_dismiss", args=[report.pk])
        self.assertEqual(self.client.get(url).status_code, 200)
        self.assertEqual(self.client.post(url, {"note": "Não há spam"}).status_code, 302)
        report.refresh_from_db(); comment.refresh_from_db()
        self.assertTrue(report.dismissed)
        self.assertEqual(report.review_note, "Não há spam")
        self.assertEqual(comment.status, Comment.Status.PUBLISHED)

    def test_timezone(self):
        from datetime import datetime, timezone as tz
        self.assertEqual(timezone.localtime(datetime(2026, 10, 7, 15, tzinfo=tz.utc)).hour, 12)
