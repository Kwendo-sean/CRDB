from datetime import datetime
from django import forms
from django.utils import timezone
from .models import Activity, Badge, EventSettings, GoogleRegistrationSource, Participant, Quiz, ScoringRule, Session


class StyledFormMixin:
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for field in self.fields.values():
            field.widget.attrs.setdefault("class", "control-input")


class SessionForm(StyledFormMixin, forms.ModelForm):
    date = forms.DateField(widget=forms.DateInput(attrs={"type": "date"}))
    start_time = forms.TimeField(widget=forms.TimeInput(attrs={"type": "time"}))
    end_time = forms.TimeField(widget=forms.TimeInput(attrs={"type": "time"}))

    class Meta:
        model = Session
        fields = ("title", "day", "date", "start_time", "end_time", "facilitator", "format", "audience", "location", "capacity", "is_active")

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if self.instance and self.instance.pk:
            local_start = timezone.localtime(self.instance.starts_at)
            local_end = timezone.localtime(self.instance.ends_at)
            self.fields["date"].initial = local_start.date()
            self.fields["start_time"].initial = local_start.time().replace(second=0, microsecond=0)
            self.fields["end_time"].initial = local_end.time().replace(second=0, microsecond=0)

    def clean(self):
        cleaned = super().clean()
        if all(cleaned.get(k) for k in ("date", "start_time", "end_time")):
            start = timezone.make_aware(datetime.combine(cleaned["date"], cleaned["start_time"]))
            end = timezone.make_aware(datetime.combine(cleaned["date"], cleaned["end_time"]))
            if end <= start:
                self.add_error("end_time", "End time must be after start time.")
            cleaned["starts_at"] = start
            cleaned["ends_at"] = end
        return cleaned

    def save(self, commit=True):
        obj = super().save(False)
        obj.starts_at = self.cleaned_data["starts_at"]
        obj.ends_at = self.cleaned_data["ends_at"]
        if commit:
            obj.save()
        return obj


class QuizForm(StyledFormMixin, forms.ModelForm):
    class Meta:
        model = Quiz
        fields = ("title", "internal_description", "participant_description", "day", "event_date", "start_time", "end_time", "prize_eligible", "contributes_to_weekly", "daily_leaderboard_enabled", "max_attempts", "question_order", "answer_order", "auto_close_questions", "tie_break_method", "theme_key")
        widgets = {
            "event_date": forms.DateInput(attrs={"type": "date"}),
            "start_time": forms.TimeInput(attrs={"type": "time"}),
            "end_time": forms.TimeInput(attrs={"type": "time"}),
            "internal_description": forms.Textarea(attrs={"rows": 3}),
            "participant_description": forms.Textarea(attrs={"rows": 3}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for name in ("question_order", "answer_order", "tie_break_method", "theme_key"):
            self.fields[name].required = False

    def clean(self):
        cleaned = super().clean()
        cleaned["question_order"] = cleaned.get("question_order") or "fixed"
        cleaned["answer_order"] = cleaned.get("answer_order") or "fixed"
        cleaned["tie_break_method"] = cleaned.get("tie_break_method") or "correct_time_completion"
        cleaned["theme_key"] = cleaned.get("theme_key") or "infrastructure"
        return cleaned


class QuestionForm(StyledFormMixin, forms.Form):
    text = forms.CharField(widget=forms.Textarea(attrs={"rows": 3}), label="Question")
    time_limit_seconds = forms.IntegerField(min_value=5, max_value=3600, initial=20,
        label="Time limit (seconds)",
        help_text="How long this question stays open. 20 or 30 for a fast round; 300 is five minutes.",
        widget=forms.NumberInput(attrs={"list": "common-timers", "step": 5}))
    base_points = forms.IntegerField(min_value=1, initial=1000, label="Points")
    answer_1 = forms.CharField(label="Answer A")
    answer_2 = forms.CharField(label="Answer B")
    answer_3 = forms.CharField(label="Answer C")
    answer_4 = forms.CharField(label="Answer D")
    correct_answer = forms.TypedChoiceField(choices=((1, "A"), (2, "B"), (3, "C"), (4, "D")), coerce=int, widget=forms.RadioSelect)
    host_note = forms.CharField(widget=forms.Textarea(attrs={"rows": 3}), label="Explanation / Host Note")
    topic = forms.CharField(required=False)


class SelfRegistrationForm(StyledFormMixin, forms.Form):
    """Join with an email address, no spreadsheet and no Google Form required."""

    full_name = forms.CharField(label="Full name", max_length=200)
    email = forms.EmailField(label="Work email", max_length=254)
    department = forms.CharField(label="Department", max_length=160, required=False)
    staff_id = forms.CharField(label="Staff ID (optional)", max_length=80, required=False)

    def __init__(self, *args, settings_row=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.settings_row = settings_row or EventSettings.load()
        if not self.settings_row.self_registration_collects_department:
            self.fields.pop("department")
        domains = self.settings_row.allowed_domains()
        if domains:
            self.fields["email"].help_text = "Use your " + " or ".join("@" + domain for domain in domains) + " address."

    def clean_email(self):
        email = self.cleaned_data["email"].strip().lower()
        if not self.settings_row.email_is_allowed(email):
            domains = " or ".join("@" + domain for domain in self.settings_row.allowed_domains())
            raise forms.ValidationError(f"Registration is open to {domains} addresses only.")
        return email

    def clean_staff_id(self):
        return (self.cleaned_data.get("staff_id") or "").strip().upper()

    def clean(self):
        cleaned = super().clean()
        email, staff_id = cleaned.get("email"), cleaned.get("staff_id")
        # Surface a clash as a form error rather than letting the unique
        # constraint raise on save.
        if email and Participant.objects.filter(email=email).exists():
            self.add_error("email", "This email is already registered. Enter it on the sign-in step instead.")
        if staff_id and Participant.objects.filter(staff_id=staff_id).exists():
            self.add_error("staff_id", "This staff ID is already registered. Enter it on the sign-in step instead.")
        return cleaned

    def save(self):
        return Participant.objects.create(
            full_name=self.cleaned_data["full_name"].strip(),
            email=self.cleaned_data["email"],
            department=(self.cleaned_data.get("department") or "").strip(),
            staff_id=self.cleaned_data.get("staff_id") or None,
            registration_timestamp=timezone.now(),
        )


class ActivityForm(StyledFormMixin, forms.ModelForm):
    show_on_dashboard = forms.BooleanField(required=False, initial=True)
    class Meta:
        model = Activity
        fields = ("name", "code", "description", "day", "points", "repeatable", "is_active")
        widgets = {"description": forms.Textarea(attrs={"rows": 3})}


class EventSettingsForm(StyledFormMixin, forms.ModelForm):
    class Meta:
        model = EventSettings
        exclude = ("created_at", "updated_at")
        widgets = {"start_date": forms.DateInput(attrs={"type": "date"}), "end_date": forms.DateInput(attrs={"type": "date"})}


class BadgeForm(StyledFormMixin, forms.ModelForm):
    class Meta:
        model = Badge
        fields = ("code", "name", "description", "icon", "is_active")


class ScoringRuleForm(StyledFormMixin, forms.ModelForm):
    class Meta:
        model = ScoringRule
        fields = ("code", "category", "points", "description", "is_active")


class GoogleSourceForm(StyledFormMixin, forms.ModelForm):
    class Meta:
        model = GoogleRegistrationSource
        fields = ("name", "spreadsheet_id", "worksheet_name", "column_mappings", "unique_identifiers", "enabled")
        widgets = {"column_mappings": forms.Textarea(attrs={"rows": 5}), "unique_identifiers": forms.Textarea(attrs={"rows": 2})}
