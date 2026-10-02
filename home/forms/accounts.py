from django import forms
from django.contrib.auth import get_user_model
from django.contrib.auth.password_validation import validate_password

from ..models import Collaborator


class RegistrationForm(forms.Form):
    public_name = forms.CharField(
        label="Nome ou pseudônimo público",
        max_length=100,
    )
    email = forms.EmailField(
        label="E-mail",
        max_length=254,
    )
    whatsapp = forms.CharField(
        label="WhatsApp — opcional",
        max_length=30,
        required=False,
    )
    contact_preference = forms.ChoiceField(
        label="Preferência de contato sobre suas contribuições",
        choices=Collaborator.ContactPreference.choices,
    )
    contact_authorized = forms.BooleanField(
        label="Autorizo a administração a entrar em contato "
              "sobre minhas contribuições pelo canal escolhido.",
        required=False,
    )
    password1 = forms.CharField(
        label="Senha",
        strip=False,
        widget=forms.PasswordInput(
            attrs={"autocomplete": "new-password"}
        ),
    )
    password2 = forms.CharField(
        label="Confirme a senha",
        strip=False,
        widget=forms.PasswordInput(
            attrs={"autocomplete": "new-password"}
        ),
    )

    def clean_email(self):
        email = self.cleaned_data["email"].strip().lower()

        if Collaborator.objects.filter(email__iexact=email).exists():
            raise forms.ValidationError(
                "Este e-mail já está cadastrado. "
                "Entre na sua conta ou solicite uma nova confirmação."
            )

        return email

    def clean(self):
        cleaned = super().clean()
        password1 = cleaned.get("password1")
        password2 = cleaned.get("password2")

        if password1 and password2 and password1 != password2:
            self.add_error("password2", "As senhas não coincidem.")

        if password1:
            candidate = get_user_model()(
                email=cleaned.get("email", ""),
                first_name=cleaned.get("public_name", ""),
            )

            try:
                validate_password(password1, user=candidate)
            except forms.ValidationError as error:
                self.add_error("password1", error)

        preference = cleaned.get("contact_preference")
        authorized = cleaned.get("contact_authorized")

        if preference == Collaborator.ContactPreference.NONE:
            cleaned["contact_authorized"] = False
        else:
            if not authorized:
                self.add_error(
                    "contact_authorized",
                    "Autorize o contato ou escolha «Não desejo contato».",
                )

            if (
                preference == Collaborator.ContactPreference.WHATSAPP
                and not cleaned.get("whatsapp")
            ):
                self.add_error(
                    "whatsapp",
                    "Informe o WhatsApp para escolher esse canal.",
                )

        return cleaned


class ResendConfirmationForm(forms.Form):
    email = forms.EmailField(label="E-mail")