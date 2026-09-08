"""Provision isolated containers from a verified RC2 image without model calls."""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import time
import urllib.request

from .state import atomic, stamp
from .config import RuntimeConfig, load_config, CORTRIX_COMMIT, CORTRIX_RELEASE

REVISION = CORTRIX_COMMIT
ANNOTATED_TAG_SHA = "eb506804f4de1a86b10d05e2792bc5ad6846bd86"


def command(args, **kwargs):
    result = subprocess.run(args, check=False, capture_output=True, text=True, **kwargs)
    if result.returncode:
        raise RuntimeError(f"Command failed ({args[:3]}): {result.stderr[:1000]}")
    return result.stdout.strip()


def secure_text(path, text):
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    with path.open("w") as handle:
        handle.write(text)
    path.chmod(0o600)


class RuntimeManager:
    def __init__(self, root=None, config: RuntimeConfig | None = None):
        self.config = config or load_config()
        self.root = Path(root).resolve() if root is not None else self.config.runtime_root
        self.scope_id = hashlib.sha256(str(self.root).encode()).hexdigest()
        self.bound = None

    def name(self, component):
        return self.config.container_name(component)

    def full_config(self, rid, internal):
        if not re.fullmatch(r"run_[a-f0-9]{16}", rid):
            raise ValueError("Invalid run identity")
        text = (self.config.configs_root / "cortrix.full-stack.yaml").read_text()
        route = f"{self.config.core_callback_base_url}/internal/core/{rid}/model/v1"
        if text.count("https://api.deepseek.com/v1") != 3 or text.count("__RUNTIME_API_KEY__") != 3:
            raise RuntimeError("Full Stack provider template no longer matches the frozen routed-provider contract")
        text = text.replace("https://api.deepseek.com/v1", route).replace("__RUNTIME_API_KEY__", internal)
        text = text.replace("max_active: 10", "max_active: 64")
        return text

    def verify_core_source(self):
        """Verify the clean checkout, annotated release tag, and model manifest."""
        root = str(self.config.core_source_root)
        head = command(["git", "-C", root, "rev-parse", "HEAD"])
        dirty = command(["git", "-C", root, "status", "--short", "--untracked-files=all"])
        tag_object = command(["git", "-C", root, "rev-parse", "refs/tags/v1.0.0-rc.2^{tag}"])
        tag_commit = command(["git", "-C", root, "rev-parse", "refs/tags/v1.0.0-rc.2^{}"])
        if head != REVISION or tag_commit != REVISION or tag_object != ANNOTATED_TAG_SHA or dirty:
            raise RuntimeError("The Core checkout does not match the clean annotated RC2 release identity")
        manifest = self.config.core_source_root / "deploy" / "model-manifest.tsv"
        if not manifest.is_file():
            raise RuntimeError("The verified Core checkout has no model manifest")
        return {
            "head": head,
            "tag": CORTRIX_RELEASE,
            "tag_object": tag_object,
            "tag_commit": tag_commit,
            "clean": True,
            "model_manifest_sha256": hashlib.sha256(manifest.read_bytes()).hexdigest(),
        }

    def ready(self, port, timeout=180):
        deadline = time.monotonic() + timeout
        last = "not observed"
        while time.monotonic() < deadline:
            try:
                with urllib.request.urlopen(f"http://127.0.0.1:{port}/api/v1/system/health/ready", timeout=5) as response:
                    if response.status == 200:
                        return json.loads(response.read())
            except Exception as exc:
                last = str(exc)
            time.sleep(1)
        raise RuntimeError("RC2 readiness timeout: " + last)

    def validate_container(self, existing, name, image_id):
        labels = existing["Config"]["Labels"] or {}
        if existing["Image"] != image_id or labels.get("cortrix.demo.owner") != self.config.owner_label or labels.get("cortrix.demo.runtime_scope") != self.scope_id:
            raise RuntimeError("Existing container name belongs to another runtime")
        if not any(m.get("Name") == name + "-data" and m.get("Type") == "volume" and m["Destination"] == "/data" for m in existing["Mounts"]):
            raise RuntimeError("Existing demo container has an unexpected data location")
        component = name.removeprefix(self.config.container_prefix + "-")
        expected = [{"HostIp": "127.0.0.1", "HostPort": str(self.config.component_port(component))}]
        if existing.get("HostConfig", {}).get("PortBindings", {}).get("8420/tcp") != expected:
            raise RuntimeError("Existing demo container has an unexpected loopback port binding")

    def ensure_volume(self, name, existing):
        """Create a new owned volume or reject an existing volume from another runtime."""
        if name in existing:
            value = json.loads(command(["docker", "volume", "inspect", name]))[0]
            labels = value.get("Labels") or {}
            if labels.get("cortrix.demo.owner") != self.config.owner_label or labels.get("cortrix.demo.runtime_scope") != self.scope_id:
                raise RuntimeError("Existing volume belongs to another runtime")
            return
        command(["docker", "volume", "create", "--label", f"cortrix.demo.owner={self.config.owner_label}",
                 "--label", f"cortrix.demo.runtime_scope={self.scope_id}", name])
        existing.add(name)

    def ensure_network(self):
        names = set(command(["docker", "network", "ls", "--format", "{{.Name}}"] ).splitlines())
        if self.config.network_name in names:
            value = json.loads(command(["docker", "network", "inspect", self.config.network_name]))[0]
            labels = value.get("Labels") or {}
            if labels.get("cortrix.demo.owner") != self.config.owner_label or labels.get("cortrix.demo.runtime_scope") != self.scope_id:
                raise RuntimeError("Existing network belongs to another runtime")
            ipam = value.get("IPAM", {}).get("Config") or []
            if len(ipam) != 1 or ipam[0].get("Subnet") != self.config.network_subnet or ipam[0].get("Gateway") != self.config.network_gateway:
                raise RuntimeError("Existing network has an unexpected subnet or gateway")
            return
        command(["docker", "network", "create", "--label", f"cortrix.demo.owner={self.config.owner_label}",
                 "--label", f"cortrix.demo.runtime_scope={self.scope_id}", "--subnet", self.config.network_subnet,
                 "--gateway", self.config.network_gateway, self.config.network_name])

    def validate_pg_container(self, existing):
        labels = existing["Config"].get("Labels") or {}
        if existing["Config"].get("Image") != "pgvector/pgvector:pg16" or labels.get("cortrix.demo.owner") != self.config.owner_label or labels.get("cortrix.demo.runtime_scope") != self.scope_id:
            raise RuntimeError("Existing PostgreSQL container belongs to another runtime")
        expected = self.config.volume_name("pg")
        if not any(mount.get("Name") == expected and mount.get("Type") == "volume" and mount.get("Destination") == "/var/lib/postgresql/data" for mount in existing["Mounts"]):
            raise RuntimeError("Existing PostgreSQL container has an unexpected data location")
        expected_binding = [{"HostIp": "127.0.0.1", "HostPort": str(self.config.pg_port)}]
        if existing.get("HostConfig", {}).get("PortBindings", {}).get("5432/tcp") != expected_binding:
            raise RuntimeError("Existing PostgreSQL container has an unexpected loopback port binding")

    def reuse_pg_container(self, existing):
        """Validate and restart only the owned PostgreSQL container."""
        self.validate_pg_container(existing)
        if not existing["State"]["Running"]:
            command(["docker", "start", self.name("pg")])

    def readiness(self):
        return {
            "embedding": self.ready(self.config.embedding_port),
            "full": self.ready(self.config.full_port),
        }

    def retained_containers(self):
        identity = json.loads((self.root / "runtime-identity.json").read_text())
        if identity["source_revision"] != REVISION or identity.get("container_prefix") != self.config.container_prefix or identity.get("runtime_scope") != self.scope_id:
            raise RuntimeError("Runtime identity has changed")
        names = [self.name("embedding"), self.name("full")]
        containers = {item["Name"].lstrip("/"): item for item in json.loads(command(["docker", "inspect", *names]))}
        for name in names:
            self.validate_container(containers[name], name, identity["image_digest"])
        return containers

    def activate_component(self, component):
        """Alternate only the owned Core processes; retain both data volumes."""
        if component not in {"embedding", "full"}:
            raise ValueError("Unknown retained component")
        containers = self.retained_containers()
        wanted = self.name(component)
        other = self.name("full" if component == "embedding" else "embedding")
        if containers[other]["State"]["Running"]:
            command(["docker", "stop", "--time", "30", other])
        if not containers[wanted]["State"]["Running"]:
            command(["docker", "start", wanted])
        self.ready(self.config.component_port(component))
        self.bound = None

    def bind_run(self, rid, internal):
        if not re.fullmatch(r"run_[a-f0-9]{16}", rid):
            raise ValueError("Invalid run identity")
        key = (rid, internal)
        containers = self.retained_containers()
        embedding = self.name("embedding")
        full = self.name("full")
        if containers[embedding]["State"]["Running"]:
            command(["docker", "stop", "--time", "30", embedding])
        if self.bound == key and containers[full]["State"]["Running"]:
            return
        identity = json.loads((self.root / "runtime-identity.json").read_text())
        if identity["source_revision"] != REVISION:
            raise RuntimeError("Runtime identity has changed")
        # Stop the owned instance before replacing its per-run provider route.
        command(["docker", "stop", "--time", "30", full])
        secure_text(self.root / "config" / "full" / "cortrix.yaml", self.full_config(rid, internal))
        command(["docker", "start", full])
        self.ready(self.config.full_port)
        self.bound = key
        atomic(self.root / "core-binding.json", {"run_id": rid, "source_revision": REVISION, "at": stamp(), "provider_route_is_run_scoped": True})

    def prepare(self):
        self.root.mkdir(parents=True, exist_ok=True, mode=0o700)
        source_identity = self.verify_core_source()
        image = json.loads(command(["docker", "image", "inspect", self.config.cortrix_image]))[0]
        labels = image["Config"]["Labels"]
        if labels.get("org.opencontainers.image.revision") != REVISION or labels.get("version") != "1.0.0-rc.2":
            raise RuntimeError("The image is not the verified RC2 source build")
        expected = list(csv.DictReader((self.config.core_source_root / "deploy" / "model-manifest.tsv").read_text().splitlines(), delimiter="\t"))
        paths = ["/models/" + a["destination"] for a in expected]
        hashes = command(["docker", "run", "--rm", "--network", "none", "--read-only",
                          "--mount", f"type=volume,src={self.config.model_volume},dst=/models,volume-subpath=models,readonly",
                          "ubuntu:22.04", "sha256sum", *paths]).splitlines()
        actual = {line.split()[1]: line.split()[0] for line in hashes}
        if any(actual.get("/models/" + a["destination"]) != a["sha256"] for a in expected):
            raise RuntimeError("Model checksum differs from the RC2 manifest")
        self.ensure_network()
        containers = command(["docker", "ps", "-a", "--format", "{{.Names}}"] ).splitlines()
        volumes = set(command(["docker", "volume", "ls", "--format", "{{.Name}}"] ).splitlines())
        for arm in ("embedding", "full"):
            port = self.config.component_port(arm)
            name = self.name(arm)
            config = self.root / "config" / arm
            if name in containers:
                existing = json.loads(command(["docker", "inspect", name]))[0]
                self.validate_container(existing, name, image["Id"])
                if not existing["State"]["Running"]:
                    command(["docker", "start", name])
                continue
            if arm == "embedding":
                template = (self.config.configs_root / "cortrix.embedding-only.yaml").read_text().replace("max_active: 10", "max_active: 64")
            else:
                # This route cannot authorize any request until a run is bound.
                template = self.full_config("run_0000000000000000", "runtime-not-yet-bound")
            secure_text(config / "cortrix.yaml", template)
            secure_text(config / "sensitive_fields.yaml", (self.config.core_source_root / "src/logging/sensitive_fields.yaml").read_text())
            volume = name + "-data"
            self.ensure_volume(volume, volumes)
            command(["docker", "run", "--rm", "--network", "none", "--mount", f"type=volume,src={volume},dst=/data",
                     "ubuntu:22.04", "chown", f"{os.getuid()}:{os.getgid()}", "/data"])
            command(["docker", "run", "-d", "--name", name, "--network", self.config.network_name,
                     "--user", f"{os.getuid()}:{os.getgid()}",
                     "--label", f"cortrix.demo.owner={self.config.owner_label}",
                     "--label", f"cortrix.demo.runtime_scope={self.scope_id}",
                     "--publish", f"127.0.0.1:{port}:8420",
                     "--mount", f"type=volume,src={volume},dst=/data,volume-nocopy",
                     "--mount", f"type=volume,src={self.config.model_volume},dst=/data/models,volume-subpath=models,readonly",
                     "--mount", f"type=bind,src={config},dst=/app/config,readonly",
                     "--mount", f"type=bind,src={self.config.helpers_root},dst=/demo-helpers,readonly",
                     "--env", "CORTRIX_SERVER_ALLOW_UNAUTHENTICATED_CONTAINER_BIND=true",
                     "--env", "CORTRIX_AGENT_ENABLED=false", "--env", "CORTRIX_QUICKSTART_BOOTSTRAP_ENABLED=false",
                     "--env", "CORTRIX_DATA_DIR=/data", "--entrypoint", "/app/cortrix_server", self.config.cortrix_image,
                     "--config", "/app/config/cortrix.yaml"])
        pg = self.name("pg")
        if pg in containers:
            existing_pg = json.loads(command(["docker", "inspect", pg]))[0]
            self.reuse_pg_container(existing_pg)
        else:
            self.ensure_volume(self.config.volume_name("pg"), volumes)
            command(["docker", "run", "-d", "--name", pg, "--network", self.config.network_name,
                     "--label", f"cortrix.demo.owner={self.config.owner_label}",
                     "--label", f"cortrix.demo.runtime_scope={self.scope_id}",
                     "--publish", f"127.0.0.1:{self.config.pg_port}:5432", "--mount", f"type=volume,src={self.config.volume_name('pg')},dst=/var/lib/postgresql/data",
                     "--env", "POSTGRES_DB=cortrix_demo", "--env", "POSTGRES_USER=cortrix_demo",
                     "--env", "POSTGRES_PASSWORD=local-demo-only", "pgvector/pgvector:pg16"])
        health = self.readiness()
        for _ in range(60):
            result = subprocess.run(["docker", "exec", pg, "pg_isready", "-U", "cortrix_demo", "-d", "cortrix_demo"], capture_output=True)
            if result.returncode == 0:
                break
            time.sleep(1)
        command(["docker", "exec", pg, "psql", "-U", "cortrix_demo", "-d", "cortrix_demo", "-v", "ON_ERROR_STOP=1", "-c", "CREATE EXTENSION IF NOT EXISTS vector;"])
        identity = {"release": CORTRIX_RELEASE, "source_revision": REVISION,
                    "image": self.config.cortrix_image, "image_digest": image["Id"], "model_hashes": actual,
                    "release_tag_verified": True, "source_identity": source_identity,
                    "baseline_basis": "verified_clean_rc2_annotated_tag",
                    "release_url": "https://github.com/cortrix/cortrix/releases/tag/v1.0.0-rc.2",
                    "annotated_tag_sha": source_identity["tag_object"],
                    "container_prefix": self.config.container_prefix, "runtime_scope": self.scope_id,
                    "data_volumes": {arm: self.config.volume_name(arm) for arm in ("embedding", "full", "pg")},
                    "health": health, "checked_at": stamp(), "external_model_calls": 0}
        atomic(self.root / "runtime-identity.json", identity)
        print(json.dumps({"status": "prepared", "image_digest": image["Id"], "source_revision": REVISION,
                          "external_model_calls": 0, "release_tag_verified": True}))


def provision(config: RuntimeConfig) -> None:
    """Run the explicit, operator-invoked container preflight and provisioning step."""
    RuntimeManager(config=config).prepare()


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("action", choices=["prepare"])
    parser.add_argument("--config")
    args = parser.parse_args()
    provision(load_config(args.config))
