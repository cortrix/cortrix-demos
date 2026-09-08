import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from cortrix_live_demo.config import ConfigurationError, _number, load_config, validate_config


class FakeNetwork:
    version = 4
    is_private = True
    is_loopback = False
    is_link_local = False
    is_multicast = False
    is_reserved = False
    network_address = "network"
    broadcast_address = "broadcast"

    def __contains__(self, value):
        return True

    def subnet_of(self, value):
        return True

    def __str__(self):
        return "dedicated-network"


class ConfigTests(unittest.TestCase):
    def test_missing_internal_network_fails_closed(self):
        with self.assertRaises(ConfigurationError):
            load_config(environment={})

    def test_explicit_config_is_validated_without_exposing_absolute_paths(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "config.json"
            path.write_text(json.dumps({
                "internal_bind_host": "dedicated-gateway", "internal_port": 4187,
                "core_callback_base_url": "http://dedicated-gateway:4187",
                "network_subnet": "dedicated-network", "network_gateway": "dedicated-gateway",
                "provider_input_cache_hit_usd_per_million": 0.01,
                "provider_input_cache_miss_usd_per_million": 0.1,
                "provider_output_usd_per_million": 0.2,
            }))
            with patch("cortrix_live_demo.config.ipaddress.ip_network", return_value=FakeNetwork()), \
                 patch("cortrix_live_demo.config.ipaddress.ip_address", return_value="dedicated-gateway"):
                result = validate_config(path, {})
        self.assertEqual(result["status"], "valid")
        self.assertTrue(result["config"]["paths_configured"])
        self.assertFalse(any(str(value).startswith("/") for value in result["config"].values()))

    def test_non_rfc1918_network_is_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "config.json"
            path.write_text(json.dumps({
                "internal_bind_host": "203.0.113.1", "internal_port": 4187,
                "core_callback_base_url": "http://203.0.113.1:4187",
                "network_subnet": "203.0.113.0/24", "network_gateway": "203.0.113.1",
            }))
            with self.assertRaises(ConfigurationError):
                load_config(path, {})

    def test_budget_and_price_numbers_must_be_finite(self):
        for value in (float("nan"), float("inf"), float("-inf")):
            with self.subTest(value=value), self.assertRaises(ConfigurationError):
                _number("budget", value)


if __name__ == "__main__":
    unittest.main()
