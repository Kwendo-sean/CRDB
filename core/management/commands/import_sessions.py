from django.core.management.base import BaseCommand,CommandError
from django.core.exceptions import ValidationError
from core.importers import import_session_workbook

class Command(BaseCommand):
    help="Import exact official programme sessions; aborts on malformed rows."
    def add_arguments(self,parser): parser.add_argument("workbook")
    def handle(self,*args,**opts):
        try: summary=import_session_workbook(opts["workbook"])
        except ValidationError as exc: raise CommandError("\n".join(exc.messages))
        self.stdout.write(self.style.SUCCESS(f"Imported or updated {summary['sessions']} sessions"))
