from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta
from tempfile import TemporaryDirectory
from unittest.mock import patch
from io import BytesIO

from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from django.core.management import call_command
from django.db import connections
from django.test import Client, TestCase, TransactionTestCase, override_settings
from django.urls import reverse
from django.utils import timezone
from pypdf import PdfWriter

from .helpers import ContributorFixtures, pdf_bytes
from ..forms.ideas import IdeaSubmissionForm
from ..forms.profile import ProfileForm
from ..idea_submission import DRAFT_KEY
from ..models import IdeaSubmission, IdeaDraft, PendingFileDeletion, Collaborator


class SecurityTests(ContributorFixtures, TestCase):
    def test_pdf_content_is_checked(self):
        for content in (b"HTML disguised as PDF", b"%PDF-1.4 broken"):
            form = IdeaSubmissionForm(self.payload(), {"idea_pdf": SimpleUploadedFile("fake.pdf", content)})
            self.assertFalse(form.is_valid())
            self.assertIn("idea_pdf", form.errors)

    def test_encrypted_pdf_is_rejected(self):
        stream = BytesIO()
        writer = PdfWriter(); writer.add_blank_page(width=200, height=200); writer.encrypt("secret"); writer.write(stream)
        form = IdeaSubmissionForm(self.payload(), {"idea_pdf": SimpleUploadedFile("locked.pdf", stream.getvalue())})
        self.assertFalse(form.is_valid())
        self.assertIn("idea_pdf", form.errors)

    def test_pending_pdf_checks_both_urls_and_permissions(self):
        with TemporaryDirectory() as directory, override_settings(MEDIA_ROOT=directory):
            idea = self.idea(idea_pdf=SimpleUploadedFile("test.pdf", pdf_bytes()))
            idea.is_approved = False; idea.save()
            urls = [reverse("idea_pdf", args=[idea.pk]), "/media/" + idea.idea_pdf.name]
            for url in urls:
                self.assertEqual(self.client.get(url).status_code, 404)
            self.client.force_login(self.other)
            self.assertEqual(self.client.get(urls[0]).status_code, 404)
            self.client.force_login(self.user)
            response = self.client.get(urls[0]); self.assertEqual(response.status_code, 200)
            idea.is_approved = True; idea.save()
            self.client.logout()
            response = self.client.get(urls[1]); self.assertEqual(response.status_code, 200)
            idea.is_active = False; idea.save()
            self.assertEqual(self.client.get(urls[1]).status_code, 404)

    def test_draft_contains_no_binary_in_session_and_expires(self):
        self.client.post(reverse("home"), self.payload(idea_pdf=SimpleUploadedFile("test.pdf", pdf_bytes())))
        stub = self.client.session[DRAFT_KEY]
        self.assertEqual(set(stub), {"id", "expires"})
        record = IdeaDraft.objects.get(pk=stub["id"])
        self.assertTrue(record.pdf.storage.exists(record.pdf.name))
        self.assertEqual(self.client.get("/media/" + record.pdf.name).status_code, 404)
        IdeaDraft.objects.filter(pk=record.pk).update(expires_at=timezone.now()-timedelta(seconds=1))
        with self.captureOnCommitCallbacks(execute=True):
            call_command("cleanup_uploads", stdout=__import__("io").StringIO())
        self.assertFalse(IdeaDraft.objects.exists())
        self.assertFalse(record.pdf.storage.exists(record.pdf.name))

    def test_duplicate_token_and_tampered_token(self):
        self.client.force_login(self.user)
        token = self.client.get(reverse("home")).context["submission_key"]
        data = self.payload(submission_key=token)
        self.client.post(reverse("home"), data)
        self.client.post(reverse("home"), data)
        self.assertEqual(IdeaSubmission.objects.count(), 1)
        self.client.post(reverse("home"), self.payload(submission_key="forged"))
        self.assertEqual(IdeaSubmission.objects.count(), 1)

    @override_settings(RATE_LIMITS={"login": (2, 300)})
    def test_rate_limit_with_retry_header(self):
        for _ in range(2):
            self.assertEqual(self.client.post(reverse("login"), {"username": "unknown@example.com", "password": "bad"}).status_code, 200)
        response = self.client.post(reverse("login"), {"username": "unknown@example.com", "password": "bad"}, HTTP_X_FORWARDED_FOR="8.8.8.8")
        self.assertEqual(response.status_code, 429)
        self.assertIn("Retry-After", response)

    @override_settings(RATE_LIMITS={"register": (1, 3600), "password_reset": (1, 3600), "home": (1, 3600)})
    def test_all_submission_limits(self):
        for name in ("register", "password_reset", "home"):
            self.assertNotEqual(self.client.post(reverse(name), {}).status_code, 429)
            self.assertEqual(self.client.post(reverse(name), {}).status_code, 429)

    def test_profile_does_not_overwrite_admin_block(self):
        self.client.force_login(self.user)
        original = ProfileForm.save
        def save(form, *args, **kwargs):
            result = original(form, *args, **kwargs)
            Collaborator.objects.filter(pk=self.author.pk).update(is_blocked=True, can_publish_directly=True)
            return result
        with patch.object(ProfileForm, "save", save):
            self.client.post(reverse("profile"), {"public_name": "Novo", "contact_preference": "none"})
        self.author.refresh_from_db()
        self.assertTrue(self.author.is_blocked)
        self.assertTrue(self.author.can_publish_directly)
        self.assertEqual(self.author.public_name, "Novo")

    def test_failed_file_deletion_is_retryable(self):
        with TemporaryDirectory() as directory, override_settings(MEDIA_ROOT=directory):
            idea = self.idea(idea_pdf=SimpleUploadedFile("test.pdf", pdf_bytes()))
            storage, name = idea.idea_pdf.storage, idea.idea_pdf.name
            with patch.object(storage, "delete", side_effect=OSError("offline")):
                with self.assertLogs("home.signals", level="ERROR"), self.captureOnCommitCallbacks(execute=True):
                    idea.delete()
            self.assertTrue(PendingFileDeletion.objects.filter(name=name).exists())
            call_command("cleanup_uploads", stdout=__import__("io").StringIO())
            self.assertFalse(storage.exists(name))
            self.assertFalse(PendingFileDeletion.objects.exists())


class ConcurrentSubmissionTests(TransactionTestCase):
    def test_same_token_in_parallel_creates_one_idea(self):
        user = get_user_model().objects.create_user(username="concurrent", password="safe-password-123")
        Collaborator.objects.create(user=user, public_name="Autor", email="concurrent@example.com", email_confirmed_at=timezone.now())
        client = Client(); client.force_login(user)
        token = client.get(reverse("home")).context["submission_key"]
        cookies = client.cookies.copy()
        def send(_):
            try:
                worker = Client(); worker.cookies = cookies.copy()
                return worker.post(reverse("home"), {"submission_key": token, "author_name": "Autor", "idea_title": "Única", "idea_github": "https://github.com/user/repo", "idea_consent": True}).status_code
            finally:
                connections.close_all()
        with ThreadPoolExecutor(max_workers=2) as pool:
            results = list(pool.map(send, range(2)))
        self.assertEqual(results, [302, 302])
        self.assertEqual(IdeaSubmission.objects.count(), 1)
