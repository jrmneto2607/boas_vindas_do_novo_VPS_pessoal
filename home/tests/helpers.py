"""Dados fictícios compartilhados; estes helpers não alteram o banco real."""
from django.contrib.auth import get_user_model
from django.utils import timezone
from ..models import Collaborator, IdeaSubmission


class ContributorFixtures:
    def setUp(self):
        from tempfile import TemporaryDirectory
        from django.test import override_settings
        directory = TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        override = override_settings(PRIVATE_UPLOAD_ROOT=directory.name)
        override.enable()
        self.addCleanup(override.disable)

    @classmethod
    def setUpTestData(cls):
        cls.user = get_user_model().objects.create_user(username="owner", password="safe-password-123")
        cls.author = Collaborator.objects.create(user=cls.user, public_name="Autor", email="owner@example.com", email_confirmed_at=timezone.now())
        cls.other = get_user_model().objects.create_user(username="other")
        cls.other_author = Collaborator.objects.create(user=cls.other, public_name="Outro", email="other@example.com", email_confirmed_at=timezone.now())


    def payload(self, **extra):
        return dict(author_name="Nome público", idea_title="Nova ideia", idea_github="https://github.com/user/repo", idea_consent=True, **extra)


    def idea(self, **extra):
        return IdeaSubmission.objects.create(is_approved=True, owner=self.user, author_name="Autor", idea_title="Minha ideia", **extra)



def pdf_bytes():
    from io import BytesIO
    from pypdf import PdfWriter
    stream = BytesIO()
    writer = PdfWriter()
    writer.add_blank_page(width=200, height=200)
    writer.write(stream)
    return stream.getvalue()
