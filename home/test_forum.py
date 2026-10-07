from datetime import timedelta

from django.contrib.auth import get_user_model
from django.core.exceptions import PermissionDenied, ValidationError
from django.test import Client, TestCase
from django.urls import reverse
from django.utils import timezone

from .forms.forum import CommentForm
from .forum_services import create_comment
from .models import Collaborator, Comment, IdeaSubmission


class ForumSubmissionTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.user = get_user_model().objects.create_user(
            username="forum-test", password="test-password",
        )
        cls.author = Collaborator.objects.create(
            user=cls.user, public_name="Colaborador",
            email="forum@example.com", email_confirmed_at=timezone.now(),
        )
        cls.other_user = get_user_model().objects.create_user(username="other")
        cls.other_author = Collaborator.objects.create(
            user=cls.other_user, public_name="Outro",
            email="other@example.com", email_confirmed_at=timezone.now(),
        )
        cls.idea = IdeaSubmission.objects.create(
            author_name="Autor", idea_title="Ideia de teste",
        )
        cls.other_idea = IdeaSubmission.objects.create(
            author_name="Autor", idea_title="Outra ideia",
        )

    def setUp(self):
        self.client.force_login(self.user)
        self.url = reverse("comment_create", args=[self.idea.pk])

    def send(self, **extra):
        data = {"message": "Minha contribuição"}
        data.update(extra)
        return self.client.post(self.url, data)

    def parent(self, **extra):
        data = {
            "idea": self.idea, "author": self.other_author,
            "message": "Comentário principal", "status": Comment.Status.PUBLISHED,
        }
        data.update(extra)
        return Comment.objects.create(**data)

    def test_submission_is_pending_and_sanitized(self):
        response = self.send(
            message='<p onclick="alert(1)">Texto</p><script>alert(1)</script>',
            author_id=self.other_author.pk, status="published",
            idea_id=self.other_idea.pk,
        )
        self.assertRedirects(response, reverse("idea_detail", args=[self.idea.pk]) + "#forum-form", fetch_redirect_response=False)
        comment = Comment.objects.get()
        self.assertEqual(comment.status, Comment.Status.PENDING)
        self.assertEqual(comment.author_id, self.author.pk)
        self.assertEqual(comment.idea_id, self.idea.pk)
        self.assertEqual(comment.message, "<p>Texto</p>")
        response = self.client.get(response.url)
        self.assertContains(response, "Sua contribuição foi enviada.")

    def test_direct_publication(self):
        Collaborator.objects.filter(pk=self.author.pk).update(can_publish_directly=True)
        self.assertEqual(self.send().status_code, 302)
        self.assertEqual(Comment.objects.get().status, Comment.Status.PUBLISHED)

    def test_invalid_message_preserves_form_and_creates_nothing(self):
        response = self.send(message="<p><br></p>", github_url="https://github.com/user/repo")
        self.assertEqual(response.status_code, 400)
        self.assertContains(response, "Escreva uma mensagem", status_code=400)
        self.assertEqual(response.context["comment_form"].data["github_url"], "https://github.com/user/repo")
        self.assertFalse(Comment.objects.exists())

    def test_anonymous_cannot_submit(self):
        self.client.logout()
        self.assertEqual(self.send().status_code, 302)
        self.assertFalse(Comment.objects.exists())

    def test_post_only(self):
        self.assertEqual(self.client.get(self.url).status_code, 405)
        self.assertFalse(Comment.objects.exists())

    def test_csrf_is_required(self):
        client = Client(enforce_csrf_checks=True)
        client.force_login(self.user)
        self.assertEqual(client.post(self.url, {"message": "Texto"}).status_code, 403)
        response = client.get(reverse("idea_detail", args=[self.idea.pk]))
        self.assertEqual(response.status_code, 200)
        response = client.post(self.url, {
            "message": "Texto", "csrfmiddlewaretoken": client.cookies["csrftoken"].value,
        })
        self.assertEqual(response.status_code, 302)

    def test_blocked_account(self):
        Collaborator.objects.filter(pk=self.author.pk).update(is_blocked=True)
        self.assertEqual(self.send().status_code, 403)
        self.assertFalse(Comment.objects.exists())

    def test_unconfirmed_account(self):
        Collaborator.objects.filter(pk=self.author.pk).update(email_confirmed_at=None)
        self.assertEqual(self.send().status_code, 403)
        self.assertFalse(Comment.objects.exists())

    def test_account_without_collaborator(self):
        user = get_user_model().objects.create_user(username="no-profile")
        self.client.force_login(user)
        self.assertEqual(self.send().status_code, 403)
        self.assertFalse(Comment.objects.exists())

    def test_inactive_account_is_checked_again_in_service(self):
        get_user_model().objects.filter(pk=self.user.pk).update(is_active=False)
        with self.assertRaises(PermissionDenied):
            create_comment(user=self.user, idea_id=self.idea.pk, cleaned_data={
                "message": "Texto", "github_url": "",
            })
        self.assertFalse(Comment.objects.exists())

    def test_reply_to_published_root(self):
        parent = self.parent()
        self.assertEqual(self.send(parent_id=parent.pk).status_code, 302)
        reply = Comment.objects.exclude(pk=parent.pk).get()
        self.assertEqual(reply.parent_id, parent.pk)
        self.assertEqual(reply.status, Comment.Status.PENDING)

    def test_reply_rejects_wrong_idea(self):
        parent = self.parent(idea=self.other_idea)
        self.assertEqual(self.send(parent_id=parent.pk).status_code, 400)
        self.assertEqual(Comment.objects.count(), 1)

    def test_reply_rejects_unavailable_parent(self):
        for status in (Comment.Status.PENDING, Comment.Status.REPORTED, Comment.Status.DISABLED):
            with self.subTest(status=status):
                parent = self.parent(status=status)
                self.assertEqual(self.send(parent_id=parent.pk).status_code, 400)
        parent = self.parent(removed_at=timezone.now())
        self.assertEqual(self.send(parent_id=parent.pk).status_code, 400)
        self.assertFalse(Comment.objects.filter(author=self.author).exists())

    def test_reply_rejects_nested_and_missing_parent(self):
        root = self.parent()
        reply = self.parent(parent=root)
        self.assertEqual(self.send(parent_id=reply.pk).status_code, 400)
        self.assertEqual(self.send(parent_id=999999).status_code, 400)
        self.assertEqual(self.send(parent_id="invalid").status_code, 400)
        self.assertFalse(Comment.objects.filter(author=self.author).exists())

    def test_cooldown_counts_removed_comments_in_other_ideas(self):
        self.parent(author=self.author, idea=self.other_idea, removed_at=timezone.now())
        response = self.send()
        self.assertContains(response, "Aguarde 30 segundos", status_code=400)
        self.assertEqual(Comment.objects.count(), 1)

    def test_hourly_limit(self):
        for _ in range(20):
            self.parent(author=self.author, idea=self.other_idea)
        Comment.objects.filter(author=self.author).update(
            created_at=timezone.now() - timedelta(minutes=2),
        )
        self.assertContains(self.send(), "20 contribuições por hora", status_code=400)
        self.assertEqual(Comment.objects.count(), 20)

    def test_expired_limits_allow_submission(self):
        comment = self.parent(author=self.author)
        Comment.objects.filter(pk=comment.pk).update(
            created_at=timezone.now() - timedelta(hours=2),
        )
        self.assertEqual(self.send().status_code, 302)
        self.assertEqual(Comment.objects.count(), 2)

    def test_unknown_idea(self):
        self.url = reverse("comment_create", args=[999999])
        self.assertEqual(self.send().status_code, 404)
        self.assertFalse(Comment.objects.exists())

    def test_public_page_does_not_show_form_or_private_contacts(self):
        self.client.logout()
        response = self.client.get(reverse("idea_detail", args=[self.idea.pk]))
        self.assertContains(response, "Entrar para participar")
        self.assertNotContains(response, 'name="message"')
        self.assertNotContains(response, self.author.email)

    def test_parent_id_is_optional_and_positive(self):
        self.assertTrue(CommentForm({"message": "Texto"}).is_valid())
        for parent_id in (0, -1, "invalid"):
            self.assertFalse(CommentForm({"message": "Texto", "parent_id": parent_id}).is_valid())

    def test_model_validation_rolls_back_invalid_service_data(self):
        with self.assertRaises(ValidationError):
            create_comment(user=self.user, idea_id=self.idea.pk, cleaned_data={
                "message": "Texto", "github_url": "endereço inválido",
            })
        self.assertFalse(Comment.objects.exists())

    def test_public_visibility_hides_unpublished_and_private_contacts(self):
        self.parent(message="Texto público")
        for status in (Comment.Status.PENDING, Comment.Status.REPORTED, Comment.Status.DISABLED):
            self.parent(author=self.author, message="Privado " + status, status=status)
        self.client.logout()
        response = self.client.get(reverse("idea_detail", args=[self.idea.pk]))
        self.assertContains(response, "Texto público")
        for status in (Comment.Status.PENDING, Comment.Status.REPORTED, Comment.Status.DISABLED):
            self.assertNotContains(response, "Privado " + status)
        self.assertNotContains(response, self.author.email)
        self.assertNotContains(response, self.other_author.email)
        self.assertNotContains(response, "forum-editor.js")

    def test_author_sees_own_moderated_comments_and_rejection_only(self):
        self.parent(author=self.author, message="Meu pendente", status=Comment.Status.PENDING)
        self.parent(author=self.author, message="Meu denunciado", status=Comment.Status.REPORTED)
        self.parent(author=self.author, message="Meu desativado", status=Comment.Status.DISABLED)
        self.parent(message="Pendente alheio", status=Comment.Status.PENDING)
        response = self.client.get(reverse("idea_detail", args=[self.idea.pk]))
        self.assertContains(response, "Meu pendente")
        self.assertNotContains(response, "Aguardando aprovação")
        self.assertContains(response, "Meu denunciado")
        self.assertNotContains(response, "Oculto por denúncias")
        self.assertContains(response, "Sua contribuição não foi aprovada.")
        self.assertContains(response, "Meu desativado")
        self.assertNotContains(response, "Pendente alheio")

    def test_removed_root_preserves_replies_without_content_or_identity(self):
        root = self.parent(message="Conteúdo removido secreto", removed_at=timezone.now(), github_url="https://github.com/secret/repo")
        self.parent(parent=root, author=self.author, message="Resposta preservada")
        self.client.logout()
        response = self.client.get(reverse("idea_detail", args=[self.idea.pk]))
        self.assertContains(response, "Comentário removido pelo autor.")
        self.assertContains(response, "Resposta preservada")
        self.assertNotContains(response, "Conteúdo removido secreto")
        self.assertNotContains(response, "https://github.com/secret/repo")
        self.assertNotContains(response, self.other_author.public_name)

    def test_removed_reply_and_empty_removed_root_are_hidden(self):
        self.parent(message="Raiz removida vazia", removed_at=timezone.now())
        root = self.parent(message="Raiz pública")
        self.parent(parent=root, message="Resposta removida", removed_at=timezone.now())
        self.client.logout()
        response = self.client.get(reverse("idea_detail", args=[self.idea.pk]))
        self.assertContains(response, "Raiz pública")
        self.assertNotContains(response, "Raiz removida vazia")
        self.assertNotContains(response, "Resposta removida")
        self.assertNotContains(response, "Comentário removido pelo autor.")

    def test_hidden_parent_hides_thread(self):
        for status in (Comment.Status.PENDING, Comment.Status.REPORTED, Comment.Status.DISABLED):
            root = self.parent(status=status, message="Raiz " + status)
            self.parent(parent=root, message="Resposta " + status)
        response = self.client.get(reverse("idea_detail", args=[self.idea.pk]))
        for status in (Comment.Status.PENDING, Comment.Status.REPORTED, Comment.Status.DISABLED):
            self.assertNotContains(response, "Raiz " + status)
            self.assertNotContains(response, "Resposta " + status)

    def test_pending_reply_visible_only_to_its_author(self):
        root = self.parent()
        self.parent(parent=root, author=self.author, message="Minha resposta pendente", status=Comment.Status.PENDING)
        response = self.client.get(reverse("idea_detail", args=[self.idea.pk]))
        self.assertContains(response, "Minha resposta pendente")
        self.client.logout()
        response = self.client.get(reverse("idea_detail", args=[self.idea.pk]))
        self.assertNotContains(response, "Minha resposta pendente")

    def test_legacy_html_is_sanitized_when_read(self):
        self.parent(message='<p onclick="alert(1)"><u>Texto</u><s>riscado</s></p><script>alert(1)</script>', github_url="javascript:alert(1)")
        response = self.client.get(reverse("idea_detail", args=[self.idea.pk]))
        self.assertContains(response, "<u>Texto</u><s>riscado</s>", html=False)
        self.assertNotContains(response, "onclick=")
        self.assertNotContains(response, "javascript:alert")
        self.assertNotContains(response, "<script>alert")

    def test_pagination_counts_only_visible_roots(self):
        for number in range(12):
            self.parent(message=f"Público {number}")
        for _ in range(3):
            self.parent(status=Comment.Status.PENDING)
        self.client.logout()
        url = reverse("idea_detail", args=[self.idea.pk])
        response = self.client.get(url)
        page = response.context["forum_page"]
        self.assertEqual(page.paginator.count, 12)
        self.assertEqual(len(page.object_list), 10)
        self.assertEqual(page.object_list[0]["message_html"], "Público 11")
        response = self.client.get(url, {"page": 2})
        self.assertEqual(len(response.context["forum_page"].object_list), 2)
        self.assertContains(response, "Anterior")

    def test_reply_selector_sets_form_and_cancel_link(self):
        root = self.parent()
        url = reverse("idea_detail", args=[self.idea.pk])
        response = self.client.get(url, {"responder": root.pk})
        self.assertEqual(response.context["comment_form"]["parent_id"].value(), root.pk)
        self.assertContains(response, "Respondendo a Outro")
        self.assertContains(response, "Cancelar resposta")
        self.assertContains(response, "forum-editor.js")

    def test_reply_selector_rejects_unavailable_and_invalid_ids(self):
        root = self.parent(status=Comment.Status.PENDING)
        other_root = self.parent(idea=self.other_idea)
        url = reverse("idea_detail", args=[self.idea.pk])
        for value in (root.pk, other_root.pk, "invalid", -1, 2**64):
            self.assertEqual(self.client.get(url, {"responder": value}).status_code, 404)
        self.assertEqual(self.send(parent_id=2**64).status_code, 400)

    def test_editor_seed_is_sanitized_after_invalid_submission(self):
        response = self.send(message='<p><strong>Preservar</strong></p><script>alert(1)</script>', github_url="https://example.com")
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.context["editor_initial"], "<p><strong>Preservar</strong></p>")
        self.assertContains(response, 'id="forum-editor-initial"', status_code=400)

    def test_new_editor_formats_survive_submission(self):
        source = '<p><u>Sublinhado</u><s>Riscado</s><span style="color:red;position:fixed">Cor</span></p><blockquote>Citação</blockquote><ol><li>Primeiro</li></ol>'
        self.assertEqual(self.send(message=source).status_code, 302)
        comment = Comment.objects.get()
        self.assertIn('<u>Sublinhado</u>', comment.message)
        self.assertIn('<s>Riscado</s>', comment.message)
        self.assertIn('color:red', comment.message)
        self.assertIn('<blockquote>Citação</blockquote>', comment.message)
        self.assertNotIn('position', comment.message)

    def test_quill_color_on_bold_text_survives_sanitization(self):
        source = '<p><strong style="color:rgb(94,234,212);position:fixed">Colorido</strong></p>'
        self.assertEqual(self.send(message=source).status_code, 302)
        comment = Comment.objects.get()
        self.assertIn('<strong style="color:', comment.message)
        self.assertNotIn('position', comment.message)
        response = self.client.get(reverse("idea_detail", args=[self.idea.pk]))
        self.assertContains(response, '<strong style="color:', html=False)

    def test_confirmation_is_identical_for_pending_and_direct_publication(self):
        response = self.send()
        pending_notice = list(self.client.get(response.url).context["messages"])
        Comment.objects.filter(author=self.author).update(created_at=timezone.now() - timedelta(minutes=2))
        Collaborator.objects.filter(pk=self.author.pk).update(can_publish_directly=True)
        response = self.send(message="Outra contribuição")
        published_notice = list(self.client.get(response.url).context["messages"])
        self.assertEqual(str(pending_notice[0]), "Sua contribuição foi enviada.")
        self.assertEqual(str(pending_notice[0]), str(published_notice[0]))

    def test_author_can_reply_to_own_pending_comment_privately(self):
        root = self.parent(author=self.author, status=Comment.Status.PENDING)
        Comment.objects.filter(pk=root.pk).update(created_at=timezone.now() - timedelta(minutes=2))
        response = self.client.get(reverse("idea_detail", args=[self.idea.pk]), {"responder": root.pk})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(self.send(parent_id=root.pk).status_code, 302)
        reply = Comment.objects.exclude(pk=root.pk).get()
        self.assertEqual(reply.status, Comment.Status.PENDING)
        response = self.client.get(reverse("idea_detail", args=[self.idea.pk]))
        self.assertContains(response, "Minha contribuição")
        self.assertNotContains(response, "Aguardando aprovação")
        self.client.logout()
        self.assertNotContains(self.client.get(reverse("idea_detail", args=[self.idea.pk])), "Minha contribuição")

    def test_direct_author_reply_to_pending_root_still_requires_review(self):
        root = self.parent(author=self.author, status=Comment.Status.PENDING)
        Comment.objects.filter(pk=root.pk).update(created_at=timezone.now() - timedelta(minutes=2))
        Collaborator.objects.filter(pk=self.author.pk).update(can_publish_directly=True)
        self.assertEqual(self.send(parent_id=root.pk).status_code, 302)
        self.assertEqual(Comment.objects.exclude(pk=root.pk).get().status, Comment.Status.PENDING)

    def test_rejection_of_reply_visible_only_to_author(self):
        root = self.parent()
        self.parent(parent=root, author=self.author, message="Resposta rejeitada", status=Comment.Status.DISABLED)
        url = reverse("idea_detail", args=[self.idea.pk])
        self.assertContains(self.client.get(url), "Sua contribuição não foi aprovada.")
        self.client.logout()
        response = self.client.get(url)
        self.assertNotContains(response, "Sua contribuição não foi aprovada.")
        self.assertNotContains(response, "Resposta rejeitada")

    def test_rejected_reply_in_hidden_thread_still_notifies_its_author(self):
        root = self.parent(status=Comment.Status.DISABLED, message="Conversa indisponível")
        self.parent(parent=root, author=self.author, message="Minha resposta rejeitada", status=Comment.Status.DISABLED)
        url = reverse("idea_detail", args=[self.idea.pk])
        response = self.client.get(url)
        self.assertContains(response, "Uma contribuição sua nesta ideia não foi aprovada.")
        self.assertNotContains(response, "Conversa indisponível")
        self.client.logout()
        self.assertNotContains(self.client.get(url), "Uma contribuição sua nesta ideia não foi aprovada.")
