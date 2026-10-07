from django.urls import path

from . import profile_views
from . import views
from . import account_views
from . import forum_views
from . import moderation_views
from django.contrib.auth import views as auth_views
from django.urls import reverse_lazy
from .forms.accounts import (
    EmailAuthenticationForm,
    CollaboratorPasswordResetForm,
)

urlpatterns = [
    path("conta/perfil/", profile_views.profile, name="profile"),
    path("conta/ideias/<int:pk>/excluir/", profile_views.idea_remove, name="idea_remove"),
    path("conta/alterar-senha/", auth_views.PasswordChangeView.as_view(
        template_name="home/account_form.html", success_url=reverse_lazy("profile"),
        extra_context={"title": "Alterar senha", "button_label": "Salvar senha"}), name="password_change"),
    path("", views.index, name="home"),
    path("ideias/", views.idea_list, name="idea_list"),
    path("ideias/<int:pk>/", views.idea_detail, name="idea_detail"),
    path(
        "ideias/<int:pk>/comentarios/enviar/",
        forum_views.comment_create,
        name="comment_create",
    ),

    path("ideias/<int:pk>/comentarios/<int:comment_id>/editar/", forum_views.comment_edit, name="comment_edit"),
    path("ideias/<int:pk>/comentarios/<int:comment_id>/remover/", forum_views.comment_remove, name="comment_remove"),
    path("ideias/<int:pk>/comentarios/<int:comment_id>/denunciar/", forum_views.comment_report, name="comment_report"),
    path(
        "ideias/<int:pk>/comentarios/<int:comment_id>/moderar/",
        moderation_views.comment_moderate,
        name="comment_moderate",
    ),
    path(
        "ideias/<int:pk>/desativar/",
        moderation_views.idea_deactivate,
        name="idea_deactivate",
    ),

# Account management
    path(
        "conta/cadastro/",
        account_views.register,
        name="register",
    ),
    path(
        "conta/confirmar/<str:token>/",
        account_views.confirm_email,
        name="confirm_email",
    ),
    path(
        "conta/reenviar-confirmacao/",
        account_views.resend_confirmation,
        name="resend_confirmation",
    ),

# Authentication and password management
    path(
        "conta/entrar/",
        auth_views.LoginView.as_view(
            template_name="home/account_form.html",
            authentication_form=EmailAuthenticationForm,
            extra_context={
                "title": "Entrar",
                "button_label": "Entrar",
            },
        ),
        name="login",
    ),
    path(
        "conta/sair/",
        auth_views.LogoutView.as_view(),
        name="logout",
    ),
    path(
        "conta/recuperar-senha/",
        auth_views.PasswordResetView.as_view(
            template_name="home/account_form.html",
            form_class=CollaboratorPasswordResetForm,
            email_template_name="home/password_reset_email.txt",
            subject_template_name="home/password_reset_subject.txt",
            success_url=reverse_lazy("password_reset_done"),
            extra_context={
                "title": "Recuperar senha",
                "button_label": "Enviar link de recuperação",
            },
        ),
        name="password_reset",
    ),
    path(
        "conta/recuperar-senha/enviado/",
        auth_views.PasswordResetDoneView.as_view(
            template_name="home/account_notice.html",
            extra_context={
                "title": "Verifique seu e-mail",
                "notice": (
                    "Se houver uma conta habilitada para esse endereço, "
                    "você receberá um link para definir uma nova senha. "
                    "Verifique também a pasta de spam."
                ),
            },
        ),
        name="password_reset_done",
    ),
    path(
        "conta/nova-senha/<uidb64>/<token>/",
        auth_views.PasswordResetConfirmView.as_view(
            template_name="home/password_reset_confirm.html",
            success_url=reverse_lazy("password_reset_complete"),
        ),
        name="password_reset_confirm",
    ),
    path(
        "conta/nova-senha/concluido/",
        auth_views.PasswordResetCompleteView.as_view(
            template_name="home/account_notice.html",
            extra_context={
                "title": "Senha atualizada",
                "notice": "Sua senha foi atualizada. Entre com a nova senha.",
            },
        ),
        name="password_reset_complete",
    ),
]