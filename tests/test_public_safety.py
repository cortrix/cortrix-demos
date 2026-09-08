from __future__ import annotations

from pathlib import Path
import unittest

from cortrix_demo_runner.safety import TEXT_SUFFIXES, scan_text


class PublicSafetyTests(unittest.TestCase):
    def test_native_harness_modules_are_scanned(self) -> None:
        self.assertIn(".mjs", TEXT_SUFFIXES)
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


if __name__ == "__main__":
    unittest.main()
