import secrets
import string

from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand, CommandError

ALPHABET = string.ascii_letters + string.digits


class Command(BaseCommand):
    help = "Create or update a Control Room operator. Prints a generated password when none is given."

    def add_arguments(self, parser):
        parser.add_argument("username")
        parser.add_argument("--email", default="")
        parser.add_argument("--password", default="", help="Leave blank to generate a strong one and print it.")
        parser.add_argument("--superuser", action="store_true", help="Also grant Django admin access.")

    def handle(self, *args, **options):
        User = get_user_model()
        username = options["username"].strip()
        if not username:
            raise CommandError("A username is required.")
        password = options["password"] or "".join(secrets.choice(ALPHABET) for _ in range(20))
        generated = not options["password"]

        user, created = User.objects.get_or_create(username=username, defaults={"email": options["email"]})
        if options["email"]:
            user.email = options["email"]
        user.is_staff = True
        user.is_superuser = options["superuser"] or user.is_superuser
        user.set_password(password)
        user.save()

        self.stdout.write(self.style.SUCCESS(f"{'Created' if created else 'Updated'} operator '{username}'"))
        self.stdout.write(f"  Control Room : /control/login/")
        self.stdout.write(f"  Username     : {username}")
        if generated:
            self.stdout.write(f"  Password     : {password}")
            self.stdout.write(self.style.WARNING("  Store this now — it is not recoverable, only resettable."))
        else:
            self.stdout.write("  Password     : (as supplied)")
