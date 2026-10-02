from django.urls import path

from . import views
from . import account_views


urlpatterns = [
    path("", views.index, name="home"),
    path("ideias/", views.idea_list, name="idea_list"),
    path("ideias/<int:pk>/", views.idea_detail, name="idea_detail"),
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
]