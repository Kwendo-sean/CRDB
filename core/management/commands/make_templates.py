from pathlib import Path

from django.core.management.base import BaseCommand

from core.workbooks import TEMPLATES


class Command(BaseCommand):
    help = "Write the admin import templates (quiz questions, sessions, activities, participants) to a folder."

    def add_arguments(self, parser):
        parser.add_argument("--output", default="import_templates", help="Destination folder (default: import_templates)")

    def handle(self, *args, **options):
        destination = Path(options["output"])
        destination.mkdir(parents=True, exist_ok=True)
        for key, (filename, builder) in sorted(TEMPLATES.items()):
            path = destination / filename
            builder().save(path)
            self.stdout.write(f"  {key:<20} -> {path}")
        self.stdout.write(self.style.SUCCESS(f"Wrote {len(TEMPLATES)} templates to {destination.resolve()}"))
