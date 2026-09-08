from contextlib import redirect_stderr
import io
import json
from pathlib import Path
import tempfile
import unittest

from cortrix_live_demo.cli import main


class CliTests(unittest.TestCase):
    def test_invalid_config_error_is_json_and_does_not_echo_its_path(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "operator-config.json"
            path.write_text("{}")
            error = io.StringIO()
            with redirect_stderr(error):
                result = main(["--config", str(path), "validate-config"])
        payload = json.loads(error.getvalue())
        self.assertEqual(1, result)
        self.assertEqual("CORTRIX_LIVE_DEMO_CONFIG_INVALID", payload["error"]["code"])
        self.assertNotIn(str(path), error.getvalue())


if __name__ == "__main__":
    unittest.main()
