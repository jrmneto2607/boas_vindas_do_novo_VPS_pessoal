from django.contrib import admin
from django.contrib.admin.models import LogEntry
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group, Permission
from django.core.exceptions import PermissionDenied
from django.test import Client, RequestFactory, TestCase
from django.urls import reverse
from django.utils import timezone

from .forum_services import create_comment
from .models import Collaborator, Comment, CommentReport, IdeaSubmission
from .moderation_services import can_manage, moderate_comment


class ModerationTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        users = get_user_model()
        cls.author_user = users.objects.create_user(username="author")
        cls.author = Collaborator.objects.create(
            user=cls.author_user, public_name="Autor público", email="private@example.com",
            email_confirmed_at=timezone.now(),
        )
        cls.reporter_user = users.objects.create_user(username="reporter")
        cls.reporter = Collaborator.objects.create(
            user=cls.reporter_user, public_name="Denunciante", email="reporter@example.com",
            email_confirmed_at=timezone.now(),
        )
        cls.staff = users.objects.create_user(username="staff", is_staff=True)
        cls.moderator = users.objects.create_user(username="moderator", is_staff=True)
        cls.editor = users.objects.create_user(username="editor", is_staff=True)
        cls.deleter = users.objects.create_user(username="deleter", is_staff=True)
        cls.outsider = users.objects.create_user(username="outsider")
        cls.superuser = users.objects.create_superuser(username="root", email="root@example.com", password="test")
        comment_permission = Permission.objects.get(content_type__app_label="home", codename="change_comment")
        idea_permission = Permission.objects.get(content_type__app_label="home", codename="change_ideasubmission")
        delete_permission = Permission.objects.get(content_type__app_label="home", codename="delete_ideasubmission")
        cls.moderator.user_permissions.add(comment_permission)
        cls.editor.user_permissions.add(idea_permission)
        cls.deleter.user_permissions.add(delete_permission)
        cls.outsider.user_permissions.add(comment_permission, idea_permission, delete_permission)
        cls.idea = IdeaSubmission.objects.create(author_name="Autor", idea_title="Ideia moderada", is_featured=True)
        cls.other_idea = IdeaSubmission.objects.create(author_name="Autor", idea_title="Outra ideia")
        cls.pending = Comment.objects.create(idea=cls.idea, author=cls.author, message="Contribuição em análise")
        cls.published = Comment.objects.create(idea=cls.idea, author=cls.author, message="Contribuição pública", status=Comment.Status.PUBLISHED)
        cls.disabled = Comment.objects.create(idea=cls.idea, author=cls.author, message="Contribuição desativada", status=Comment.Status.DISABLED)

    def login(self, user):
        self.client.force_login(user)

    def moderate(self, comment=None, action="approve"):
        comment = comment or self.pending
        return self.client.post(reverse("comment_moderate", args=[self.idea.pk, comment.pk]), {"action": action})

    def detail(self):
        return self.client.get(reverse("idea_detail", args=[self.idea.pk]))

    def test_staff_can_access_organizer_but_has_no_extra_controls(self):
        self.login(self.staff)
        self.assertEqual(self.client.get(reverse("admin:index")).status_code, 200)
        response = self.detail()
        self.assertContains(response, "Organizador")
        self.assertNotContains(response, 'aria-label="Aprovar comentário"')
        self.assertNotContains(response, "Desativar ideia")
        self.assertNotContains(response, "Excluir ideia")
        self.assertNotContains(response, "Contribuição em análise")

    def test_regular_users_and_anonymous_cannot_manage(self):
        for user in (self.author_user, self.staff, self.outsider):
            self.login(user)
            self.assertEqual(self.moderate().status_code, 403)
            self.assertEqual(self.client.post(reverse("idea_deactivate", args=[self.idea.pk])).status_code, 403)
        self.client.logout()
        self.assertEqual(self.moderate().status_code, 403)
        self.pending.refresh_from_db()
        self.assertEqual(self.pending.status, Comment.Status.PENDING)
        self.idea.refresh_from_db()
        self.assertTrue(self.idea.is_active)

    def test_nonstaff_permission_does_not_expose_private_comments(self):
        self.login(self.outsider)
        response = self.detail()
        self.assertNotContains(response, "Contribuição em análise")
        self.assertNotContains(response, "Contribuição desativada")
        self.assertNotContains(response, "Organizador")
        self.assertNotContains(response, 'aria-label="Aprovar comentário"')

    def test_moderator_sees_states_controls_and_replies(self):
        Comment.objects.create(idea=self.idea, author=self.author, parent=self.pending, message="Resposta pendente")
        self.login(self.moderator)
        response = self.detail()
        self.assertContains(response, "Contribuição em análise")
        self.assertContains(response, "Contribuição desativada")
        self.assertContains(response, "Resposta pendente")
        self.assertContains(response, "Aguardando aprovação")
        self.assertContains(response, 'aria-label="Aprovar comentário"')
        self.assertContains(response, 'aria-label="Desativar comentário"')
        self.assertNotContains(response, self.author.email)
        self.assertNotContains(response, "Desativar ideia")
        items = {item["id"]: item for item in response.context["forum_page"]}
        self.assertFalse(items[self.published.pk]["can_approve"])
        self.assertTrue(items[self.published.pk]["can_disable"])
        self.assertTrue(items[self.disabled.pk]["can_approve"])
        self.assertFalse(items[self.disabled.pk]["can_disable"])

    def test_permissions_are_independent(self):
        self.login(self.editor)
        response = self.detail()
        self.assertContains(response, "Desativar ideia")
        self.assertNotContains(response, "Excluir ideia")
        self.assertNotContains(response, 'aria-label="Aprovar comentário"')
        self.assertEqual(self.moderate().status_code, 403)
        self.login(self.deleter)
        response = self.detail()
        self.assertContains(response, "Excluir ideia")
        self.assertNotContains(response, "Desativar ideia")
        self.assertEqual(self.client.post(reverse("idea_deactivate", args=[self.idea.pk])).status_code, 403)

    def test_group_permission_is_supported(self):
        group = Group.objects.create(name="Moderadores")
        group.permissions.add(Permission.objects.get(content_type__app_label="home", codename="change_comment"))
        self.staff.groups.add(group)
        self.login(self.staff)
        self.assertEqual(self.moderate().status_code, 302)
        self.pending.refresh_from_db()
        self.assertEqual(self.pending.status, Comment.Status.PUBLISHED)

    def test_approval_records_actor_and_resolves_reports(self):
        report = CommentReport.objects.create(comment=self.pending, reporter=self.reporter, reason="spam")
        self.login(self.moderator)
        self.assertEqual(self.moderate().status_code, 302)
        self.pending.refresh_from_db()
        report.refresh_from_db()
        self.assertEqual(self.pending.status, Comment.Status.PUBLISHED)
        self.assertEqual(self.pending.moderated_by_id, self.moderator.pk)
        self.assertIsNotNone(self.pending.moderated_at)
        self.assertEqual(report.reviewed_by_id, self.moderator.pk)
        self.assertIsNotNone(report.reviewed_at)
        self.assertTrue(LogEntry.objects.filter(user=self.moderator, object_id=str(self.pending.pk), change_message="Comentário aprovado.").exists())
        self.client.logout()
        self.assertContains(self.detail(), "Contribuição em análise")

    def test_published_comment_can_be_disabled_and_reapproved(self):
        self.login(self.moderator)
        self.assertEqual(self.moderate(self.published, "disable").status_code, 302)
        self.published.refresh_from_db()
        self.assertEqual(self.published.status, Comment.Status.DISABLED)
        self.client.logout()
        self.assertNotContains(self.detail(), "Contribuição pública")
        self.login(self.author_user)
        self.assertContains(self.detail(), "Sua contribuição não foi aprovada.")
        self.login(self.moderator)
        self.assertEqual(self.moderate(self.published, "approve").status_code, 302)
        self.published.refresh_from_db()
        self.assertEqual(self.published.status, Comment.Status.PUBLISHED)

    def test_wrong_idea_missing_comment_and_invalid_action(self):
        self.login(self.moderator)
        url = reverse("comment_moderate", args=[self.other_idea.pk, self.pending.pk])
        self.assertEqual(self.client.post(url, {"action": "approve"}).status_code, 404)
        url = reverse("comment_moderate", args=[self.idea.pk, 999999])
        self.assertEqual(self.client.post(url, {"action": "approve"}).status_code, 404)
        self.assertEqual(self.moderate(action="delete").status_code, 302)
        self.pending.refresh_from_db()
        self.assertEqual(self.pending.status, Comment.Status.PENDING)
        self.assertFalse(LogEntry.objects.exists())

    def test_removed_content_cannot_be_restored_even_by_superuser(self):
        Comment.objects.filter(pk=self.pending.pk).update(removed_at=timezone.now())
        self.login(self.superuser)
        self.assertEqual(self.moderate().status_code, 302)
        self.pending.refresh_from_db()
        self.assertEqual(self.pending.status, Comment.Status.PENDING)
        self.assertIsNotNone(self.pending.removed_at)
        self.assertFalse(LogEntry.objects.exists())

    def test_get_and_csrf_cannot_modify_content(self):
        self.login(self.superuser)
        url = reverse("comment_moderate", args=[self.idea.pk, self.pending.pk])
        self.assertEqual(self.client.get(url).status_code, 405)
        self.assertEqual(self.client.get(reverse("idea_deactivate", args=[self.idea.pk])).status_code, 405)
        client = Client(enforce_csrf_checks=True)
        client.force_login(self.superuser)
        self.assertEqual(client.post(url, {"action": "approve"}).status_code, 403)
        self.assertEqual(client.post(reverse("idea_deactivate", args=[self.idea.pk])).status_code, 403)

    def test_superuser_has_all_controls(self):
        self.login(self.superuser)
        response = self.detail()
        self.assertContains(response, "Organizador")
        self.assertContains(response, "Desativar ideia")
        self.assertContains(response, "Excluir ideia")
        self.assertContains(response, 'aria-label="Aprovar comentário"')
        self.assertEqual(self.moderate().status_code, 302)
        self.assertEqual(self.client.post(reverse("idea_deactivate", args=[self.idea.pk])).status_code, 302)

    def test_inactive_staff_is_denied(self):
        self.moderator.is_active = False
        self.assertFalse(can_manage(self.moderator, "home.change_comment"))
        with self.assertRaises(PermissionDenied):
            moderate_comment(user=self.moderator, idea_id=self.idea.pk, comment_id=self.pending.pk, action="approve")

    def test_deactivation_hides_idea_and_keeps_records(self):
        self.login(self.editor)
        self.assertEqual(self.client.post(reverse("idea_deactivate", args=[self.idea.pk])).status_code, 302)
        self.idea.refresh_from_db()
        self.assertFalse(self.idea.is_active)
        self.assertEqual(Comment.objects.filter(idea=self.idea).count(), 3)
        self.assertTrue(LogEntry.objects.filter(user=self.editor, change_message="Ideia desativada pelo site.").exists())
        self.client.logout()
        for url in (reverse("home"), reverse("idea_list")):
            self.assertNotContains(self.client.get(url), "Ideia moderada")
        self.assertEqual(self.detail().status_code, 404)
        self.login(self.author_user)
        self.assertEqual(self.client.post(reverse("comment_create", args=[self.idea.pk]), {"message": "Texto"}).status_code, 404)
        with self.assertRaises(PermissionDenied):
            create_comment(user=self.author_user, idea_id=self.idea.pk, cleaned_data={"message": "Texto", "github_url": ""})

    def test_inactive_idea_can_be_reactivated_in_organizer(self):
        IdeaSubmission.objects.filter(pk=self.idea.pk).update(is_active=False)
        self.login(self.editor)
        response = self.client.post(reverse("admin:home_ideasubmission_change", args=[self.idea.pk]), {
            "author_name": self.idea.author_name, "idea_title": self.idea.idea_title,
            "status": self.idea.status, "is_active": "on", "_save": "Salvar",
        })
        self.assertEqual(response.status_code, 302)
        self.idea.refresh_from_db()
        self.assertTrue(self.idea.is_active)
        self.assertEqual(self.detail().status_code, 200)

    def test_delete_link_uses_organizer_confirmation_without_deleting_on_get(self):
        self.login(self.deleter)
        response = self.client.get(reverse("admin:home_ideasubmission_delete", args=[self.other_idea.pk]))
        self.assertEqual(response.status_code, 200)
        self.assertTrue(IdeaSubmission.objects.filter(pk=self.other_idea.pk).exists())
        self.login(self.staff)
        self.assertEqual(self.client.get(reverse("admin:home_ideasubmission_delete", args=[self.other_idea.pk])).status_code, 403)

    def test_admin_bulk_action_uses_same_moderation_rules(self):
        self.login(self.moderator)
        model_admin = admin.site._registry[Comment]
        request = RequestFactory().post("/organizador/")
        request.user = self.moderator
        count = model_admin._moderate_selected(request, Comment.objects.filter(pk=self.pending.pk), "approve")
        self.assertEqual(count, 1)
        self.pending.refresh_from_db()
        self.assertEqual(self.pending.moderated_by_id, self.moderator.pk)
        self.assertEqual(self.pending.status, Comment.Status.PUBLISHED)
        self.author.refresh_from_db()
        self.assertTrue(self.author.can_publish_directly)

    def test_moderation_of_inactive_idea_returns_to_organizer(self):
        IdeaSubmission.objects.filter(pk=self.idea.pk).update(is_active=False)
        self.login(self.moderator)
        response = self.moderate()
        self.assertEqual(response.url, reverse("admin:home_comment_changelist"))

    def test_approval_releases_future_comments_and_replies(self):
        moderate_comment(user=self.moderator, idea_id=self.idea.pk,
                         comment_id=self.pending.pk, action="approve")
        self.author.refresh_from_db()
        self.assertTrue(self.author.can_publish_directly)
        self.assertTrue(LogEntry.objects.filter(object_id=str(self.author.pk),
            change_message="Publicação direta liberada após aprovação de comentário.").exists())
        Comment.objects.filter(author=self.author).update(created_at=timezone.now() - timezone.timedelta(minutes=2))
        comment = create_comment(user=self.author_user, idea_id=self.other_idea.pk,
                                 cleaned_data={"message": "Nova contribuição", "github_url": ""})
        self.assertEqual(comment.status, Comment.Status.PUBLISHED)
        Comment.objects.filter(pk=comment.pk).update(created_at=timezone.now() - timezone.timedelta(minutes=2))
        reply = create_comment(user=self.author_user, idea_id=self.idea.pk,
                               cleaned_data={"message": "Nova resposta", "github_url": "", "parent_id": self.published.pk})
        self.assertEqual(reply.status, Comment.Status.PUBLISHED)

    def test_approving_reply_also_releases_author(self):
        reply = Comment.objects.create(idea=self.idea, author=self.author,
                                       parent=self.published, message="Resposta")
        moderate_comment(user=self.moderator, idea_id=self.idea.pk,
                         comment_id=reply.pk, action="approve")
        self.author.refresh_from_db()
        self.assertTrue(self.author.can_publish_directly)

    def test_disabling_does_not_release_author(self):
        moderate_comment(user=self.moderator, idea_id=self.idea.pk,
                         comment_id=self.pending.pk, action="disable")
        self.author.refresh_from_db()
        self.assertFalse(self.author.can_publish_directly)

    def test_approval_does_not_remove_participation_block(self):
        Collaborator.objects.filter(pk=self.author.pk).update(is_blocked=True)
        moderate_comment(user=self.moderator, idea_id=self.idea.pk,
                         comment_id=self.pending.pk, action="approve")
        self.author.refresh_from_db()
        self.assertTrue(self.author.is_blocked)
        with self.assertRaises(PermissionDenied):
            create_comment(user=self.author_user, idea_id=self.idea.pk,
                           cleaned_data={"message": "Texto", "github_url": ""})


    def test_owner_can_edit_and_remove_without_losing_replies(self):
        reply = Comment.objects.create(idea=self.idea, author=self.reporter,
            parent=self.published, message="Resposta preservada", status=Comment.Status.PUBLISHED)
        self.login(self.author_user)
        url = reverse("comment_edit", args=[self.idea.pk, self.published.pk])
        self.assertContains(self.client.get(url), "Editar contribuição")
        response = self.client.post(url, {"message": "<strong>Texto editado</strong>", "github_url": ""})
        self.assertEqual(response.status_code, 302)
        self.published.refresh_from_db()
        self.assertEqual(self.published.status, Comment.Status.PENDING)
        self.assertEqual(self.published.message, "<strong>Texto editado</strong>")
        self.assertEqual(self.client.get(reverse("comment_remove", args=[self.idea.pk, self.published.pk])).status_code, 405)
        self.assertEqual(self.client.post(reverse("comment_remove", args=[self.idea.pk, self.published.pk])).status_code, 302)
        self.published.refresh_from_db()
        self.assertIsNotNone(self.published.removed_at)
        self.assertTrue(Comment.objects.filter(pk=reply.pk).exists())
        self.client.logout()
        self.assertContains(self.detail(), "Comentário removido pelo autor.")
        self.assertContains(self.detail(), "Resposta preservada")
        self.assertNotContains(self.detail(), "Texto editado")

    def test_other_users_cannot_edit_or_remove_and_csrf_is_required(self):
        self.login(self.reporter_user)
        for action in ("comment_edit", "comment_remove"):
            url = reverse(action, args=[self.idea.pk, self.published.pk])
            self.assertEqual(self.client.post(url, {"message": "Tentativa"}).status_code, 404)
        client = Client(enforce_csrf_checks=True)
        client.force_login(self.author_user)
        for action in ("comment_edit", "comment_remove", "comment_report"):
            self.assertEqual(client.post(reverse(action, args=[self.idea.pk, self.published.pk])).status_code, 403)

    def test_reports_are_unique_private_and_hide_after_two_people(self):
        self.login(self.reporter_user)
        url = reverse("comment_report", args=[self.idea.pk, self.published.pk])
        self.assertEqual(self.client.post(url, {"reason": "other", "details": ""}).status_code, 200)
        self.assertFalse(CommentReport.objects.exists())
        self.assertEqual(self.client.post(url, {"reason": "spam", "details": "Detalhe privado"}).status_code, 302)
        self.assertEqual(self.client.post(url, {"reason": "spam"}).status_code, 200)
        self.assertEqual(CommentReport.objects.count(), 1)
        self.assertNotContains(self.detail(), "Detalhe privado")
        user = get_user_model().objects.create_user(username="second-reporter")
        Collaborator.objects.create(user=user, public_name="Segundo", email="second@example.com", email_confirmed_at=timezone.now())
        self.login(user)
        self.assertEqual(self.client.post(url, {"reason": "abuse"}).status_code, 302)
        self.published.refresh_from_db()
        self.assertEqual(self.published.status, Comment.Status.REPORTED)
        self.client.logout()
        self.assertNotContains(self.detail(), "Contribuição pública")
        self.login(self.author_user)
        self.assertContains(self.detail(), "Contribuição pública")
        self.assertNotContains(self.detail(), "Oculto por denúncias")

    def test_cannot_report_own_comment_or_participate_when_blocked(self):
        self.login(self.author_user)
        self.assertEqual(self.client.get(reverse("comment_report", args=[self.idea.pk, self.published.pk])).status_code, 404)
        Collaborator.objects.filter(pk=self.author.pk).update(is_blocked=True)
        for action in ("comment_edit", "comment_remove", "comment_report"):
            self.assertEqual(self.client.post(reverse(action, args=[self.idea.pk, self.published.pk]), {"message": "Texto", "reason": "spam"}).status_code, 403)

    def test_trusted_edits_publish_but_rejected_edits_return_to_review(self):
        Collaborator.objects.filter(pk=self.author.pk).update(can_publish_directly=True)
        self.login(self.author_user)
        for comment, status in ((self.published, Comment.Status.PUBLISHED), (self.disabled, Comment.Status.PENDING)):
            self.assertEqual(self.client.post(reverse("comment_edit", args=[self.idea.pk, comment.pk]), {"message": "Mensagem alterada"}).status_code, 302)
            comment.refresh_from_db()
            self.assertEqual(comment.status, status)

    def test_sort_count_and_shared_link_follow_visible_pagination(self):
        for i in range(12):
            Comment.objects.create(idea=self.idea, author=self.reporter, message=f"Contribuição {i}", status=Comment.Status.PUBLISHED)
        recent = self.detail().context["forum_page"]
        self.assertEqual(recent.contribution_count, 13)
        oldest = self.client.get(reverse("idea_detail", args=[self.idea.pk]), {"ordem": "antigos"}).context["forum_page"]
        self.assertEqual(oldest.object_list[0]["id"], self.published.pk)
        shared = self.client.get(reverse("idea_detail", args=[self.idea.pk]), {"comentario": self.published.pk}).context["forum_page"]
        self.assertEqual(shared.number, 2)
        self.assertIn(self.published.pk, [item["id"] for item in shared])
        self.assertNotContains(self.detail(), "Contribuição em análise")

    def test_reply_preview_and_controls_are_attached_to_each_contribution(self):
        self.login(self.author_user)
        response = self.client.get(reverse("idea_detail", args=[self.idea.pk]), {"responder": self.published.pk})
        self.assertContains(response, 'class="forum-reply-preview"')
        self.assertContains(response, "Contribuição pública")
        self.assertContains(response, reverse("comment_edit", args=[self.idea.pk, self.published.pk]))
        self.assertContains(response, "Compartilhar ideia")
        self.assertContains(response, "Copiar link")
