from __future__ import annotations

import unittest
from unittest.mock import MagicMock, patch

from packages.viewer.serve import LOOPBACK, create_server


class ViewerServerTests(unittest.TestCase):
    @patch("packages.viewer.serve.ThreadingHTTPServer")
    def test_unavailable_preferred_address_falls_back_to_loopback(self, server_type: MagicMock) -> None:
        fallback_server = MagicMock()
        server_type.side_effect = [OSError("address unavailable"), fallback_server]
        server, bind, used_fallback = create_server("192.0.2.1", 18765)
        self.assertIs(fallback_server, server)
        self.assertEqual(LOOPBACK, bind)
        self.assertTrue(used_fallback)
        self.assertEqual((LOOPBACK, 18765), server_type.call_args_list[1].args[0])

    @patch("packages.viewer.serve.ThreadingHTTPServer")
    def test_loopback_failure_is_not_hidden(self, server_type: MagicMock) -> None:
        server_type.side_effect = OSError("port unavailable")
        with self.assertRaises(OSError):
            create_server(LOOPBACK, 18765)
        self.assertEqual(1, server_type.call_count)


if __name__ == "__main__":
    unittest.main()
