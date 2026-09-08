from django.contrib import admin
from . import models

@admin.register(models.Participant)
class ParticipantAdmin(admin.ModelAdmin):
    list_display=("full_name","staff_id","email","department","pass_number","is_active")
    search_fields=("full_name","staff_id","email","department","pass_number")
    list_filter=("department","is_active")
    readonly_fields=("id","qr_token","pass_number","created_at","updated_at")
@admin.register(models.Session)
class SessionAdmin(admin.ModelAdmin): list_display=("day","starts_at","title","facilitator","format","is_active"); list_filter=("day","format","is_active"); search_fields=("title","facilitator")
@admin.register(models.Attendance)
class AttendanceAdmin(admin.ModelAdmin): list_display=("participant","session","checked_in_at","checked_in_by","is_override"); list_filter=("session__day","is_override"); search_fields=("participant__full_name","participant__staff_id")
@admin.register(models.Quiz)
class QuizAdmin(admin.ModelAdmin): list_display=("day","title","state","prize_eligible","speed_bonus_enabled")
@admin.register(models.Question)
class QuestionAdmin(admin.ModelAdmin): list_display=("quiz","number","time_limit_seconds","base_points","is_open"); list_filter=("quiz",)
@admin.register(models.QuizAttempt)
class QuizAttemptAdmin(admin.ModelAdmin): list_display=("participant","quiz","official_score","correct_count","total_response_ms","authorised","state"); list_filter=("quiz","authorised","state"); search_fields=("participant__full_name","participant__staff_id")
@admin.register(models.QuizResponse)
class QuizResponseAdmin(admin.ModelAdmin): list_display=("attempt","question","is_correct","base_points_awarded","response_duration_ms","submitted_at"); readonly_fields=[f.name for f in models.QuizResponse._meta.fields]
@admin.register(models.ScoreTransaction)
class ScoreTransactionAdmin(admin.ModelAdmin): list_display=("participant","category","points","description","created_at"); list_filter=("category",); readonly_fields=("idempotency_key","created_at","updated_at")
for model in (models.SessionRegistration,models.AnswerChoice,models.ScoringRule,models.Badge,models.ParticipantBadge,models.Activity,models.ActivityCompletion,models.PALIntegrationResult,models.GoogleRegistrationSource,models.SyncLog,models.WinnerRecord,models.ScoreAdjustment,models.AuditEvent):
    admin.site.register(model)
admin.site.site_header="CRDB Learning Week / Control Room"
admin.site.site_title="CRDB Learning Week"
admin.site.index_title="Operations"
