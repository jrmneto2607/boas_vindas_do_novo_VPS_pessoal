from django import forms
from ..models import Collaborator


class ProfileForm(forms.ModelForm):
    class Meta:
        model = Collaborator
        fields = ("public_name", "whatsapp", "contact_preference", "contact_authorized")

    def clean(self):
        cleaned = super().clean()
        preference = cleaned.get("contact_preference")
        if preference == Collaborator.ContactPreference.NONE:
            cleaned["contact_authorized"] = False
        elif preference:
            if not cleaned.get("contact_authorized"):
                self.add_error("contact_authorized", "Autorize o contato ou escolha «Não desejo contato».")
            if preference == Collaborator.ContactPreference.WHATSAPP and not cleaned.get("whatsapp"):
                self.add_error("whatsapp", "Informe o WhatsApp para escolher esse canal.")
        return cleaned
