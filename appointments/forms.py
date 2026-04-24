from django import forms

from .models import MedicalReport


class MedicalReportForm(forms.ModelForm):
    class Meta:
        model = MedicalReport
        fields = ["report_file", "description"]
        widgets = {
            "report_file": forms.ClearableFileInput(attrs={"accept": ".pdf,.jpg,.jpeg,.png"}),
            "description": forms.Textarea(attrs={"rows": 4, "placeholder": "Optional description"}),
        }

