from __future__ import annotations

from pathlib import Path
import unittest

from cortrix_demo_runner.safety import scan_text


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


if __name__ == "__main__":
    unittest.main()
