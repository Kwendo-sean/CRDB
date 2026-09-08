import hashlib, hmac, json
from urllib.parse import urlencode
from django.conf import settings
from django.core import signing
from django.db import transaction
from django.utils import timezone
from .models import PALIntegrationResult, Participant, ScoreTransaction

def build_pal_launch(participant):
    result=PALIntegrationResult.objects.create(participant=participant)
    payload={"sub":str(participant.id),"nonce":str(result.launch_nonce),"iss":settings.PAL_ISSUER,"aud":settings.PAL_AUDIENCE}
    signed=signing.dumps(payload,salt="pal-launch",compress=True)
    return f"{settings.PAL_LAUNCH_URL}?{urlencode({'token':signed})}"

def verify_callback_signature(body,signature):
    expected=hmac.new(settings.PAL_CALLBACK_SECRET.encode(),body,hashlib.sha256).hexdigest()
    return hmac.compare_digest(expected,signature or "")

@transaction.atomic
def apply_pal_callback(payload,body):
    result=PALIntegrationResult.objects.select_for_update().get(participant_id=payload["subject"],launch_nonce=payload["nonce"])
    external_id=str(payload["external_result_id"])
    existing=PALIntegrationResult.objects.filter(external_result_id=external_id).exclude(pk=result.pk).first()
    if existing: return existing
    result.external_result_id=external_id; result.status=payload.get("status","complete")
    result.career_role=str(payload.get("career_role", ""))[:200]
    result.career_hp=payload.get("career_hp")
    result.ai_risk_score=payload.get("ai_risk_score")
    result.skill_gaps=payload.get("skill_gaps",[])[:20]
    result.recommendation_summary=str(payload.get("recommendation_summary",""))[:4000]
    result.risk_card_url=str(payload.get("risk_card_url",""))[:200]
    result.payload_checksum=hashlib.sha256(body).hexdigest()
    if result.status=="complete": result.completed_at=timezone.now()
    result.save()
    if result.status=="complete": ScoreTransaction.objects.get_or_create(participant=result.participant,category="pal",idempotency_key=f"pal:{external_id}",defaults={"points":500,"learning_xp":500,"source_type":"pal_result","source_id":str(result.pk),"description":"PAL AI Jobs completion"})
    return result

def sync_registration_rows(source,rows):
    created=updated=rejected=0; errors=[]
    mapping=source.column_mappings
    for number,row in enumerate(rows,start=2):
        staff=str(row.get(mapping.get("staff_id","staff_id"),"") or "").strip().upper() or None
        email=str(row.get(mapping.get("email","email"),"") or "").strip().lower() or None
        if not staff and not email: rejected+=1; errors.append({"row":number,"error":"missing_identifier"}); continue
        by_staff=Participant.objects.filter(staff_id=staff).first() if staff else None
        by_email=Participant.objects.filter(email=email).first() if email else None
        if by_staff and by_email and by_staff.pk!=by_email.pk: rejected+=1; errors.append({"row":number,"error":"identity_conflict"}); continue
        participant=by_staff or by_email
        values={"full_name":str(row.get(mapping.get("full_name","full_name"),"")).strip(),"department":str(row.get(mapping.get("department","department"),"") or "").strip(),"job_role":str(row.get(mapping.get("job_role","job_role"),"") or "").strip(),"phone":str(row.get(mapping.get("phone","phone"),"") or "").strip(),"staff_id":staff,"email":email}
        if not values["full_name"]: rejected+=1; errors.append({"row":number,"error":"missing_name"}); continue
        if participant:
            for k,v in values.items():
                if v: setattr(participant,k,v)
            participant.save(); updated+=1
        else: Participant.objects.create(**values); created+=1
    return {"created":created,"updated":updated,"rejected":rejected,"errors":errors}
