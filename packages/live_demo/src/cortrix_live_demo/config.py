"""Configuration and validation for the live three-path implementation candidate."""

from __future__ import annotations

from dataclasses import asdict, dataclass, fields
import ipaddress
import json
import math
import os
from pathlib import Path
import re
from typing import Any, Mapping
from urllib.parse import urlsplit


SCENARIO_ID = "order-api-live-three-path"
CONTRACT_VERSION = "live_three_path/v1"
CORTRIX_RELEASE = "v1.0.0-rc.2"
CORTRIX_COMMIT = "d298d6b7e64c67551f567e7cddd514bae1adb57b"
HARNESS_REPOSITORY = "https://github.com/deepseek-ai/deepseek-harness"
HARNESS_COMMIT = "99f6f02fecdb7dff40c3fbc9470f5907c29f74ca"
PACKAGE_ROOT = Path(__file__).resolve().parents[2]
ENV_PREFIX = "CORTRIX_LIVE_DEMO_"
PATH_FIELDS = {
    "runtime_root", "helpers_root", "configs_root", "core_source_root",
    "harness_root", "fixtures_root", "provider_secret_file",
}
PORT_FIELDS = {"port", "internal_port", "embedding_port", "full_port", "pg_port"}


class ConfigurationError(ValueError):
    """The runtime configuration is missing, unsafe, or inconsistent."""


@dataclass(frozen=True)
class RuntimeConfig:
    bind_host: str
    port: int
    operator_origin: str
    internal_bind_host: str
    internal_port: int
    core_callback_base_url: str
    runtime_root: Path
    helpers_root: Path
    configs_root: Path
    model_volume: str
    cortrix_image: str
    core_source_root: Path
    container_prefix: str
    network_subnet: str
    network_gateway: str
    embedding_port: int
    full_port: int
    pg_port: int
    harness_root: Path
    fixtures_root: Path
    allow_external_calls: bool
    budget_total_usd: float
    budget_deterministic_usd: float
    budget_harness_usd: float
    provider_input_cache_hit_usd_per_million: float | None
    provider_input_cache_miss_usd_per_million: float | None
    provider_output_usd_per_million: float | None
    provider_secret_file: Path | None = None
    scenario_id: str = SCENARIO_ID
    contract_version: str = CONTRACT_VERSION
    cortrix_release: str = CORTRIX_RELEASE
    cortrix_commit: str = CORTRIX_COMMIT
    harness_repository: str = HARNESS_REPOSITORY
    harness_commit: str = HARNESS_COMMIT
    provider_model: str = "deepseek-v4-flash"
    provider_base_url: str = "https://api.deepseek.com/v1"

    @property
    def listen_url(self) -> str:
        return f"http://{self.bind_host}:{self.port}"

    @property
    def network_name(self) -> str:
        return self.container_prefix

    @property
    def owner_label(self) -> str:
        return self.container_prefix

    def container_name(self, component: str) -> str:
        if component not in {"embedding", "full", "pg"}:
            raise ConfigurationError("Unknown runtime component")
        return f"{self.container_prefix}-{component}"

    def volume_name(self, component: str) -> str:
        return self.container_name(component) + "-data"

    def component_port(self, component: str) -> int:
        return {"embedding": self.embedding_port, "full": self.full_port, "pg": self.pg_port}[component]

    def execution_identity(self) -> dict[str, Any]:
        value = asdict(self)
        value.pop("provider_secret_file", None)
        return {key: str(item) if isinstance(item, Path) else item for key, item in value.items()}

    def public_identity(self) -> dict[str, Any]:
        value = self.execution_identity()
        for name in PATH_FIELDS:
            value.pop(name, None)
        value["paths_configured"] = True
        value["provider_secret_file_configured"] = self.provider_secret_file is not None
        return value


def _defaults(base: Path) -> dict[str, Any]:
    return {
        "bind_host": "127.0.0.1",
        "port": 4186,
        "operator_origin": "http://127.0.0.1:4186",
        "internal_bind_host": None,
        "internal_port": None,
        "core_callback_base_url": None,
        "runtime_root": base / ".runtime",
        "helpers_root": base / "runtime-support" / "helpers",
        "configs_root": base / "runtime-support" / "config",
        "model_volume": "cortrix-live-demo-models",
        "cortrix_image": "cortrix-live-demo-core:rc2",
        "core_source_root": base / "runtime-support" / "rc2-source",
        "container_prefix": "cortrix-live-demo",
        "network_subnet": None,
        "network_gateway": None,
        "embedding_port": 18426,
        "full_port": 18427,
        "pg_port": 15436,
        "harness_root": base / "runtime-support" / "harness",
        "fixtures_root": base / "runtime-support" / "fixtures",
        "allow_external_calls": False,
        "budget_total_usd": 1.0,
        "budget_deterministic_usd": 0.3,
        "budget_harness_usd": 0.7,
        "provider_input_cache_hit_usd_per_million": None,
        "provider_input_cache_miss_usd_per_million": None,
        "provider_output_usd_per_million": None,
        "provider_secret_file": None,
        "scenario_id": SCENARIO_ID,
        "contract_version": CONTRACT_VERSION,
        "cortrix_release": CORTRIX_RELEASE,
        "cortrix_commit": CORTRIX_COMMIT,
        "harness_repository": HARNESS_REPOSITORY,
        "harness_commit": HARNESS_COMMIT,
        "provider_model": "deepseek-v4-flash",
        "provider_base_url": "https://api.deepseek.com/v1",
    }


def _read_file(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ConfigurationError("Cannot read runtime configuration") from exc
    if not isinstance(value, dict):
        raise ConfigurationError("Runtime configuration must be a JSON object")
    known = {item.name for item in fields(RuntimeConfig)}
    unknown = sorted(set(value) - known)
    if unknown:
        raise ConfigurationError("Unknown runtime configuration fields: " + ", ".join(unknown))
    return value


def _path(name: str, value: Any, base: Path, optional: bool = False) -> Path | None:
    if optional and value in {None, ""}:
        return None
    if not isinstance(value, (str, os.PathLike)):
        raise ConfigurationError(f"{name} must be a filesystem path")
    path = Path(value).expanduser()
    if not path.is_absolute():
        path = base / path
    path = path.resolve(strict=False)
    if path == Path(path.anchor) or len(path.parts) < 3:
        raise ConfigurationError(f"{name} is too broad")
    return path


def _url(name: str, value: Any, schemes: set[str]) -> str:
    if not isinstance(value, str):
        raise ConfigurationError(f"{name} must be a URL")
    parsed = urlsplit(value)
    if parsed.scheme not in schemes or not parsed.hostname or parsed.username or parsed.password or parsed.query or parsed.fragment:
        raise ConfigurationError(f"{name} is invalid")
    if parsed.path not in {"", "/", "/v1"}:
        raise ConfigurationError(f"{name} has an unexpected path")
    return value.rstrip("/")


def _port(name: str, value: Any) -> int:
    if isinstance(value, bool):
        raise ConfigurationError(f"{name} must be an integer port")
    try:
        port = int(value)
    except (TypeError, ValueError) as exc:
        raise ConfigurationError(f"{name} must be an integer port") from exc
    if not 1 <= port <= 65535:
        raise ConfigurationError(f"{name} must be between 1 and 65535")
    return port


def _number(name: str, value: Any, optional: bool = False) -> float | None:
    if optional and value is None:
        return None
    if isinstance(value, bool):
        raise ConfigurationError(f"{name} must be a nonnegative number")
    try:
        number = float(value)
    except (TypeError, ValueError) as exc:
        raise ConfigurationError(f"{name} must be a nonnegative number") from exc
    if not math.isfinite(number) or number < 0:
        raise ConfigurationError(f"{name} must be a nonnegative number")
    return number


def load_config(config_file: str | os.PathLike[str] | None = None, environment: Mapping[str, str] | None = None) -> RuntimeConfig:
    """Load repository-relative defaults, a JSON file, then environment overrides."""
    env = os.environ if environment is None else environment
    selected = config_file or env.get(ENV_PREFIX + "CONFIG_FILE")
    config_path = Path(selected).expanduser().resolve(strict=False) if selected else None
    base = config_path.parent if config_path else PACKAGE_ROOT
    values = _defaults(base)
    if config_path:
        values.update(_read_file(config_path))
    for item in fields(RuntimeConfig):
        key = ENV_PREFIX + item.name.upper()
        if key in env:
            values[item.name] = env[key]
    for name in PATH_FIELDS:
        values[name] = _path(name, values[name], base, optional=name == "provider_secret_file")
    for name in PORT_FIELDS:
        values[name] = _port(name, values[name])
    values["operator_origin"] = _url("operator_origin", values["operator_origin"], {"http"})
    values["core_callback_base_url"] = _url("core_callback_base_url", values["core_callback_base_url"], {"http"})
    values["provider_base_url"] = _url("provider_base_url", values["provider_base_url"], {"https"})
    if values["bind_host"] != "127.0.0.1":
        raise ConfigurationError("The operator surface must bind to 127.0.0.1")
    operator = urlsplit(values["operator_origin"])
    if operator.hostname != values["bind_host"] or operator.port != values["port"]:
        raise ConfigurationError("operator_origin must match the loopback listener")
    try:
        subnet = ipaddress.ip_network(str(values["network_subnet"]), strict=True)
        gateway = ipaddress.ip_address(str(values["network_gateway"]))
        internal = ipaddress.ip_address(str(values["internal_bind_host"]))
    except ValueError as exc:
        raise ConfigurationError("A dedicated RFC1918 subnet, gateway, and internal bind address are required") from exc
    rfc1918 = (
        ipaddress.ip_network((10 << 24, 8)),
        ipaddress.ip_network(((172 << 24) | (16 << 16), 12)),
        ipaddress.ip_network(((192 << 24) | (168 << 16), 16)),
    )
    if subnet.version != 4 or not any(subnet.subnet_of(block) for block in rfc1918):
        raise ConfigurationError("network_subnet must be a dedicated RFC 1918 IPv4 network")
    if gateway not in subnet or gateway in {subnet.network_address, subnet.broadcast_address} or internal != gateway:
        raise ConfigurationError("The internal bind address must equal the usable dedicated network gateway")
    values["network_subnet"], values["network_gateway"], values["internal_bind_host"] = str(subnet), str(gateway), str(internal)
    callback = urlsplit(values["core_callback_base_url"])
    if callback.hostname != values["internal_bind_host"] or callback.port != values["internal_port"]:
        raise ConfigurationError("core_callback_base_url must match the internal listener")
    ports = [values[name] for name in PORT_FIELDS]
    if len(ports) != len(set(ports)):
        raise ConfigurationError("Listener and component ports must be distinct")
    for name in ("container_prefix", "model_volume"):
        if not isinstance(values[name], str) or not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.-]{0,127}", values[name]):
            raise ConfigurationError(f"{name} contains unsafe characters")
    if not isinstance(values["cortrix_image"], str) or not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.:/@-]{0,199}", values["cortrix_image"]):
        raise ConfigurationError("cortrix_image contains unsafe characters")
    for name in ("allow_external_calls",):
        if isinstance(values[name], str):
            if values[name].lower() not in {"true", "false"}:
                raise ConfigurationError(f"{name} must be true or false")
            values[name] = values[name].lower() == "true"
        if not isinstance(values[name], bool):
            raise ConfigurationError(f"{name} must be a boolean")
    values["budget_total_usd"] = _number("budget_total_usd", values["budget_total_usd"])
    values["budget_deterministic_usd"] = _number("budget_deterministic_usd", values["budget_deterministic_usd"])
    values["budget_harness_usd"] = _number("budget_harness_usd", values["budget_harness_usd"])
    for name in ("provider_input_cache_hit_usd_per_million", "provider_input_cache_miss_usd_per_million", "provider_output_usd_per_million"):
        values[name] = _number(name, values[name], optional=True)
    if values["budget_deterministic_usd"] + values["budget_harness_usd"] > values["budget_total_usd"]:
        raise ConfigurationError("Mode budgets exceed the total budget")
    fixed = {
        "scenario_id": SCENARIO_ID, "contract_version": CONTRACT_VERSION,
        "cortrix_release": CORTRIX_RELEASE, "cortrix_commit": CORTRIX_COMMIT,
        "harness_repository": HARNESS_REPOSITORY, "harness_commit": HARNESS_COMMIT,
    }
    for name, expected in fixed.items():
        if values[name] != expected:
            raise ConfigurationError(f"{name} does not match the public live_three_path/v1 contract")
    runtime_root = values["runtime_root"]
    for name in ("helpers_root", "configs_root", "core_source_root", "harness_root", "fixtures_root", "provider_secret_file"):
        path = values[name]
        if path is not None and (path == runtime_root or path.is_relative_to(runtime_root) or runtime_root.is_relative_to(path)):
            raise ConfigurationError(f"{name} must not overlap runtime_root")
    return RuntimeConfig(**values)


def validate_config(config_file: str | os.PathLike[str] | None = None, environment: Mapping[str, str] | None = None) -> dict[str, Any]:
    """Return a secret-free configuration identity for CLI and embedding callers."""
    config = load_config(config_file, environment)
    return {"status": "valid", "scenario_id": config.scenario_id, "contract_version": config.contract_version, "config": config.public_identity()}


def load_provider_secret(config: RuntimeConfig, environment: Mapping[str, str] | None = None) -> str:
    """Resolve the provider key only after an authorized request reserves budget."""
    if not config.allow_external_calls:
        raise ConfigurationError("External model calls are disabled by configuration")
    env = os.environ if environment is None else environment
    key = env.get("DEEPSEEK_API_KEY")
    if key is None and config.provider_secret_file is not None:
        try:
            stat = config.provider_secret_file.stat()
            if stat.st_mode & 0o077:
                raise ConfigurationError("The provider secret file must have mode 0600 or stricter")
            key = config.provider_secret_file.read_text(encoding="utf-8").strip()
        except OSError as exc:
            raise ConfigurationError("Cannot read the provider secret file") from exc
    if not key or len(key) < 16 or any(character.isspace() for character in key):
        raise ConfigurationError("DEEPSEEK_API_KEY or provider_secret_file must supply a valid runtime key")
    return key
