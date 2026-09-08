from celery import shared_task
from django.core.management import call_command
@shared_task(autoretry_for=(Exception,),retry_backoff=True,max_retries=5)
def sync_google_source(source_id):
 call_command("sync_google_registrations",source=source_id)
 return source_id
