from urllib.parse import urlsplit

from django import forms

from ..forum_html import (
    MESSAGE_MAX_LENGTH,
    message_has_text,
    sanitize_message,
)
from ..models import CommentReport


class CommentForm(forms.Form):
    parent_id = forms.IntegerField(
        required=False,
        min_value=1,
        max_value=2**63 - 1,
        widget=forms.HiddenInput(),
    )

    message = forms.CharField(
        label="Mensagem",
        max_length=MESSAGE_MAX_LENGTH,
        widget=forms.Textarea(attrs={
            "rows": 6,
            "data-forum-editor": "true",
            "placeholder": "Compartilhe sua contribuição...",
        }),
        error_messages={
            "max_length": (
                "A mensagem ultrapassou o limite permitido. "
                "Reduza o texto ou a formatação."
            ),
        },
    )
    github_url = forms.URLField(
        label="GitHub",
        required=False,
        max_length=500,
        assume_scheme="https",
        widget=forms.URLInput(attrs={
            "placeholder": "https://github.com/usuario/projeto",
        }),
        help_text="Opcional: compartilhe um exemplo ou versão do projeto.",
    )

    def clean_message(self):
        message = sanitize_message(self.cleaned_data["message"])
        if not message_has_text(message):
            raise forms.ValidationError(
                "Escreva uma mensagem antes de enviar."
            )
        if len(message) > MESSAGE_MAX_LENGTH:
            raise forms.ValidationError(
                "A mensagem ultrapassou o limite permitido. "
                "Reduza o texto ou a formatação."
            )
        return message

    def clean_github_url(self):
        github_url = self.cleaned_data.get("github_url", "")
        if not github_url:
            return ""
        try:
            parsed = urlsplit(github_url)
            valid = (
                parsed.scheme == "https"
                and parsed.hostname == "github.com"
                and parsed.username is None
                and parsed.password is None
                and parsed.port in (None, 443)
            )
        except ValueError:
            valid = False
        if not valid:
            raise forms.ValidationError(
                "Informe um endereço HTTPS do github.com."
            )
        return github_url


class CommentReportForm(forms.Form):
    reason = forms.ChoiceField(
        label="Motivo",
        choices=[
            ("", "Selecione um motivo"),
            *CommentReport.Reason.choices,
        ],
    )
    details = forms.CharField(
        label="Detalhes",
        required=False,
        max_length=1000,
        widget=forms.Textarea(attrs={
            "rows": 3,
            "placeholder": "Explique o problema, se necessário.",
        }),
    )

    def clean(self):
        cleaned_data = super().clean()
        if (
            cleaned_data.get("reason") == CommentReport.Reason.OTHER
            and not cleaned_data.get("details")
        ):
            self.add_error("details", "Explique o motivo da denúncia.")
        return cleaned_data
