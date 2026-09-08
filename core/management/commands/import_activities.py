from django.core.management.base import BaseCommand,CommandError
from django.core.exceptions import ValidationError
from core.control_views import sync_activity_experiences
from core.importers import import_activity_workbook

class Command(BaseCommand):
    help="Import interactive games, expo stands and AIoT demos; aborts on malformed rows."
    def add_arguments(self,parser): parser.add_argument("workbook")
    def handle(self,*args,**opts):
        try: summary=import_activity_workbook(opts["workbook"])
        except ValidationError as exc: raise CommandError("\n".join(exc.messages))
        sync_activity_experiences()
        self.stdout.write(self.style.SUCCESS(f"Activities loaded: {summary['created']} added, {summary['updated']} updated"))
