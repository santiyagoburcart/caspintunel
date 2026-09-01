from django import forms

from apps.panel.group_choices import get_group_choices

from .models import Plan


class PlanAdminForm(forms.ModelForm):
    group_ids = forms.MultipleChoiceField(
        required=False,
        widget=forms.CheckboxSelectMultiple,
        help_text="Panel groups this plan attaches to. Leave all unchecked to use the panel default.",
    )

    class Meta:
        model = Plan
        fields = "__all__"

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        current = list(self.instance.group_ids or []) if self.instance and self.instance.pk else []
        choices = get_group_choices()
        known = {c[0] for c in choices}
        # keep any id already stored on the plan even if the panel no longer lists it
        choices = choices + [(gid, f"Group {gid} (not on panel)") for gid in current if gid not in known]
        self.fields["group_ids"].choices = [(str(c), lbl) for c, lbl in choices]
        if current:
            self.initial["group_ids"] = [str(g) for g in current]

    def clean_group_ids(self):
        return [int(x) for x in self.cleaned_data.get("group_ids", [])]
