from pathlib import Path
import tempfile
import unittest

from cortrix_live_demo.state import Paused, State
from support import make_config


class StateTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.config = make_config(Path(self.temp.name))
        self.state = State(self.config.runtime_root, self.config)
        self.file = self.state.add_file("fixture.md", b"Current field is buyer_account_id.")

    def payload(self, **changes):
        value = {"mode": "deterministic", "locale": "en-US", "input_ids": [self.file["id"]],
                 "question": "Which field is current?", "idempotency_key": "state-unit-key",
                 "external_call_authorized": True}
        value.update(changes)
        return value

    def test_en_us_run_uses_contract_paths_and_requires_explicit_authorization(self):
        with self.assertRaisesRegex(ValueError, "Explicit authorization"):
            self.state.create(self.payload(external_call_authorized=False))
        run, fresh = self.state.create(self.payload())
        self.assertTrue(fresh)
        self.assertEqual(list(run["paths"]), ["a0", "a1", "b"])
        self.assertEqual(run["locale"], "en-US")
        run["state"] = "completed"
        self.state.put(run)
        with self.assertRaisesRegex(ValueError, "en-US"):
            self.state.create(self.payload(locale="zh-CN", idempotency_key="locale-unit-key"))

    def test_budget_reservation_stops_when_external_calls_are_disabled(self):
        run, _ = self.state.create(self.payload())
        run["state"] = "running"
        self.state.put(run)
        payload = {"model": self.config.provider_model, "max_tokens": 8}
        reservation = self.state.reserve(run["id"], "a1", "request-one", payload)
        self.state.settle("request-one", {"prompt_tokens": 10, "completion_tokens": 2, "prompt_cache_hit_tokens": 0})
        self.assertEqual(self.state.data["requests"][0]["state"], "completed")
        disabled = make_config(Path(self.temp.name) / "disabled", external_calls=False)
        other = State(disabled.runtime_root, disabled)
        source = other.add_file("fixture.md", b"Evidence")
        blocked, _ = other.create({**self.payload(), "input_ids": [source["id"]], "idempotency_key": "disabled-key"})
        blocked["state"] = "running"
        other.put(blocked)
        with self.assertRaisesRegex(Paused, "EXTERNAL_CALLS_DISABLED"):
            other.reserve(blocked["id"], "a1", "request-two", payload)


if __name__ == "__main__":
    unittest.main()
