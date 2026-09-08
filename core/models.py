import secrets
import uuid
from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import IntegrityError, models, transaction
from django.db.models import Q


def token(): return secrets.token_urlsafe(32)
def pass_number():
    # 8 hex characters, not 6. At 2,000 participants a 6-character space carries an
    # 11% chance that two people collide, which would fail a registration outright.
    return f"CRDB-LW-{secrets.token_hex(4).upper()}"

class TimeStamped(models.Model):
    created_at=models.DateTimeField(auto_now_add=True)
    updated_at=models.DateTimeField(auto_now=True)
    class Meta: abstract=True

class Participant(TimeStamped):
    id=models.UUIDField(primary_key=True,default=uuid.uuid4,editable=False)
    staff_id=models.CharField(max_length=80,unique=True,null=True,blank=True)
    full_name=models.CharField(max_length=200)
    email=models.EmailField(unique=True,null=True,blank=True)
    department=models.CharField(max_length=160,blank=True)
    job_role=models.CharField(max_length=160,blank=True)
    phone=models.CharField(max_length=40,blank=True)
    qr_token=models.CharField(max_length=64,unique=True,default=token,editable=False)
    pass_number=models.CharField(max_length=32,unique=True,default=pass_number,editable=False)
    registration_timestamp=models.DateTimeField(null=True,blank=True)
    is_active=models.BooleanField(default=True)
    class Meta:
        ordering=("full_name",)
        indexes=[models.Index(fields=["department"]),models.Index(fields=["is_active","full_name"])]
    def clean(self):
        if not self.staff_id and not self.email: raise ValidationError("Staff ID or email is required.")
    def save(self,*args,**kwargs):
        self.staff_id=self.staff_id.strip().upper() if self.staff_id else None
        self.email=self.email.strip().lower() if self.email else None
        self.full_name=self.full_name.strip()
        creating=self._state.adding
        for remaining in reversed(range(5)):
            try:
                self.full_clean()
                with transaction.atomic():
                    return super().save(*args,**kwargs)
            except (IntegrityError,ValidationError) as exc:
                # Two people can draw the same random pass number. Redraw and retry
                # rather than failing someone's registration; never mask any other error.
                if not creating or not remaining or "pass_number" not in str(exc): raise
                self.pass_number=pass_number()
    @property
    def public_name(self):
        bits=self.full_name.split()
        return self.full_name if len(bits)<2 else f"{bits[0]} {bits[-1][0]}."
    def __str__(self): return f"{self.full_name} / {self.pass_number}"

class Session(TimeStamped):
    class Format(models.TextChoices): FACE_TO_FACE="face","FACE-TO-FACE"; VIRTUAL="virtual","VIRTUAL"; HYBRID="hybrid","HYBRID"
    day=models.PositiveSmallIntegerField()
    source_key=models.CharField(max_length=120,unique=True,null=True,blank=True)
    title=models.CharField(max_length=300)
    facilitator=models.CharField(max_length=200,blank=True)
    format=models.CharField(max_length=20,choices=Format.choices,default=Format.FACE_TO_FACE)
    audience=models.CharField(max_length=240,blank=True)
    location=models.CharField(max_length=200,blank=True)
    starts_at=models.DateTimeField()
    ends_at=models.DateTimeField()
    capacity=models.PositiveIntegerField(null=True,blank=True)
    is_active=models.BooleanField(default=True)
    class Meta: ordering=("day","starts_at"); indexes=[models.Index(fields=["day","starts_at"])]
    def __str__(self): return self.title

class SessionRegistration(TimeStamped):
    participant=models.ForeignKey(Participant,on_delete=models.CASCADE,related_name="session_registrations")
    session=models.ForeignKey(Session,on_delete=models.CASCADE,related_name="registrations")
    source=models.CharField(max_length=40,default="google_sheet")
    source_row_key=models.CharField(max_length=160,blank=True)
    selected_at=models.DateTimeField(null=True,blank=True)
    class Meta: constraints=[models.UniqueConstraint(fields=["participant","session"],name="unique_session_registration")]

class Attendance(TimeStamped):
    participant=models.ForeignKey(Participant,on_delete=models.PROTECT,related_name="attendance_records")
    session=models.ForeignKey(Session,on_delete=models.PROTECT,related_name="attendance_records")
    checked_in_at=models.DateTimeField()
    checked_in_by=models.ForeignKey(settings.AUTH_USER_MODEL,on_delete=models.SET_NULL,null=True,blank=True)
    source=models.CharField(max_length=30,default="qr")
    is_override=models.BooleanField(default=False)
    override_note=models.TextField(blank=True)
    class Meta: constraints=[models.UniqueConstraint(fields=["participant","session"],name="unique_attendance")]; indexes=[models.Index(fields=["session","checked_in_at"]),models.Index(fields=["checked_in_at"])]

class Quiz(TimeStamped):
    class State(models.TextChoices):
        DRAFT="draft","DRAFT"
        SCHEDULED="scheduled","SCHEDULED"
        LOBBY="lobby","LOBBY OPEN"
        QUESTION_OPEN="question_open","LIVE"
        QUESTION_CLOSED="question_closed","QUESTION CLOSED"
        REVEAL="reveal","ANSWER REVEAL"
        LEADERBOARD="leaderboard","LEADERBOARD"
        FINISHED="finished","FINISHED"
        VERIFIED="verified","VERIFIED"
        ARCHIVED="archived","ARCHIVED"
    day=models.PositiveSmallIntegerField()
    title=models.CharField(max_length=240)
    internal_description=models.TextField(blank=True)
    participant_description=models.TextField(blank=True)
    event_date=models.DateField(null=True,blank=True)
    start_time=models.TimeField(null=True,blank=True)
    end_time=models.TimeField(null=True,blank=True)
    sequence=models.PositiveSmallIntegerField(unique=True)
    state=models.CharField(max_length=30,choices=State.choices,default=State.DRAFT)
    prize_eligible=models.BooleanField(default=True)
    contributes_to_weekly=models.BooleanField(default=True)
    daily_leaderboard_enabled=models.BooleanField(default=True)
    speed_bonus_enabled=models.BooleanField(default=False)
    auto_close_questions=models.BooleanField(default=True)
    auto_run=models.BooleanField(default=True,help_text="Start once and the whole round plays itself: every question opens and closes on its own timer, with no host action between questions.")
    reveal_seconds=models.PositiveSmallIntegerField(default=8,help_text="Seconds spent showing the correct answer between questions.")
    lobby_seconds=models.PositiveSmallIntegerField(default=10,help_text="Countdown shown after starting, before question 1 opens.")
    auto_started_at=models.DateTimeField(null=True,blank=True,editable=False)
    question_order=models.CharField(max_length=16,choices=(("fixed","Fixed"),("random","Random")),default="fixed")
    answer_order=models.CharField(max_length=16,choices=(("fixed","Fixed"),("random","Randomized")),default="fixed")
    tie_break_method=models.CharField(max_length=80,default="correct_time_completion")
    theme_key=models.CharField(max_length=40,default="infrastructure")
    max_attempts=models.PositiveSmallIntegerField(default=1)
    current_question=models.ForeignKey("Question",on_delete=models.SET_NULL,null=True,blank=True,related_name="+")
    class Meta: ordering=("sequence",)
    def __str__(self): return f"Day {self.day} / {self.title}"

class Question(TimeStamped):
    quiz=models.ForeignKey(Quiz,on_delete=models.CASCADE,related_name="questions")
    number=models.PositiveSmallIntegerField()
    text=models.TextField()
    time_limit_seconds=models.PositiveSmallIntegerField()
    base_points=models.PositiveIntegerField(default=1000)
    host_note=models.TextField(blank=True)
    topic=models.CharField(max_length=120,blank=True)
    is_open=models.BooleanField(default=False)
    opened_at=models.DateTimeField(null=True,blank=True)
    closes_at=models.DateTimeField(null=True,blank=True)
    class Meta: ordering=("number",); constraints=[models.UniqueConstraint(fields=["quiz","number"],name="unique_quiz_question_number")]

    @property
    def window(self):
        return self.opened_at,self.closes_at

    def is_live(self,now=None):
        """Whether this question still accepts answers.

        The deadline is authoritative, not the is_open flag: a host who never
        pressed Close leaves is_open set long after the timer ran out, and the
        answer endpoint rejects those submissions. Display has to agree with it,
        or participants are shown buttons that cannot work.
        """
        from django.utils import timezone as _tz
        if not self.is_open: return False
        now=now or _tz.now()
        # An auto-run round schedules every question up front, so a question is
        # only live inside its own window, not merely because it has been opened.
        if self.opened_at and now<self.opened_at: return False
        if self.closes_at is None: return True
        return now<=self.closes_at

    def __str__(self): return f"{self.quiz.title} / Q{self.number}"

class AnswerChoice(TimeStamped):
    question=models.ForeignKey(Question,on_delete=models.CASCADE,related_name="choices")
    number=models.PositiveSmallIntegerField()
    text=models.TextField()
    is_correct=models.BooleanField(default=False)
    class Meta:
        ordering=("number",)
        constraints=[models.UniqueConstraint(fields=["question","number"],name="unique_question_choice_number"),models.CheckConstraint(condition=Q(number__gte=1)&Q(number__lte=4),name="choice_number_1_to_4")]

class QuizAttempt(TimeStamped):
    class State(models.TextChoices): ACTIVE="active","ACTIVE"; COMPLETE="complete","COMPLETE"; VOID="void","VOID"
    id=models.UUIDField(primary_key=True,default=uuid.uuid4,editable=False)
    participant=models.ForeignKey(Participant,on_delete=models.PROTECT,related_name="quiz_attempts")
    quiz=models.ForeignKey(Quiz,on_delete=models.PROTECT,related_name="attempts")
    authorised=models.BooleanField(default=True)
    state=models.CharField(max_length=20,choices=State.choices,default=State.ACTIVE)
    started_at=models.DateTimeField(auto_now_add=True)
    completed_at=models.DateTimeField(null=True,blank=True)
    official_score=models.PositiveIntegerField(default=0)
    correct_count=models.PositiveSmallIntegerField(default=0)
    total_response_ms=models.PositiveIntegerField(default=0)
    final_daily_rank=models.PositiveIntegerField(null=True,blank=True)
    class Meta: constraints=[models.UniqueConstraint(fields=["participant","quiz"],condition=Q(authorised=True)&~Q(state="void"),name="unique_authorised_attempt")]; indexes=[models.Index(fields=["quiz","official_score","correct_count"]),models.Index(fields=["participant","quiz"]),models.Index(fields=["authorised","state"])]

class QuizResponse(TimeStamped):
    id=models.UUIDField(primary_key=True,default=uuid.uuid4,editable=False)
    attempt=models.ForeignKey(QuizAttempt,on_delete=models.PROTECT,related_name="responses")
    question=models.ForeignKey(Question,on_delete=models.PROTECT,related_name="responses")
    selected_choice=models.ForeignKey(AnswerChoice,on_delete=models.PROTECT,related_name="responses")
    submission_id=models.UUIDField(unique=True)
    is_correct=models.BooleanField()
    base_points_awarded=models.PositiveIntegerField(default=0)
    speed_points_awarded=models.PositiveIntegerField(default=0)
    response_duration_ms=models.PositiveIntegerField()
    submitted_at=models.DateTimeField(auto_now_add=True)
    class Meta:
        constraints=[models.UniqueConstraint(fields=["attempt","question"],name="unique_attempt_question_response")]
        indexes=[models.Index(fields=["question","selected_choice"]),models.Index(fields=["question","submitted_at"])]

class ScoringRule(TimeStamped):
    code=models.SlugField(unique=True)
    category=models.CharField(max_length=40)
    points=models.IntegerField()
    is_active=models.BooleanField(default=True)
    description=models.CharField(max_length=240,blank=True)

class ScoreTransaction(TimeStamped):
    class Status(models.TextChoices): ACTIVE="active","ACTIVE"; VOID="void","VOID"; REVERSED="reversed","REVERSED"
    participant=models.ForeignKey(Participant,on_delete=models.PROTECT,related_name="xp_transactions")
    category=models.CharField(max_length=40)
    points=models.IntegerField()
    competition_points=models.IntegerField(default=0)
    learning_xp=models.IntegerField(default=0)
    source_type=models.CharField(max_length=40,blank=True)
    source_id=models.CharField(max_length=160,blank=True)
    reason=models.TextField(blank=True)
    status=models.CharField(max_length=20,choices=Status.choices,default=Status.ACTIVE)
    idempotency_key=models.CharField(max_length=160,unique=True)
    description=models.CharField(max_length=240,blank=True)
    actor=models.ForeignKey(settings.AUTH_USER_MODEL,on_delete=models.SET_NULL,null=True,blank=True)
    class Meta: indexes=[models.Index(fields=["participant","category","status"]),models.Index(fields=["source_type","source_id"])]

class Badge(TimeStamped):
    code=models.SlugField(unique=True); name=models.CharField(max_length=120); description=models.TextField(blank=True); icon=models.CharField(max_length=40,blank=True); rule=models.JSONField(default=dict,blank=True); is_active=models.BooleanField(default=True)
class ParticipantBadge(TimeStamped):
    participant=models.ForeignKey(Participant,on_delete=models.CASCADE,related_name="badge_awards"); badge=models.ForeignKey(Badge,on_delete=models.PROTECT,related_name="awards"); evidence=models.JSONField(default=dict,blank=True); awarded_at=models.DateTimeField(auto_now_add=True)
    class Meta: constraints=[models.UniqueConstraint(fields=["participant","badge"],name="unique_participant_badge")]
class Activity(TimeStamped):
    code=models.SlugField(unique=True)
    name=models.CharField(max_length=160)
    description=models.TextField(blank=True)
    day=models.PositiveSmallIntegerField(default=1)
    points=models.PositiveIntegerField(default=100)
    repeatable=models.BooleanField(default=False)
    is_active=models.BooleanField(default=True)
class ActivityCompletion(TimeStamped):
    participant=models.ForeignKey(Participant,on_delete=models.PROTECT,related_name="activity_completions"); activity=models.ForeignKey(Activity,on_delete=models.PROTECT,related_name="completions"); completed_at=models.DateTimeField(); external_id=models.CharField(max_length=160,blank=True); metadata=models.JSONField(default=dict,blank=True)
    class Meta: constraints=[models.UniqueConstraint(fields=["participant","activity"],name="unique_participant_activity")]

class PALIntegrationResult(TimeStamped):
    class Status(models.TextChoices): PENDING="pending","PENDING"; COMPLETE="complete","COMPLETE"; FAILED="failed","FAILED"
    participant=models.ForeignKey(Participant,on_delete=models.PROTECT,related_name="pal_results"); external_result_id=models.CharField(max_length=160,unique=True,null=True,blank=True); launch_nonce=models.UUIDField(default=uuid.uuid4,unique=True); status=models.CharField(max_length=20,choices=Status.choices,default=Status.PENDING); career_role=models.CharField(max_length=200,blank=True); ai_risk_score=models.DecimalField(max_digits=5,decimal_places=2,null=True,blank=True); career_hp=models.PositiveSmallIntegerField(null=True,blank=True); skill_gaps=models.JSONField(default=list,blank=True); recommendation_summary=models.TextField(blank=True); risk_card_url=models.URLField(blank=True); payload_checksum=models.CharField(max_length=64,blank=True); completed_at=models.DateTimeField(null=True,blank=True)

class GoogleRegistrationSource(TimeStamped):
    name=models.CharField(max_length=160); spreadsheet_id=models.CharField(max_length=240); worksheet_name=models.CharField(max_length=160); column_mappings=models.JSONField(default=dict); unique_identifiers=models.JSONField(default=list); enabled=models.BooleanField(default=True); last_sync_at=models.DateTimeField(null=True,blank=True); last_cursor=models.CharField(max_length=160,blank=True)
class SyncLog(TimeStamped):
    class Status(models.TextChoices): RUNNING="running","RUNNING"; SUCCESS="success","SUCCESS"; FAILED="failed","FAILED"
    source=models.ForeignKey(GoogleRegistrationSource,on_delete=models.CASCADE,related_name="sync_logs"); status=models.CharField(max_length=20,choices=Status.choices,default=Status.RUNNING); started_at=models.DateTimeField(auto_now_add=True); completed_at=models.DateTimeField(null=True,blank=True); rows_read=models.PositiveIntegerField(default=0); created_count=models.PositiveIntegerField(default=0); updated_count=models.PositiveIntegerField(default=0); rejected_count=models.PositiveIntegerField(default=0); errors=models.JSONField(default=list,blank=True)

class WinnerRecord(TimeStamped):
    class Status(models.TextChoices): PROVISIONAL="provisional","PROVISIONAL"; VERIFIED="verified","VERIFIED"; WINNER="winner","WINNER"; DISQUALIFIED="disqualified","DISQUALIFIED"
    participant=models.ForeignKey(Participant,on_delete=models.PROTECT,related_name="winner_records"); quiz=models.ForeignKey(Quiz,on_delete=models.PROTECT,null=True,blank=True); scope=models.CharField(max_length=20); calculated_rank=models.PositiveIntegerField(); final_rank=models.PositiveIntegerField(null=True,blank=True); score_snapshot=models.PositiveIntegerField(); correct_snapshot=models.PositiveIntegerField(default=0); response_ms_snapshot=models.PositiveIntegerField(default=0); status=models.CharField(max_length=20,choices=Status.choices,default=Status.PROVISIONAL)
    class Meta: constraints=[models.UniqueConstraint(fields=["participant","quiz","scope"],name="unique_winner_scope")]
class ScoreAdjustment(TimeStamped):
    attempt=models.ForeignKey(QuizAttempt,on_delete=models.PROTECT,related_name="adjustments"); admin=models.ForeignKey(settings.AUTH_USER_MODEL,on_delete=models.PROTECT); old_value=models.IntegerField(); new_value=models.IntegerField(); reason=models.TextField()
class AuditEvent(TimeStamped):
    actor=models.ForeignKey(settings.AUTH_USER_MODEL,on_delete=models.SET_NULL,null=True,blank=True); action=models.CharField(max_length=100); object_type=models.CharField(max_length=100); object_id=models.CharField(max_length=100); before=models.JSONField(default=dict,blank=True); after=models.JSONField(default=dict,blank=True); reason=models.TextField(blank=True); ip_address=models.GenericIPAddressField(null=True,blank=True)

class ExperienceTheme(TimeStamped):
    key=models.SlugField(unique=True)
    name=models.CharField(max_length=100)
    accent=models.CharField(max_length=12,default="#df1f26")
    background_treatment=models.CharField(max_length=40,default="grid")
    hero_label=models.CharField(max_length=120,blank=True)
    icon=models.CharField(max_length=40,blank=True)
    intro_copy=models.TextField(blank=True)
    result_language=models.CharField(max_length=120,blank=True)

class Experience(TimeStamped):
    class Type(models.TextChoices):
        QUIZ="quiz","Quiz"
        SESSION="session","Session"
        PAL_CHALLENGE="pal_challenge","PAL AI Jobs"
        EXPO_ACTIVITY="expo_activity","Expo Activity"
        AIOT_DEMO="aiot_demo","AIoT Demo"
        SURVEY="survey","Survey"
        CUSTOM_CHALLENGE="custom_challenge","Custom Challenge"
    class Status(models.TextChoices):
        DRAFT="draft","Draft"
        SCHEDULED="scheduled","Scheduled"
        LIVE="live","Live"
        PAUSED="paused","Paused"
        ENDED="ended","Ended"
        ARCHIVED="archived","Archived"
    title=models.CharField(max_length=240)
    slug=models.SlugField(unique=True)
    type=models.CharField(max_length=30,choices=Type.choices)
    description=models.TextField(blank=True)
    day=models.PositiveSmallIntegerField(default=1)
    start_at=models.DateTimeField(null=True,blank=True)
    end_at=models.DateTimeField(null=True,blank=True)
    status=models.CharField(max_length=20,choices=Status.choices,default=Status.DRAFT)
    visibility=models.CharField(max_length=20,choices=(("public","Public"),("registered","Registered only"),("hidden","Hidden")),default="registered")
    location=models.CharField(max_length=200,blank=True)
    points_enabled=models.BooleanField(default=False)
    completion_points=models.PositiveIntegerField(default=0)
    requires_registration=models.BooleanField(default=False)
    requires_checkin=models.BooleanField(default=False)
    show_on_dashboard=models.BooleanField(default=True)
    featured=models.BooleanField(default=False)
    cover_asset=models.CharField(max_length=240,blank=True)
    instructions=models.TextField(blank=True)
    theme=models.ForeignKey(ExperienceTheme,on_delete=models.SET_NULL,null=True,blank=True,related_name="experiences")
    quiz=models.OneToOneField(Quiz,on_delete=models.CASCADE,null=True,blank=True,related_name="experience")
    session=models.OneToOneField(Session,on_delete=models.CASCADE,null=True,blank=True,related_name="experience")
    activity=models.OneToOneField(Activity,on_delete=models.CASCADE,null=True,blank=True,related_name="experience")
    class Meta: ordering=("day","start_at","title"); indexes=[models.Index(fields=["status","show_on_dashboard","start_at"]),models.Index(fields=["type","day"])]
    def __str__(self): return self.title

class EventSettings(TimeStamped):
    event_name=models.CharField(max_length=240,default="CRDB × Predictive Analytics Lab Learning Week Experience")
    start_date=models.DateField(default="2026-09-07")
    end_date=models.DateField(default="2026-09-10")
    timezone=models.CharField(max_length=64,default="Africa/Dar_es_Salaam")
    registration_url=models.URLField(blank=True)
    programme_visible=models.BooleanField(default=True)
    leaderboard_visible=models.BooleanField(default=True)
    grand_prize_visible=models.BooleanField(default=False)
    qr_behavior=models.CharField(max_length=40,default="persistent_pass")
    support_contact=models.CharField(max_length=200,blank=True)
    pal_enabled=models.BooleanField(default=True)
    google_forms_enabled=models.BooleanField(default=False)
    self_registration_enabled=models.BooleanField(default=True,help_text="Let people join by entering their email, without being pre-loaded from a spreadsheet or Google Form.")
    allowed_email_domains=models.CharField(max_length=400,blank=True,help_text="Comma-separated domains allowed to self-register, e.g. crdbbank.co.tz. Leave blank to accept any email address.")
    self_registration_collects_department=models.BooleanField(default=True,help_text="Ask for department during self-registration. It drives the analytics breakdown.")

    def allowed_domains(self):
        return [part.strip().lower().lstrip("@") for part in self.allowed_email_domains.split(",") if part.strip()]

    def email_is_allowed(self,email):
        domains=self.allowed_domains()
        if not domains: return True
        return (email or "").rsplit("@",1)[-1].strip().lower() in domains
    def save(self,*args,**kwargs):
        if not self.pk and EventSettings.objects.exists():
            self.pk=EventSettings.objects.first().pk
        return super().save(*args,**kwargs)
    @classmethod
    def load(cls): return cls.objects.first() or cls()
