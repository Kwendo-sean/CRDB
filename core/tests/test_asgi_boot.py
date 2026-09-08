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

from django.test import SimpleTestCase, TestCase


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


class HealthcheckReachabilityTests(TestCase):
    """The container healthcheck must be able to reach /health/.

    docker-compose curls http://localhost:8000/health/ and nginx will not start
    until that passes. Django answers 400 for any host outside ALLOWED_HOSTS, so
    dropping localhost from it leaves the web container permanently unhealthy —
    a failure that looks like a hang, not an error.
    """

    HEALTHCHECK_HOSTS = ("localhost", "127.0.0.1")

    def test_the_healthcheck_hosts_are_answered(self):
        """A 400 here means the container can never report healthy."""
        for host in self.HEALTHCHECK_HOSTS:
            response = self.client.get("/health/", HTTP_HOST=host, HTTP_X_FORWARDED_PROTO="https")
            self.assertNotEqual(response.status_code, 400, f"healthcheck host {host} is not in ALLOWED_HOSTS")
            self.assertEqual(response.status_code, 200, f"healthcheck host {host} did not report ready")

    def test_the_setup_script_keeps_localhost_in_allowed_hosts(self):
        from pathlib import Path
        script = Path("server_setup.sh").read_text(encoding="utf-8")
        for line in script.splitlines():
            if "upsert DJANGO_ALLOWED_HOSTS" in line:
                self.assertIn("localhost", line,
                              "server_setup.sh must keep localhost in ALLOWED_HOSTS or the "
                              "container healthcheck fails and nginx never starts")

    def test_the_compose_healthcheck_still_targets_a_host_we_allow(self):
        from pathlib import Path
        compose = Path("docker-compose.yml").read_text(encoding="utf-8")
        healthcheck = next(line for line in compose.splitlines() if "health/" in line)
        self.assertTrue(
            any(host in healthcheck for host in self.HEALTHCHECK_HOSTS),
            f"healthcheck targets a host this test does not cover: {healthcheck.strip()}",
        )
