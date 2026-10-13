import json
import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from dbt_pipeline import TOKEN_ENV, execute_build, make_profile


class DbtPipelineTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.source = self.root / "source"
        self.source.mkdir()
        (self.source / "dbt_project.yml").write_text("name: boucherie", encoding="utf-8")
        (self.source / "models").mkdir()
        (self.source / "models" / "sample.sql").write_text("select 1", encoding="utf-8")
        self.executable = self.root / "dbt"
        self.executable.touch()
        self.connection = SimpleNamespace(
            host="test.cloud.databricks.com", password="test-token-not-real",
            extra_dejson={"http_path": "/sql/1.0/warehouses/abc123", "catalog": "workspace", "schema": "boucherie_raw"},
        )

    def run_build(self):
        return execute_build(self.connection, "manual:test", self.source, self.executable, self.root / "artifacts")

    def test_profile_uses_output_schema_and_secret_reference(self):
        profile = make_profile(self.connection)
        self.assertNotIn(self.connection.password, json.dumps(profile))
        self.assertEqual(profile["boucherie"]["outputs"]["airflow"]["schema"], "dbt_boucherie_dev")

    def test_refuses_output_in_raw_schema(self):
        self.connection.extra_dejson["dbt_schema"] = "boucherie_raw"
        with self.assertRaises(ValueError):
            make_profile(self.connection)

    def test_success_keeps_artifacts_without_secret(self):
        def fake_run(command, **kwargs):
            profile_dir = Path(command[command.index("--profiles-dir") + 1])
            self.assertNotIn(self.connection.password, (profile_dir / "profiles.yml").read_text())
            self.assertEqual(kwargs["env"][TOKEN_ENV], self.connection.password)
            self.assertNotIn("PYTHONPATH", kwargs["env"])
            self.assertEqual(command[1], "build")
            self.assertNotEqual(kwargs["cwd"], self.source)
            target = Path(command[command.index("--target-path") + 1])
            target.mkdir()
            (target / "run_results.json").write_text(json.dumps({"results": [{"status": "success"}, {"status": "pass"}]}))
            self.profiles = profile_dir
            return SimpleNamespace(returncode=0, stdout="build termine")

        with patch("dbt_pipeline.subprocess.run", side_effect=fake_run):
            result = self.run_build()
        self.assertEqual(result["resources"], 2)
        self.assertFalse(self.profiles.exists())
        self.assertTrue((Path(result["artifacts"]) / "target" / "run_results.json").exists())

    def test_failed_dbt_fails_task_and_masks_token(self):
        with patch("dbt_pipeline.subprocess.run", return_value=SimpleNamespace(returncode=1, stdout=self.connection.password)):
            with self.assertLogs(level="INFO") as logs:
                with self.assertRaises(RuntimeError):
                    self.run_build()
        self.assertNotIn(self.connection.password, "\n".join(logs.output))

    def test_missing_results_fails_even_with_zero_exit(self):
        with patch("dbt_pipeline.subprocess.run", return_value=SimpleNamespace(returncode=0, stdout="")):
            with self.assertRaisesRegex(RuntimeError, "run_results.json"):
                self.run_build()


if __name__ == "__main__":
    unittest.main()
