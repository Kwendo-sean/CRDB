"""Boot the ASGI application the way a production server does.

The test runner and runserver both call django.setup() before touching any
module, so they cannot catch an import-order fault in config/asgi.py. gunicorn
does not: it imports the module cold. These tests reproduce that by importing
in a clean subprocess, which is the only way this class of failure shows up
before deployment.
"""

import subprocess
import sys
import textwrap

from django.test import SimpleTestCase


def boot(snippet):
    """Run a snippet in a fresh interpreter with no Django set up."""
    return subprocess.run(
        [sys.executable, "-c", textwrap.dedent(snippet)],
        capture_output=True, text=True, timeout=120,
    )


class AsgiBootTests(SimpleTestCase):
    def test_the_asgi_application_imports_without_django_being_set_up(self):
        result = boot("""
            import os
            os.environ["DJANGO_SETTINGS_MODULE"] = "config.settings"
            from config.asgi import application
            assert application is not None
            print("BOOTED")
        """)
        self.assertIn("BOOTED", result.stdout,
                      f"config.asgi failed to import cold, as gunicorn does:\n{result.stderr}")
        self.assertNotIn("AppRegistryNotReady", result.stderr)

    def test_it_serves_both_http_and_websocket(self):
        result = boot("""
            import os
            os.environ["DJANGO_SETTINGS_MODULE"] = "config.settings"
            from config.asgi import application
            print(sorted(application.application_mapping))
        """)
        self.assertIn("'http'", result.stdout, result.stderr)
        self.assertIn("'websocket'", result.stdout, result.stderr)

    def test_the_wsgi_application_also_imports_cold(self):
        result = boot("""
            import os
            os.environ["DJANGO_SETTINGS_MODULE"] = "config.settings"
            from config.wsgi import application
            assert application is not None
            print("BOOTED")
        """)
        self.assertIn("BOOTED", result.stdout, result.stderr)

    def test_celery_imports_cold(self):
        result = boot("""
            import os
            os.environ["DJANGO_SETTINGS_MODULE"] = "config.settings"
            from config.celery import app
            assert app is not None
            print("BOOTED")
        """)
        self.assertIn("BOOTED", result.stdout, result.stderr)
