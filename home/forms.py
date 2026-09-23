from django import forms
from django.core.validators import FileExtensionValidator

class IdeaSubmissionForm(forms.Form):

    author_name = forms.CharField(required=True)
    idea_title = forms.CharField(required=True)

    idea_pdf = forms.FileField(
        required=False,
        validators=[
            FileExtensionValidator(
                allowed_extensions=["pdf"],
                message="Envie um arquivo no formato PDF."
            )
        ]
    )
    idea_github = forms.URLField(required=False)

    contact_email = forms.EmailField(required=False)
    contact_whatsapp = forms.CharField(required=False)

    idea_consent = forms.BooleanField(required=True)


    def clean_idea_pdf(self):
            idea_pdf = self.cleaned_data.get("idea_pdf")
    
            if idea_pdf and idea_pdf.size > 10 * 1024 * 1024:
                raise forms.ValidationError(
                    "O arquivo PDF deve ter no máximo 10 MB."
                )
    
            return idea_pdf

    def clean(self):
        cleaned_data = super().clean()
        idea_pdf = cleaned_data.get("idea_pdf")
        idea_github = cleaned_data.get("idea_github")

        if (
            not idea_pdf
            and not idea_github
            and not self.errors.get("idea_pdf")
            and not self.errors.get("idea_github")
        ):
            raise forms.ValidationError(
                "Informe um PDF ou um link do GitHub para enviar sua ideia."
            )

        return cleaned_data

    