from django.core.management.base import BaseCommand,CommandError
from django.core.exceptions import ValidationError
from core.importers import import_quiz_workbook
class Command(BaseCommand):
 help="Import the exact official quiz spreadsheet; aborts on any malformed row."
 def add_arguments(self,parser): parser.add_argument("workbook")
 def handle(self,*args,**opts):
  try: summary=import_quiz_workbook(opts["workbook"])
  except ValidationError as exc: raise CommandError("\n".join(exc.messages))
  self.stdout.write(self.style.SUCCESS(f"Imported {summary['quizzes']} quizzes / {summary['questions']} questions"))
