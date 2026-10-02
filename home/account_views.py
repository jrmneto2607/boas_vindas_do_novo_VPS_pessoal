import logging
import uuid
from datetime import timedelta

from django.conf import settings
from django.contrib import messages
from django.contrib.auth import get_user_model
from django.core import signing
from django.core.mail import send_mail
from django.db import IntegrityError, transaction
from django.shortcuts import redirect, render
from django.urls import reverse
from django.utils import timezone
from django.views.decorators.http import require_http_methods

from .forms.accounts import RegistrationForm, ResendConfirmationForm
from .models import Collaborator


logger = logging.getLogger(__name__)

CONFIRMATION_SALT = "home.confirm-email.v1"
CONFIRMATION_MAX_AGE = 24 * 60 * 60
RESEND_INTERVAL = timedelta(minutes=5)


def send_confirmation(request, collaborator):
    token = signing.dumps(
        {
            "collaborator_id": collaborator.pk,
            "email": collaborator.email,
        },
        salt=CONFIRMATION_SALT,
    )

    confirmation_url = request.build_absolute_uri(
        reverse("confirm_email", kwargs={"token": token})
    )

    send_mail(
        subject="Confirme seu e-mail — Maflo Tech",
        message=(
            "Confirme seu e-mail para participar das discussões:\n\n"
            f"{confirmation_url}\n\n"
            "Este link é válido por 24 horas.\n"
            "Se você não realizou este cadastro, ignore esta mensagem."
        ),
        from_email=settings.DEFAULT_FROM_EMAIL,
        recipient_list=[collaborator.email],
        fail_silently=False,
    )


def attempt_confirmation(request, collaborator):
    try:
        send_confirmation(request, collaborator)
    except Exception:
        # A conta permanece pendente e pode solicitar um novo envio.
        logger.exception(
            "Falha ao enviar confirmação para colaborador %s",
            collaborator.pk,
        )
        return False

    return True


@require_http_methods(["GET", "POST"])
def register(request):
    form = RegistrationForm(
        request.POST if request.method == "POST" else None
    )

    if request.method == "POST" and form.is_valid():
        data = form.cleaned_data

        try:
            with transaction.atomic():
                user = get_user_model().objects.create_user(
                    username=uuid.uuid4().hex,
                    email=data["email"],
                    password=data["password1"],
                    is_active=False,
                )

                collaborator = Collaborator.objects.create(
                    user=user,
                    public_name=data["public_name"],
                    email=data["email"],
                    whatsapp=data["whatsapp"],
                    contact_preference=data["contact_preference"],
                    contact_authorized=data["contact_authorized"],
                    contact_consent_at=(
                        timezone.now()
                        if data["contact_authorized"]
                        else None
                    ),
                    confirmation_sent_at=timezone.now(),
                )
        except IntegrityError:
            form.add_error(
                "email",
                "Não foi possível concluir o cadastro com este e-mail. "
                "Se já possui uma conta, solicite uma nova confirmação.",
            )
        else:
            if attempt_confirmation(request, collaborator):
                messages.success(
                    request,
                    "Cadastro recebido. Verifique seu e-mail "
                    "para confirmar a conta.",
                )
            else:
                messages.warning(
                    request,
                    "Sua conta foi criada, mas o envio do e-mail falhou. "
                    "Solicite uma nova confirmação em alguns minutos.",
                )

            return redirect("resend_confirmation")

    return render(request, "home/account_form.html", {
        "form": form,
        "title": "Criar conta",
        "button_label": "Cadastrar",
    })


@require_http_methods(["GET", "POST"])
def confirm_email(request, token):
    try:
        data = signing.loads(
            token,
            salt=CONFIRMATION_SALT,
            max_age=CONFIRMATION_MAX_AGE,
        )
    except signing.BadSignature:
        messages.error(
            request,
            "O link de confirmação é inválido ou expirou.",
        )
        return redirect("resend_confirmation")

    collaborator = None

    if request.method == "POST":
        with transaction.atomic():
            collaborator = (
                Collaborator.objects
                .select_for_update()
                .filter(
                    pk=data["collaborator_id"],
                    email=data["email"],
                )
                .first()
            )

            if collaborator is None:
                messages.error(request, "Confirmação inválida.")
            elif collaborator.email_confirmed_at is not None:
                messages.info(request, "Este e-mail já foi confirmado.")
            elif collaborator.is_blocked:
                messages.error(
                    request,
                    "Esta conta não pode ser ativada. "
                    "Entre em contato com a administração.",
                )
            else:
                collaborator.email_confirmed_at = timezone.now()
                collaborator.save(
                    update_fields=["email_confirmed_at"]
                )

                user = collaborator.user
                user.is_active = True
                user.save(update_fields=["is_active"])

                messages.success(
                    request,
                    "E-mail confirmado. Sua conta foi ativada.",
                )

        return redirect("idea_list")

    collaborator = Collaborator.objects.filter(
        pk=data["collaborator_id"],
        email=data["email"],
    ).first()

    if collaborator is None:
        messages.error(request, "Confirmação inválida.")
        return redirect("resend_confirmation")

    return render(request, "home/confirm_email.html")


@require_http_methods(["GET", "POST"])
def resend_confirmation(request):
    form = ResendConfirmationForm(
        request.POST if request.method == "POST" else None
    )

    if request.method == "POST" and form.is_valid():
        collaborator_to_send = None
        email = form.cleaned_data["email"].strip().lower()

        with transaction.atomic():
            collaborator = (
                Collaborator.objects
                .select_for_update()
                .filter(
                    email__iexact=email,
                    email_confirmed_at__isnull=True,
                    is_blocked=False,
                )
                .first()
            )

            if collaborator is not None:
                now = timezone.now()
                last_sent = collaborator.confirmation_sent_at

                if last_sent is None or now - last_sent >= RESEND_INTERVAL:
                    collaborator.confirmation_sent_at = now
                    collaborator.save(
                        update_fields=["confirmation_sent_at"]
                    )
                    collaborator_to_send = collaborator

        if collaborator_to_send is not None:
            attempt_confirmation(request, collaborator_to_send)

        messages.info(
            request,
            "Se houver uma conta pendente para esse e-mail "
            "e o intervalo de envio permitir, "
            "você receberá uma confirmação. Verifique também o spam.",
        )

        return redirect("resend_confirmation")

    return render(request, "home/account_form.html", {
        "form": form,
        "title": "Confirmar meu e-mail",
        "button_label": "Enviar confirmação",
    })
