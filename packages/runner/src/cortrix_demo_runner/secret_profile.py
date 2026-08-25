from __future__ import annotations

from dataclasses import dataclass, field
import json
import os
from pathlib import Path
import re
import stat
from typing import Mapping
from urllib.parse import urlparse

from .errors import DemoContractError


PROFILE_POINTER_ENV = "CORTRIX_LLM_SECRET_FILE"
DEFAULT_PROFILE_RELATIVE_PATH = Path("cortrix/secrets/llm/current.yaml")
MAX_PROFILE_BYTES = 64 * 1024
MIN_SECRET_LENGTH = 20


@dataclass(frozen=True)
class SecretResolution:
    value: str = field(repr=False)
    source: str


def resolve_secret(
    secret_env: str,
    *,
    expected_model: str | None = None,
    expected_base_url: str | None = None,
    environment: Mapping[str, str] | None = None,
) -> SecretResolution:
    values = os.environ if environment is None else environment
    explicit_value = values.get(secret_env, "").strip()
    if explicit_value:
        _require_secret_length(explicit_value, secret_env, "environment")
        return SecretResolution(explicit_value, "environment")

    pointer = values.get(PROFILE_POINTER_ENV, "").strip()
    if pointer:
        profile_path = Path(pointer).expanduser()
        if not profile_path.is_absolute():
            raise _profile_error(
                "The selected LLM secret profile path must be absolute",
                secret_env,
                "explicit_profile",
                code="CX_DEMO_SECRET_PROFILE_INVALID",
            )
        source = "explicit_profile"
    else:
        profile_path = _default_profile_path(values)
        source = "default_profile"

    if not profile_path.exists():
        raise _missing_secret(secret_env)
    profile = _read_profile(profile_path, secret_env, source)
    _verify_profile_identity(profile, secret_env, source, expected_model, expected_base_url)
    secret_value = profile.get("api_key", "").strip()
    _require_secret_length(secret_value, secret_env, source)
    return SecretResolution(secret_value, source)


def secret_value_for_redaction(
    secret_env: str,
    *,
    expected_model: str | None = None,
    expected_base_url: str | None = None,
) -> str:
    try:
        return resolve_secret(
            secret_env,
            expected_model=expected_model,
            expected_base_url=expected_base_url,
        ).value
    except DemoContractError:
        return ""


def _default_profile_path(environment: Mapping[str, str]) -> Path:
    configured_home = environment.get("XDG_CONFIG_HOME", "").strip()
    if configured_home:
        config_home = Path(configured_home).expanduser()
        if not config_home.is_absolute():
            return Path("/__cortrix_invalid_relative_xdg_config_home__")
    else:
        home = environment.get("HOME", "").strip()
        config_home = Path(home).expanduser() / ".config" if home else Path.home() / ".config"
    return config_home / DEFAULT_PROFILE_RELATIVE_PATH


def _read_profile(path: Path, secret_env: str, source: str) -> dict[str, object]:
    try:
        resolved = path.resolve(strict=True)
        metadata = resolved.stat()
    except (OSError, RuntimeError) as exc:
        raise _profile_error(
            "The selected LLM secret profile cannot be read",
            secret_env,
            source,
            code="CX_DEMO_SECRET_PROFILE_INVALID",
        ) from exc
    if not stat.S_ISREG(metadata.st_mode):
        raise _profile_error(
            "The selected LLM secret profile is not a regular file",
            secret_env,
            source,
            code="CX_DEMO_SECRET_PROFILE_INVALID",
        )
    if os.name == "posix":
        if metadata.st_uid != os.geteuid() or stat.S_IMODE(metadata.st_mode) & 0o077:
            raise _profile_error(
                "The selected LLM secret profile owner or permissions are unsafe",
                secret_env,
                source,
                code="CX_DEMO_SECRET_PROFILE_UNSAFE",
            )
    if metadata.st_size > MAX_PROFILE_BYTES:
        raise _profile_error(
            "The selected LLM secret profile is too large",
            secret_env,
            source,
            code="CX_DEMO_SECRET_PROFILE_INVALID",
        )
    try:
        text = resolved.read_text(encoding="utf-8")
    except (OSError, UnicodeError) as exc:
        raise _profile_error(
            "The selected LLM secret profile cannot be read as UTF-8",
            secret_env,
            source,
            code="CX_DEMO_SECRET_PROFILE_INVALID",
        ) from exc
    if "\x00" in text:
        raise _profile_error(
            "The selected LLM secret profile is malformed",
            secret_env,
            source,
            code="CX_DEMO_SECRET_PROFILE_INVALID",
        )
    return {
        "api_key": _top_level_scalar(text, "api_key", secret_env, source),
        "base_url": _top_level_scalar(text, "base_url", secret_env, source),
        "models": _model_scalars(text, secret_env, source),
    }


def _top_level_scalar(text: str, key: str, secret_env: str, source: str) -> str:
    matches = re.findall(rf"^{re.escape(key)}[ \t]*:[ \t]*(.+?)[ \t]*$", text, flags=re.MULTILINE)
    if len(matches) != 1:
        raise _profile_error(
            f"The selected LLM secret profile must contain exactly one top-level {key} field",
            secret_env,
            source,
            code="CX_DEMO_SECRET_PROFILE_INVALID",
        )
    return _decode_scalar(matches[0], secret_env, source)


def _model_scalars(text: str, secret_env: str, source: str) -> set[str]:
    values = re.findall(r"^[ \t]+model[ \t]*:[ \t]*(.+?)[ \t]*$", text, flags=re.MULTILINE)
    if not values:
        raise _profile_error(
            "The selected LLM secret profile does not declare a role model",
            secret_env,
            source,
            code="CX_DEMO_SECRET_PROFILE_INVALID",
        )
    return {_decode_scalar(value, secret_env, source) for value in values}


def _decode_scalar(value: str, secret_env: str, source: str) -> str:
    value = value.strip()
    if not value:
        return ""
    if value.startswith('"'):
        try:
            decoded = json.loads(value)
        except json.JSONDecodeError as exc:
            raise _profile_error(
                "The selected LLM secret profile contains an invalid quoted scalar",
                secret_env,
                source,
                code="CX_DEMO_SECRET_PROFILE_INVALID",
            ) from exc
        return decoded if isinstance(decoded, str) else ""
    if value.startswith("'"):
        if len(value) < 2 or not value.endswith("'"):
            raise _profile_error(
                "The selected LLM secret profile contains an invalid quoted scalar",
                secret_env,
                source,
                code="CX_DEMO_SECRET_PROFILE_INVALID",
            )
        return value[1:-1].replace("''", "'")
    if " #" in value:
        value = value.split(" #", 1)[0].rstrip()
    if any(character.isspace() for character in value):
        raise _profile_error(
            "The selected LLM secret profile contains an unsupported scalar",
            secret_env,
            source,
            code="CX_DEMO_SECRET_PROFILE_INVALID",
        )
    return value


def _verify_profile_identity(
    profile: dict[str, object],
    secret_env: str,
    source: str,
    expected_model: str | None,
    expected_base_url: str | None,
) -> None:
    models = profile["models"]
    if expected_model and (not isinstance(models, set) or models != {expected_model}):
        raise _profile_error(
            "The selected LLM secret profile model does not match the scenario contract",
            secret_env,
            source,
            code="CX_DEMO_SECRET_PROFILE_MISMATCH",
        )
    if expected_base_url:
        configured_url = profile["base_url"]
        if not isinstance(configured_url, str) or _normalize_base_url(configured_url) != _normalize_base_url(expected_base_url):
            raise _profile_error(
                "The selected LLM secret profile endpoint does not match the scenario contract",
                secret_env,
                source,
                code="CX_DEMO_SECRET_PROFILE_MISMATCH",
            )


def _normalize_base_url(value: str) -> tuple[str, str, str]:
    parsed = urlparse(value.rstrip("/"))
    path = parsed.path.rstrip("/")
    if path == "/v1":
        path = ""
    return parsed.scheme.lower(), (parsed.hostname or "").lower(), path


def _require_secret_length(value: str, secret_env: str, source: str) -> None:
    if len(value) < MIN_SECRET_LENGTH:
        if source == "environment":
            raise _missing_secret(secret_env)
        raise _profile_error(
            "The selected LLM secret profile does not contain a usable key",
            secret_env,
            source,
            code="CX_DEMO_SECRET_PROFILE_INVALID",
        )


def _missing_secret(secret_env: str) -> DemoContractError:
    return DemoContractError(
        f"{secret_env} is missing and no usable local profile was found; no external call was made",
        code="CX_DEMO_SECRET_MISSING",
        category="auth",
        structured_data={
            "secret_env": secret_env,
            "profile_pointer_env": PROFILE_POINTER_ENV,
            "default_profile_supported": True,
            "external_calls_made": False,
            "next_action": "Set the declared secret environment variable or configure a protected local LLM profile, then rerun preflight.",
        },
    )


def _profile_error(message: str, secret_env: str, source: str, *, code: str) -> DemoContractError:
    return DemoContractError(
        message + "; no external call was made",
        code=code,
        category="auth",
        structured_data={
            "secret_env": secret_env,
            "secret_source": source,
            "external_calls_made": False,
            "next_action": "Repair or replace the selected local LLM profile, then rerun preflight.",
        },
    )
