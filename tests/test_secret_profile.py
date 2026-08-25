from __future__ import annotations

import os
from pathlib import Path
import tempfile
import unittest

from cortrix_demo_runner.errors import DemoContractError
from cortrix_demo_runner.secret_profile import resolve_secret


class SecretProfileTests(unittest.TestCase):
    EXPECTED_MODEL = "deepseek-v4-flash"
    EXPECTED_BASE_URL = "https://api.deepseek.com/v1"

    def profile_text(self, key: str, *, model: str | None = None, base_url: str | None = None) -> str:
        return "\n".join(
            (
                'label: "test-profile"',
                f'base_url: "{base_url or "https://api.deepseek.com"}"',
                f'api_key: "{key}"',
                "roles:",
                "  semantic_llm:",
                f'    model: "{model or self.EXPECTED_MODEL}"',
                "",
            )
        )

    def write_profile(self, path: Path, key: str, *, mode: int = 0o600, model: str | None = None, base_url: str | None = None) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(self.profile_text(key, model=model, base_url=base_url), encoding="utf-8")
        path.chmod(mode)

    def resolve(self, environment: dict[str, str]):
        return resolve_secret(
            "DEEPSEEK_API_KEY",
            expected_model=self.EXPECTED_MODEL,
            expected_base_url=self.EXPECTED_BASE_URL,
            environment=environment,
        )

    def test_explicit_environment_variable_has_highest_precedence(self) -> None:
        key = "sk-" + "e" * 32
        result = self.resolve({"DEEPSEEK_API_KEY": key, "CORTRIX_LLM_SECRET_FILE": "/missing/profile.yaml"})
        self.assertEqual("environment", result.source)
        self.assertEqual(key, result.value)

    def test_explicit_profile_is_resolved_without_disclosing_its_path(self) -> None:
        key = "sk-" + "p" * 32
        with tempfile.TemporaryDirectory() as directory:
            profile = Path(directory) / "selected.yaml"
            self.write_profile(profile, key)
            result = self.resolve({"CORTRIX_LLM_SECRET_FILE": str(profile), "HOME": directory})
            self.assertEqual("explicit_profile", result.source)
            self.assertEqual(key, result.value)
            self.assertNotIn(str(profile), repr(result))
            self.assertNotIn(key, repr(result))

    def test_default_profile_allows_a_protected_symlink_target(self) -> None:
        key = "sk-" + "d" * 32
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            target = root / "deepseek.yaml"
            current = root / ".config" / "cortrix" / "secrets" / "llm" / "current.yaml"
            self.write_profile(target, key)
            current.parent.mkdir(parents=True)
            current.symlink_to(target)
            result = self.resolve({"HOME": directory})
            self.assertEqual("default_profile", result.source)
            self.assertEqual(key, result.value)

    @unittest.skipUnless(os.name == "posix", "POSIX permissions are required for this test")
    def test_group_readable_profile_fails_closed(self) -> None:
        key = "sk-" + "u" * 32
        with tempfile.TemporaryDirectory() as directory:
            profile = Path(directory) / "unsafe.yaml"
            self.write_profile(profile, key, mode=0o640)
            with self.assertRaises(DemoContractError) as captured:
                self.resolve({"CORTRIX_LLM_SECRET_FILE": str(profile), "HOME": directory})
            error = captured.exception.as_dict()["error"]
            self.assertEqual("CX_DEMO_SECRET_PROFILE_UNSAFE", error["code"])
            self.assertFalse(error["structured_data"]["external_calls_made"])
            self.assertNotIn(str(profile), str(error))
            self.assertNotIn(key, str(error))

    def test_model_and_endpoint_mismatch_fail_closed(self) -> None:
        key = "sk-" + "m" * 32
        cases = (
            {"model": "different-model"},
            {"base_url": "https://example.invalid/v1"},
        )
        for changes in cases:
            with self.subTest(changes=changes), tempfile.TemporaryDirectory() as directory:
                profile = Path(directory) / "mismatch.yaml"
                self.write_profile(profile, key, **changes)
                with self.assertRaises(DemoContractError) as captured:
                    self.resolve({"CORTRIX_LLM_SECRET_FILE": str(profile), "HOME": directory})
                self.assertEqual("CX_DEMO_SECRET_PROFILE_MISMATCH", captured.exception.as_dict()["error"]["code"])

    def test_missing_secret_reports_supported_discovery_without_a_local_path(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            with self.assertRaises(DemoContractError) as captured:
                self.resolve({"HOME": directory})
            error = captured.exception.as_dict()["error"]
            self.assertEqual("CX_DEMO_SECRET_MISSING", error["code"])
            self.assertTrue(error["structured_data"]["default_profile_supported"])
            self.assertNotIn(directory, str(error))

    def test_safe_commands_do_not_read_an_invalid_profile(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            invalid_profile = Path(directory) / "invalid.yaml"
            invalid_profile.write_text("not a profile\n", encoding="utf-8")
            environment = {
                key: value
                for key, value in os.environ.items()
                if key not in {"DEEPSEEK_API_KEY", "CORTRIX_LLM_SECRET_FILE"}
            }
            environment["CORTRIX_LLM_SECRET_FILE"] = str(invalid_profile)
            import subprocess

            for arguments in (("list", "--json"), ("validate", "--scenario", "order-api-field-migration"), ("verify-accepted",)):
                result = subprocess.run(
                    [str(Path(__file__).parents[1] / "democtl"), *arguments],
                    env=environment,
                    check=False,
                    capture_output=True,
                    text=True,
                )
                self.assertEqual(0, result.returncode, result.stderr)


if __name__ == "__main__":
    unittest.main()
