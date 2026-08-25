from __future__ import annotations

from pathlib import Path
import subprocess
import tempfile
import unittest

from cortrix_demo_runner.errors import DemoContractError
from cortrix_demo_runner.history_safety import verify_public_history


class HistorySafetyTests(unittest.TestCase):
    def test_scans_each_commit_after_the_base(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            subprocess.run(["git", "init", "-b", "main"], cwd=root, check=True, capture_output=True)
            subprocess.run(["git", "config", "user.name", "Public Test"], cwd=root, check=True)
            subprocess.run(["git", "config", "user.email", "public@example.invalid"], cwd=root, check=True)
            (root / "README.md").write_text("Safe public content.\n", encoding="utf-8")
            subprocess.run(["git", "add", "README.md"], cwd=root, check=True)
            subprocess.run(["git", "commit", "-m", "safe base"], cwd=root, check=True, capture_output=True)
            base = subprocess.run(["git", "rev-parse", "HEAD"], cwd=root, check=True, capture_output=True, text=True).stdout.strip()
            (root / "README.md").write_text("Safe public content.\nMore public content.\n", encoding="utf-8")
            subprocess.run(["git", "commit", "-am", "safe update"], cwd=root, check=True, capture_output=True)
            result = verify_public_history(root, base)
            self.assertEqual(1, result["commits_scanned"])
            (root / "unsafe.md").write_text("Private path: /" + "Users/example\n", encoding="utf-8")
            subprocess.run(["git", "add", "unsafe.md"], cwd=root, check=True)
            subprocess.run(["git", "commit", "-m", "unsafe update"], cwd=root, check=True, capture_output=True)
            with self.assertRaisesRegex(DemoContractError, "Public history validation failed"):
                verify_public_history(root, base)


if __name__ == "__main__":
    unittest.main()
