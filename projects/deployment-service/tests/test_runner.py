import importlib.util
from pathlib import Path
import unittest

path = Path(__file__).parents[1] / "runner" / "jormall_runner.py"
spec = importlib.util.spec_from_file_location("jormall_runner", path)
runner = importlib.util.module_from_spec(spec)
assert spec.loader
spec.loader.exec_module(runner)


class RunnerValidationTests(unittest.TestCase):
    def test_domains(self):
        self.assertEqual(runner.domain_for("crm", "production"), "crm.jormallapp.com")
        self.assertEqual(runner.domain_for("crm", "staging"), "crm.staging.jormallapp.com")

    def test_rejects_unsafe_fields(self):
        for value in ("../root", "bad.dot", "a_b", "-bad"):
            with self.assertRaises(runner.RunnerError):
                runner.validate_app(value)
        for value in ("image;id", "-v/:/host", "", "repo/image latest"):
            with self.assertRaises(runner.RunnerError):
                runner.validate_image(value)

    def test_generated_nginx_is_loopback_only(self):
        text = runner.nginx_text(app="demo", environment="preview", domain="demo.preview.jormallapp.com", port=18001, protected=True)
        self.assertIn("proxy_pass http://127.0.0.1:18001", text)
        self.assertIn("auth_basic", text)
        self.assertNotIn("0.0.0.0:18001", text)

    def test_ai_dashboard_is_public_without_sso_gate(self):
        text = runner.nginx_text(
            app="ai-dashboard",
            environment="production",
            domain="ai-dashboard.jormallapp.com",
            port=18013,
            protected=False,
        )
        self.assertNotIn("auth_request", text)
        self.assertNotIn("/_sso_verify", text)
        self.assertIn("proxy_pass http://127.0.0.1:18013", text)

    def test_build_context_cannot_escape_apps_root(self):
        with self.assertRaises(runner.RunnerError):
            runner.validate_build_context("/tmp/untrusted")

    def test_persistent_mount_rejects_host_paths(self):
        with self.assertRaises(runner.RunnerError):
            runner.validate_persistent_mounts(
                "demo", "production", [{"name": "host", "container_path": "/etc"}]
            )

    def test_upload_identifier_validation(self):
        self.assertIsNone(runner.validate_upload_id(None))
        self.assertEqual(runner.validate_upload_id("a" * 32), "a" * 32)
        for value in ("../archive", "A" * 32, "abc", "a" * 33):
            with self.assertRaises(runner.RunnerError):
                runner.validate_upload_id(value)

    def test_archive_secret_filter(self):
        self.assertTrue(runner._archive_path(("src", "main.py")))
        self.assertFalse(runner._archive_path((".env",)))
        self.assertFalse(runner._archive_path(("config", "private.key")))
        self.assertFalse(runner._archive_path((".git", "config")))
        self.assertFalse(runner._archive_path(("compose.yaml",)))


if __name__ == "__main__":
    unittest.main()
