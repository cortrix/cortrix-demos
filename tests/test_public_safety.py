from __future__ import annotations

from pathlib import Path
import unittest

from cortrix_demo_runner.safety import ALLOWED_INTERNAL_FEATURE_ID, is_archived_evidence, scan_internal_feature_ids, scan_text


class PublicSafetyTests(unittest.TestCase):
    def test_rejects_private_path_and_cjk(self) -> None:
        unsafe_text = "Internal path: /" + "Users/example. Private note: \u5185\u90e8.\n"
        failures = scan_text(unsafe_text, Path("unsafe.md"))
        self.assertTrue(any("local absolute path" in failure for failure in failures))
        self.assertTrue(any("CJK text" in failure for failure in failures))

    def test_rejects_secret_like_assignment(self) -> None:
        unsafe_text = "DEEPSEEK_API_KEY" + "=abcdefghijklmnopqrstuvwxyz\n"
        failures = scan_text(unsafe_text, Path("unsafe.txt"))
        self.assertTrue(any("secret-like assignment" in failure for failure in failures))

    def test_rejects_unintended_private_ipv4_literals(self) -> None:
        failures = scan_text("Bind to " + "192." + "168.1.44" + " for local access.\n", Path("docs/example.md"))
        self.assertTrue(any("private IPv4 literal" in failure for failure in failures))
        self.assertEqual([], scan_text("VIEWER_BIND ?= " + "192.168." + "50.75" + "\n", Path("Makefile")))

    def test_rejects_internal_feature_identifiers_in_public_text(self) -> None:
        for text in ("The " + "F" + "41" + " summary path is required.\n", '  "' + "f41" + '_document_summary_ingestion": true\n'):
            failures = scan_internal_feature_ids(text, Path("docs/example.md"))
            self.assertTrue(any("internal feature identifier" in failure for failure in failures), text)

    def test_accepts_public_capability_names_and_unrelated_tokens(self) -> None:
        text = "document_summary_ingestion and contextualization_all_chunks completed. Digest 32b82f6f8f1d.\n"
        self.assertEqual([], scan_internal_feature_ids(text, Path("docs/example.md")))

    def test_verbatim_upstream_quote_is_exempt_only_for_its_own_file_and_token(self) -> None:
        quoting_doc = next(iter(ALLOWED_INTERNAL_FEATURE_ID))
        allowed_token = next(iter(ALLOWED_INTERNAL_FEATURE_ID[quoting_doc]))
        self.assertEqual([], scan_internal_feature_ids(f'  "feature_id": "{allowed_token}"\n', quoting_doc))
        self.assertTrue(scan_internal_feature_ids(f'  "feature_id": "{allowed_token}"\n', Path("docs/other.md")))
        self.assertTrue(scan_internal_feature_ids("The " + "F" + "13" + " trace path.\n", quoting_doc))

    def test_archived_evidence_is_exempt_from_the_feature_identifier_rule(self) -> None:
        self.assertTrue(is_archived_evidence(Path("scenarios/demo/evidence/runs/run-1/run-manifest.json")))
        self.assertFalse(is_archived_evidence(Path("scenarios/demo/profiles/full-stack.json")))
        self.assertFalse(is_archived_evidence(Path("docs/full-stack-runbook.md")))


if __name__ == "__main__":
    unittest.main()
