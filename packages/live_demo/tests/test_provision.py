import copy
from dataclasses import replace
import importlib
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from cortrix_live_demo.provision import RuntimeManager
from support import make_config

provision_module = importlib.import_module("cortrix_live_demo.provision")


class ProvisionTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.config = make_config(Path(self.temp.name))
        self.manager = RuntimeManager(config=self.config)

    def test_container_and_volume_ownership_include_runtime_scope(self):
        name = self.config.container_name("embedding")
        value = {"Image": "image-digest", "Config": {"Labels": {
            "cortrix.demo.owner": self.config.owner_label,
            "cortrix.demo.runtime_scope": self.manager.scope_id,
        }}, "Mounts": [{"Name": name + "-data", "Type": "volume", "Destination": "/data"}],
            "HostConfig": {"PortBindings": {"8420/tcp": [{"HostIp": "127.0.0.1", "HostPort": str(self.config.embedding_port)}]}}}
        self.manager.validate_container(value, name, "image-digest")
        changed = copy.deepcopy(value)
        changed["Config"]["Labels"]["cortrix.demo.runtime_scope"] = "another-scope"
        with self.assertRaises(RuntimeError):
            self.manager.validate_container(changed, name, "image-digest")

    def test_provider_template_uses_the_configured_internal_callback(self):
        self.config.configs_root.mkdir(parents=True)
        template = "\n".join(["base_url: https://api.deepseek.com/v1\napi_key: __RUNTIME_API_KEY__"] * 3) + "\nmax_active: 10\n"
        (self.config.configs_root / "cortrix.full-stack.yaml").write_text(template)
        rendered = self.manager.full_config("run_0000000000000000", "runtime-token-value")
        self.assertEqual(rendered.count(self.config.core_callback_base_url), 3)
        self.assertNotIn("https://api.deepseek.com/v1", rendered)

    def test_network_create_and_validation_use_the_configured_subnet_and_gateway(self):
        with patch.object(provision_module, "command", side_effect=["", self.config.network_name]) as command:
            self.manager.ensure_network()
        creation = command.call_args_list[1].args[0]
        self.assertIn(self.config.network_subnet, creation)
        self.assertIn(self.config.network_gateway, creation)

    def test_core_source_identity_verifies_clean_annotated_release(self):
        manifest = self.config.core_source_root / "deploy" / "model-manifest.tsv"
        manifest.parent.mkdir(parents=True)
        manifest.write_text("source\tdestination\tsha256\n")
        with patch.object(provision_module, "command", side_effect=[
            provision_module.REVISION,
            "",
            provision_module.ANNOTATED_TAG_SHA,
            provision_module.REVISION,
        ]):
            identity = self.manager.verify_core_source()
        self.assertEqual(provision_module.REVISION, identity["head"])
        self.assertEqual(provision_module.ANNOTATED_TAG_SHA, identity["tag_object"])
        self.assertTrue(identity["clean"])

    def test_readiness_uses_configured_component_ports(self):
        config = replace(self.config, embedding_port=28426, full_port=28427)
        manager = RuntimeManager(config=config)
        with patch.object(manager, "ready", side_effect=[{"ready": "embedding"}, {"ready": "full"}]) as ready:
            self.assertEqual({"embedding": {"ready": "embedding"}, "full": {"ready": "full"}}, manager.readiness())
        self.assertEqual([28426, 28427], [call.args[0] for call in ready.call_args_list])

    def test_stopped_owned_postgres_is_restarted(self):
        name = self.config.container_name("pg")
        existing = {
            "Config": {"Image": "pgvector/pgvector:pg16", "Labels": {
                "cortrix.demo.owner": self.config.owner_label,
                "cortrix.demo.runtime_scope": self.manager.scope_id,
            }},
            "Mounts": [{"Name": self.config.volume_name("pg"), "Type": "volume", "Destination": "/var/lib/postgresql/data"}],
            "HostConfig": {"PortBindings": {"5432/tcp": [{"HostIp": "127.0.0.1", "HostPort": str(self.config.pg_port)}]}},
            "State": {"Running": False},
        }
        with patch.object(provision_module, "command", return_value="") as command:
            self.manager.reuse_pg_container(existing)
        command.assert_called_once_with(["docker", "start", name])


if __name__ == "__main__":
    unittest.main()
