import csv
import logging
import os
import tempfile
from django.contrib import messages
from django.contrib.auth import logout
from django.contrib.auth.decorators import user_passes_test
from django.conf import settings
from django.contrib.auth.views import LoginView
from django.core.exceptions import ValidationError
from django.core.paginator import Paginator
from django.db import transaction
from django.db.models import Avg, Count, Max, Q, Sum
from django.http import HttpResponse, StreamingHttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.template.defaultfilters import slugify
from django.urls import reverse, reverse_lazy
from django.utils import timezone
from django.views.decorators.http import require_POST
from .forms import ActivityForm, BadgeForm, EventSettingsForm, GoogleSourceForm, QuestionForm, QuizForm, ScoringRuleForm, SessionForm
from .importers import import_activity_workbook, import_participant_workbook, import_questions_into_quiz, import_session_workbook, parse_quiz_workbook, select_quiz_questions
from .models import Activity, AnswerChoice, Attendance, AuditEvent, Badge, EventSettings, Experience, GoogleRegistrationSource, Participant, Question, Quiz, QuizAttempt, ScoringRule, Session, SyncLog, WinnerRecord
from django_ratelimit.core import is_ratelimited

from .services import finalize_daily_ranking
from .workbooks import TEMPLATES, template_bytes

logger = logging.getLogger(__name__)


def quiz_has_responses(quiz):
    """A round that has already been played cannot have its questions replaced."""
    return Question.objects.filter(quiz=quiz, responses__isnull=False).exists()


class ControlLoginView(LoginView):
    template_name = "control/login.html"
    redirect_authenticated_user = True

    def get_success_url(self):
        return self.get_redirect_url() or str(reverse_lazy("control-room"))

    def post(self, request, *args, **kwargs):
        if settings.RATELIMIT_ENABLE and is_ratelimited(
            request, group="control-login", key="ip", rate=settings.RATELIMIT_LOGIN, method="POST", increment=True
        ):
            messages.error(request, "TOO MANY SIGN-IN ATTEMPTS / WAIT A MINUTE AND TRY AGAIN")
            return self.render_to_response(self.get_context_data(form=self.get_form()), status=429)
        return super().post(request, *args, **kwargs)

    def form_invalid(self, form):
        logger.warning("Control Room sign-in failed from %s", self.request.META.get("REMOTE_ADDR"))
        return super().form_invalid(form)


def control_required(view):
    return user_passes_test(lambda user: user.is_active and user.is_staff, login_url="control-login")(view)


def audit(request, action, obj, before=None, after=None, reason=""):
    AuditEvent.objects.create(
        actor=request.user,
        action=action,
        object_type=obj.__class__.__name__,
        object_id=str(obj.pk),
        before=before or {},
        after=after or {},
        reason=reason,
        ip_address=request.META.get("REMOTE_ADDR"),
    )


def unique_slug(model, value):
    base = slugify(value) or "experience"
    candidate, number = base, 2
    while model.objects.filter(slug=candidate).exists():
        candidate = f"{base}-{number}"
        number += 1
    return candidate


@control_required
def control_logout(request):
    logout(request)
    return redirect("control-login")


@control_required
def overview(request):
    today = timezone.localdate()
    sessions = Session.objects.annotate(
        registration_count=Count("registrations", distinct=True),
        attendance_count=Count("attendance_records", distinct=True),
    ).order_by("starts_at")
    stats = {
        "registered": Participant.objects.filter(is_active=True).count(),
        "checked_in_today": Attendance.objects.filter(checked_in_at__date=today).count(),
        "quiz_participants": QuizAttempt.objects.filter(authorised=True).values("participant_id").distinct().count(),
        "pal_completed": Participant.objects.filter(pal_results__status="complete").distinct().count(),
    }
    quizzes = Quiz.objects.annotate(question_count=Count("questions", distinct=True)).order_by("sequence")
    return render(request, "control/overview.html", {"stats": stats, "sessions": sessions[:8], "quizzes": quizzes, "now": timezone.now(), "experiences": Experience.objects.select_related("quiz", "session", "activity")[:8]})


@control_required
def participants(request):
    query = request.GET.get("q", "").strip()
    # Both counts must be distinct: joining attendance and attempts in one query
    # multiplies the rows of each, which silently inflates an undistinct Count.
    rows = Participant.objects.annotate(
        attended=Count("attendance_records", distinct=True),
        attempts=Count("quiz_attempts", distinct=True),
    ).order_by("full_name")
    if query:
        rows = rows.filter(Q(full_name__icontains=query) | Q(staff_id__icontains=query) | Q(email__icontains=query) | Q(department__icontains=query))
    page = Paginator(rows, 100).get_page(request.GET.get("page"))
    return render(request, "control/participants.html", {"page": page, "participants": page.object_list, "total": page.paginator.count, "query": query})


@control_required
def programme_sessions(request):
    return render(request, "control/sessions.html", {"sessions": Session.objects.annotate(registration_count=Count("registrations"), attendance_count=Count("attendance_records", distinct=True)).order_by("starts_at")})


@control_required
def session_form(request, pk=None):
    instance = get_object_or_404(Session, pk=pk) if pk else None
    form = SessionForm(request.POST or None, instance=instance)
    if request.method == "POST" and form.is_valid():
        obj = form.save()
        Experience.objects.update_or_create(
            session=obj,
            defaults={"title": obj.title, "slug": unique_slug(Experience, obj.title) if not hasattr(obj, "experience") else obj.experience.slug, "type": Experience.Type.SESSION, "description": obj.audience, "day": obj.day, "start_at": obj.starts_at, "end_at": obj.ends_at, "status": Experience.Status.SCHEDULED if obj.is_active else Experience.Status.DRAFT, "location": obj.location, "requires_registration": True, "requires_checkin": True, "show_on_dashboard": True},
        )
        audit(request, "session.updated" if instance else "session.created", obj, after={"title": obj.title, "starts_at": obj.starts_at.isoformat()})
        messages.success(request, "PROGRAMME / SESSION SAVED")
        return redirect("control-sessions")
    return render(request, "control/form.html", {"form": form, "title": "EDIT SESSION" if instance else "CREATE SESSION", "kicker": "PROGRAMME / SESSION", "submit": "SAVE SESSION"})


@control_required
def experiences(request):
    return render(request, "control/experiences.html", {"experiences": Experience.objects.select_related("quiz", "session", "activity", "theme")})


@control_required
def create_experience(request):
    return render(request, "control/create_experience.html")


@control_required
def quizzes(request):
    return render(request, "control/quizzes.html", {"quizzes": Quiz.objects.annotate(question_count=Count("questions"), player_count=Count("attempts", distinct=True))})


@control_required
@transaction.atomic
def quiz_form(request, pk=None):
    instance = get_object_or_404(Quiz, pk=pk) if pk else None
    form = QuizForm(request.POST or None, instance=instance)
    if request.method == "POST" and form.is_valid():
        quiz = form.save(commit=False)
        if not quiz.pk:
            quiz.sequence = (Quiz.objects.aggregate(value=Max("sequence"))["value"] or 0) + 1
        quiz.save()
        start_at = end_at = None
        if quiz.event_date and quiz.start_time:
            start_at = timezone.make_aware(timezone.datetime.combine(quiz.event_date, quiz.start_time))
        if quiz.event_date and quiz.end_time:
            end_at = timezone.make_aware(timezone.datetime.combine(quiz.event_date, quiz.end_time))
        existing = Experience.objects.filter(quiz=quiz).first()
        Experience.objects.update_or_create(
            quiz=quiz,
            defaults={"title": quiz.title, "slug": existing.slug if existing else unique_slug(Experience, quiz.title), "type": Experience.Type.QUIZ, "description": quiz.participant_description, "day": quiz.day, "start_at": start_at, "end_at": end_at, "status": Experience.Status.DRAFT, "points_enabled": True, "show_on_dashboard": True, "featured": True},
        )
        audit(request, "quiz.updated" if instance else "quiz.created", quiz, after={"title": quiz.title, "day": quiz.day})
        messages.success(request, "QUIZ / BASICS SAVED — ADD QUESTIONS")
        return redirect("control-quiz-detail", pk=quiz.pk)
    return render(request, "control/form.html", {"form": form, "title": "EDIT QUIZ" if instance else "CREATE QUIZ", "kicker": "EXPERIENCES / QUIZ / STEP 1", "submit": "SAVE & CONTINUE"})


@control_required
def quiz_detail(request, pk):
    quiz = get_object_or_404(Quiz.objects.prefetch_related("questions__choices"), pk=pk)
    maximum = quiz.questions.aggregate(total=Sum("base_points"))["total"] or 0
    return render(request, "control/quiz_detail.html", {"quiz": quiz, "maximum": maximum})


@control_required
@transaction.atomic
def question_form(request, quiz_id, question_id=None):
    quiz = get_object_or_404(Quiz, pk=quiz_id)
    question = get_object_or_404(Question.objects.prefetch_related("choices"), pk=question_id, quiz=quiz) if question_id else None
    initial = {}
    if question:
        initial = {"text": question.text, "time_limit_seconds": question.time_limit_seconds, "base_points": question.base_points, "host_note": question.host_note, "topic": question.topic}
        for choice in question.choices.all():
            initial[f"answer_{choice.number}"] = choice.text
            if choice.is_correct:
                initial["correct_answer"] = choice.number
    form = QuestionForm(request.POST or None, initial=initial)
    if request.method == "POST" and form.is_valid():
        if question is None:
            question = Question(quiz=quiz, number=(quiz.questions.aggregate(value=Max("number"))["value"] or 0) + 1)
        question.text = form.cleaned_data["text"]
        question.time_limit_seconds = form.cleaned_data["time_limit_seconds"]
        question.base_points = form.cleaned_data["base_points"]
        question.host_note = form.cleaned_data["host_note"]
        question.topic = form.cleaned_data["topic"]
        question.save()
        question.choices.all().delete()
        AnswerChoice.objects.bulk_create([AnswerChoice(question=question, number=n, text=form.cleaned_data[f"answer_{n}"], is_correct=form.cleaned_data["correct_answer"] == n) for n in range(1, 5)])
        audit(request, "question.updated" if question_id else "question.created", question, after={"number": question.number, "points": question.base_points})
        messages.success(request, f"QUESTION {question.number:02d} / SAVED")
        return redirect("control-quiz-detail", pk=quiz.pk)
    return render(request, "control/question_form.html", {"form": form, "quiz": quiz, "question": question})


@control_required
def quiz_preview(request, pk):
    quiz = get_object_or_404(Quiz.objects.prefetch_related("questions__choices"), pk=pk)
    return render(request, "control/quiz_preview.html", {"quiz": quiz})


@control_required
@require_POST
def quiz_publish(request, pk):
    quiz = get_object_or_404(Quiz.objects.prefetch_related("questions__choices"), pk=pk)
    questions = list(quiz.questions.all())
    errors = []
    if len(questions) != 10:
        errors.append("Competition quizzes require exactly 10 questions before publishing.")
    for question in questions:
        choices = list(question.choices.all())
        if len(choices) != 4 or sum(1 for choice in choices if choice.is_correct) != 1:
            errors.append(f"Question {question.number:02d} must have four answers and one correct answer.")
    if errors:
        for error in errors:
            messages.error(request, error)
        return redirect("control-quiz-detail", pk=quiz.pk)
    quiz.state = Quiz.State.SCHEDULED
    quiz.save(update_fields=["state", "updated_at"])
    Experience.objects.filter(quiz=quiz).update(status=Experience.Status.SCHEDULED)
    audit(request, "quiz.published", quiz, after={"state": quiz.state, "questions": 10})
    messages.success(request, "QUIZ / SCHEDULED")
    return redirect("control-quiz-detail", pk=quiz.pk)


@control_required
def quiz_import(request, pk):
    quiz = get_object_or_404(Quiz, pk=pk)
    if request.method == "POST" and request.FILES.get("workbook"):
        try:
            path = saved_upload(request.FILES["workbook"])
        except ValidationError as exc:
            messages.error(request, f"IMPORT REJECTED / {exc.messages[0]}")
            return redirect("control-quiz-import", pk=quiz.pk)
        try:
            groups = parse_quiz_workbook(path)
            rows = select_quiz_questions(groups, quiz)
            if request.POST.get("action") == "preview":
                return render(request, "control/import_questions.html", {"quiz": quiz, "preview": {"detected": len(rows), "valid": len(rows), "errors": 0}, "locked": quiz_has_responses(quiz)})
            result = import_questions_into_quiz(quiz, path)
            audit(request, "questions.imported", quiz, after={"questions": result["questions"]})
            messages.success(request, f"IMPORT COMPLETE / {result['questions']} QUESTIONS")
        except ValidationError as exc:
            for message in exc.messages[:25]:
                messages.error(request, f"IMPORT REJECTED / {message}")
        except Exception as exc:
            logger.exception("Question import failed for quiz %s", quiz.pk)
            messages.error(request, f"IMPORT FAILED / {exc}")
        finally:
            if os.path.exists(path):
                os.unlink(path)
        return redirect("control-quiz-detail", pk=quiz.pk)
    return render(request, "control/import_questions.html", {"quiz": quiz, "locked": quiz_has_responses(quiz)})


@control_required
def activities(request):
    return render(request, "control/activities.html", {"activities": Activity.objects.annotate(completion_count=Count("completions"))})


@control_required
@transaction.atomic
def activity_form(request, pk=None, experience_type=Experience.Type.EXPO_ACTIVITY):
    instance = get_object_or_404(Activity, pk=pk) if pk else None
    existing_experience = Experience.objects.filter(activity=instance).first() if instance else None
    if existing_experience:
        experience_type = existing_experience.type
    allowed_types = {Experience.Type.EXPO_ACTIVITY, Experience.Type.AIOT_DEMO, Experience.Type.CUSTOM_CHALLENGE}
    if experience_type not in allowed_types:
        experience_type = Experience.Type.EXPO_ACTIVITY
    form = ActivityForm(request.POST or None, instance=instance)
    if request.method == "POST" and form.is_valid():
        activity = form.save()
        existing = Experience.objects.filter(activity=activity).first()
        Experience.objects.update_or_create(activity=activity, defaults={"title": activity.name, "slug": existing.slug if existing else unique_slug(Experience, activity.name), "type": experience_type, "description": activity.description, "day": activity.day, "status": Experience.Status.SCHEDULED if activity.is_active else Experience.Status.DRAFT, "points_enabled": True, "completion_points": activity.points, "requires_checkin": True, "show_on_dashboard": form.cleaned_data["show_on_dashboard"]})
        audit(request, "activity.updated" if instance else "activity.created", activity, after={"name": activity.name, "points": activity.points})
        messages.success(request, f"{Experience.Type(experience_type).label.upper()} / SAVED")
        return redirect("control-activities")
    label = Experience.Type(experience_type).label.upper()
    return render(request, "control/form.html", {"form": form, "title": f"EDIT {label}" if instance else f"CREATE {label}", "kicker": f"EXPERIENCES / {label}", "submit": "SAVE EXPERIENCE"})


@control_required
def rewards(request):
    return render(request, "control/rewards.html", {"badges": Badge.objects.all(), "rules": ScoringRule.objects.all(), "badge_form": BadgeForm(), "rule_form": ScoringRuleForm()})


@control_required
@require_POST
def reward_create(request, kind):
    form = BadgeForm(request.POST) if kind == "badge" else ScoringRuleForm(request.POST)
    if form.is_valid():
        obj = form.save()
        audit(request, f"{kind}.created", obj)
        messages.success(request, f"{kind.upper()} / SAVED")
    else:
        messages.error(request, f"{kind.upper()} / CHECK REQUIRED FIELDS")
    return redirect("control-rewards")


@control_required
def integrations(request):
    return render(request, "control/integrations.html", {"sources": GoogleRegistrationSource.objects.prefetch_related("sync_logs"), "form": GoogleSourceForm()})


@control_required
@require_POST
def integration_create(request):
    form = GoogleSourceForm(request.POST)
    if form.is_valid():
        source = form.save()
        audit(request, "google_source.created", source)
        messages.success(request, "GOOGLE FORM SOURCE / SAVED")
    else:
        messages.error(request, "SOURCE / INVALID CONFIGURATION")
    return redirect("control-integrations")


@control_required
def analytics(request):
    departments = Participant.objects.values("department").annotate(total=Count("id"), attended=Count("attendance_records", distinct=True)).order_by("-total")[:20]
    session_rows = Session.objects.annotate(registered=Count("registrations", distinct=True), attended=Count("attendance_records", distinct=True)).order_by("starts_at")
    quiz_rows = Quiz.objects.annotate(players=Count("attempts", distinct=True), average=Avg("attempts__official_score"), top=Max("attempts__official_score"))
    return render(request, "control/analytics.html", {"departments": departments, "sessions": session_rows, "quizzes": quiz_rows})


@control_required
def event_settings(request):
    instance = EventSettings.load()
    form = EventSettingsForm(request.POST or None, instance=instance)
    if request.method == "POST" and form.is_valid():
        obj = form.save()
        audit(request, "event_settings.updated", obj)
        messages.success(request, "EVENT SETTINGS / SAVED")
        return redirect("control-settings")
    return render(request, "control/form.html", {"form": form, "title": "EVENT SETTINGS", "kicker": "SYSTEM / CONFIGURATION", "submit": "SAVE SETTINGS"})


@control_required
def audit_log(request):
    return render(request, "control/audit.html", {"events": AuditEvent.objects.select_related("actor").order_by("-created_at")[:300]})


@control_required
def competition(request):
    winners = WinnerRecord.objects.select_related("participant", "quiz").order_by("scope", "calculated_rank")
    attempts = QuizAttempt.objects.filter(authorised=True, quiz__prize_eligible=True).select_related("participant", "quiz").order_by("quiz__day", "-official_score", "-correct_count", "total_response_ms")
    return render(request, "control/competition.html", {"winners": winners, "attempts": attempts, "quizzes": Quiz.objects.filter(prize_eligible=True)})


@control_required
@require_POST
def generate_results(request, quiz_id):
    quiz = get_object_or_404(Quiz, pk=quiz_id)
    rows = finalize_daily_ranking(quiz)
    audit(request, "results.generated", quiz, after={"ranked_attempts": len(rows)})
    messages.success(request, f"RESULTS / {len(rows)} ATTEMPTS RANKED / PROVISIONAL")
    return redirect("control-competition")


@control_required
@require_POST
def winner_action(request, pk, action):
    winner = get_object_or_404(WinnerRecord, pk=pk)
    allowed = {"verify": WinnerRecord.Status.VERIFIED, "winner": WinnerRecord.Status.WINNER, "disqualify": WinnerRecord.Status.DISQUALIFIED, "restore": WinnerRecord.Status.PROVISIONAL}
    if action not in allowed:
        messages.error(request, "INVALID WINNER ACTION")
        return redirect("control-competition")
    reason = request.POST.get("reason", "").strip()
    if action == "disqualify" and not reason:
        messages.error(request, "DISQUALIFICATION REQUIRES A REASON")
        return redirect("control-competition")
    old = winner.status
    winner.status = allowed[action]
    winner.save(update_fields=["status", "updated_at"])
    audit(request, f"winner.{action}", winner, before={"status": old}, after={"status": winner.status}, reason=reason)
    messages.success(request, f"WINNER STATUS / {winner.get_status_display()}")
    return redirect("control-competition")


class _Echo:
    def write(self, value):
        return value


@control_required
def export_participants(request):
    header = ("staff_id", "full_name", "email", "department", "job_role", "pass_number", "is_active")
    rows = Participant.objects.order_by("full_name").values_list("staff_id", "full_name", "email", "department", "job_role", "pass_number", "is_active").iterator(chunk_size=500)

    def stream():
        writer = csv.writer(_Echo())
        yield writer.writerow(header)
        for row in rows:
            yield writer.writerow(["" if value is None else value for value in row])

    audit(request, "participants.exported", request.user, after={"count": Participant.objects.count()})
    response = StreamingHttpResponse(stream(), content_type="text/csv")
    response["Content-Disposition"] = 'attachment; filename="learning-week-participants.csv"'
    return response


ALLOWED_UPLOAD_SUFFIXES = (".xlsx", ".csv")


def sync_activity_experiences():
    """Give every activity its participant-facing Experience envelope.

    Activities created through the form get one on save; ones arriving by
    spreadsheet need the same treatment or they never reach a dashboard.
    """
    for activity in Activity.objects.filter(experience__isnull=True):
        Experience.objects.create(
            activity=activity,
            title=activity.name,
            slug=unique_slug(Experience, activity.name),
            type=Experience.Type.EXPO_ACTIVITY,
            description=activity.description,
            day=activity.day,
            status=Experience.Status.SCHEDULED if activity.is_active else Experience.Status.DRAFT,
            points_enabled=True,
            completion_points=activity.points,
            requires_checkin=True,
            show_on_dashboard=True,
        )


def saved_upload(upload):
    """Write an uploaded spreadsheet to a temp file and return its path."""
    suffix = os.path.splitext(upload.name)[1].lower()
    if suffix not in ALLOWED_UPLOAD_SUFFIXES:
        raise ValidationError("Upload an .xlsx or .csv file saved from the template.")
    with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as handle:
        for chunk in upload.chunks():
            handle.write(chunk)
        return handle.name


def run_spreadsheet_import(request, importer, *, field="workbook"):
    """Shared upload plumbing: save, import, report every rejected row, clean up.

    Returns the importer summary, or None when nothing was imported. Row-level
    problems are surfaced as messages so an administrator can fix the file
    without reading a traceback.
    """
    upload = request.FILES.get(field)
    if not upload:
        messages.error(request, "SELECT A FILE / NO SPREADSHEET WAS ATTACHED")
        return None
    path = None
    try:
        path = saved_upload(upload)
        return importer(path)
    except ValidationError as exc:
        for message in exc.messages[:25]:
            messages.error(request, f"IMPORT REJECTED / {message}")
        if len(exc.messages) > 25:
            messages.error(request, f"IMPORT REJECTED / {len(exc.messages) - 25} further rows also need attention.")
    except Exception as exc:
        logger.exception("Spreadsheet import failed")
        messages.error(request, f"IMPORT FAILED / {exc}")
    finally:
        if path and os.path.exists(path):
            os.unlink(path)
    return None


@control_required
def download_template(request, key):
    try:
        filename, payload = template_bytes(key)
    except KeyError:
        messages.error(request, "UNKNOWN TEMPLATE")
        return redirect("control-room")
    response = HttpResponse(payload, content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
    response["Content-Disposition"] = f'attachment; filename="{filename}"'
    return response


@control_required
def import_participants(request):
    if request.method == "POST":
        summary = run_spreadsheet_import(request, import_participant_workbook)
        if summary:
            audit(request, "participants.imported", request.user, after=summary)
            messages.success(request, f"IMPORT COMPLETE / {summary['created']} ADDED / {summary['updated']} UPDATED")
            return redirect("control-participants")
    return render(request, "control/import_spreadsheet.html", {
        "heading": "IMPORT PARTICIPANTS",
        "kicker": "IDENTITY / REGISTRATION",
        "template_key": "participants",
        "back_url": reverse("control-participants"),
        "blurb": "One row per registered person. Rows are matched on staff ID, then email, so re-importing a corrected file updates people instead of duplicating them.",
    })


@control_required
def import_sessions(request):
    if request.method == "POST":
        summary = run_spreadsheet_import(request, import_session_workbook)
        if summary:
            audit(request, "sessions.imported", request.user, after=summary)
            messages.success(request, f"IMPORT COMPLETE / {summary['created']} ADDED / {summary['updated']} UPDATED")
            return redirect("control-sessions")
    return render(request, "control/import_spreadsheet.html", {
        "heading": "IMPORT PROGRAMME SESSIONS",
        "kicker": "PROGRAMME / TIMETABLE",
        "template_key": "programme-sessions",
        "back_url": reverse("control-sessions"),
        "blurb": "One row per session. The source_key column is the permanent identifier: re-importing the same key updates that session in place.",
    })


@control_required
def import_activities(request):
    if request.method == "POST":
        summary = run_spreadsheet_import(request, import_activity_workbook)
        if summary:
            sync_activity_experiences()
            audit(request, "activities.imported", request.user, after=summary)
            messages.success(request, f"IMPORT COMPLETE / {summary['created']} ADDED / {summary['updated']} UPDATED")
            return redirect("control-activities")
    return render(request, "control/import_spreadsheet.html", {
        "heading": "IMPORT INTERACTIVE ACTIVITIES",
        "kicker": "EXPERIENCES / GAMES & STANDS",
        "template_key": "activities",
        "back_url": reverse("control-activities"),
        "blurb": "Expo games, AIoT demos and stand challenges. The code column is the permanent identifier and is what a stand device sends when it marks a participant complete.",
    })
