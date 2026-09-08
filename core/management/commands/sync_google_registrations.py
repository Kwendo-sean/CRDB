from django.core.management.base import BaseCommand,CommandError
from django.utils import timezone
from core.google_sheets import fetch_google_sheet_rows
from core.integrations import sync_registration_rows
from core.models import GoogleRegistrationSource,SyncLog
class Command(BaseCommand):
 help="Synchronise one configured official Google Sheet registration source."
 def add_arguments(self,parser): parser.add_argument("--source",type=int,required=True); parser.add_argument("--credentials")
 def handle(self,*args,**opts):
  try: source=GoogleRegistrationSource.objects.get(pk=opts["source"],enabled=True)
  except GoogleRegistrationSource.DoesNotExist: raise CommandError("Enabled source not found")
  log=SyncLog.objects.create(source=source)
  try:
   rows=fetch_google_sheet_rows(source,opts.get("credentials")); summary=sync_registration_rows(source,rows)
   log.status="success"; log.rows_read=len(rows); log.created_count=summary["created"]; log.updated_count=summary["updated"]; log.rejected_count=summary["rejected"]; log.errors=summary["errors"]
   source.last_sync_at=timezone.now(); source.save(update_fields=["last_sync_at","updated_at"])
  except Exception as exc:
   log.status="failed"; log.errors=[{"error":str(exc)}]; raise CommandError(str(exc))
  finally: log.completed_at=timezone.now(); log.save()
  self.stdout.write(self.style.SUCCESS(f"Rows {log.rows_read} / created {log.created_count} / updated {log.updated_count} / rejected {log.rejected_count}"))
