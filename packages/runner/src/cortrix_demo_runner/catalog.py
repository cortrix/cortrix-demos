from __future__ import annotations

from pathlib import Path
from typing import Any

from .errors import DemoContractError
from .io import read_json


REGISTRY_PATH = Path("scenarios/registry.json")
ADAPTER_REGISTRY_PATH = Path("runtime/adapters/registry.json")
EXTERNAL_POLICY_PATH = Path("config/external-call-policy.json")


def _require_relative_file(root: Path, value: object, label: str) -> Path:
    if not isinstance(value, str) or not value or Path(value).is_absolute():
        raise DemoContractError(f"{label} must be a non-empty relative path")
    resolved_root = root.resolve()
    path = (root / value).resolve()
    if path != resolved_root and resolved_root not in path.parents:
        raise DemoContractError(f"{label} escapes its registry root")
    if not path.is_file():
        raise DemoContractError(f"{label} does not exist", structured_data={"path": value})
    return path


def load_scenario_registry(root: Path) -> dict[str, Any]:
    registry = read_json(root / REGISTRY_PATH)
    if registry.get("schema_version") != 1 or not isinstance(registry.get("scenarios"), list):
        raise DemoContractError("Scenario registry schema is invalid")
    return registry


def list_scenarios(root: Path) -> list[dict[str, Any]]:
    scenarios = load_scenario_registry(root)["scenarios"]
    ids = [item.get("id") for item in scenarios if isinstance(item, dict)]
    if len(ids) != len(scenarios) or any(not isinstance(value, str) or not value for value in ids) or len(set(ids)) != len(ids):
        raise DemoContractError("Scenario registry contains invalid or duplicate IDs")
    return scenarios


def scenario_entry(root: Path, scenario_id: str) -> dict[str, Any]:
    for item in list_scenarios(root):
        if item["id"] == scenario_id:
            return item
    raise DemoContractError(
        "Unknown scenario",
        code="CX_DEMO_SCENARIO_NOT_FOUND",
        category="input",
        structured_data={"scenario_id": scenario_id},
    )


def load_adapter_registry(root: Path) -> dict[str, Any]:
    registry = read_json(root / ADAPTER_REGISTRY_PATH)
    if registry.get("schema_version") != 1:
        raise DemoContractError("Adapter registry schema is invalid")
    for key in ("baselines", "llm_providers"):
        if not isinstance(registry.get(key), list):
            raise DemoContractError(f"Adapter registry {key} list is missing")
    return registry


def adapter_entry(root: Path, kind: str, adapter_id: str) -> dict[str, Any]:
    key = "baselines" if kind == "baseline" else "llm_providers" if kind == "llm_provider" else None
    if key is None:
        raise DemoContractError("Unknown adapter kind", structured_data={"kind": kind})
    for item in load_adapter_registry(root)[key]:
        if isinstance(item, dict) and item.get("id") == adapter_id:
            return item
    raise DemoContractError(
        "Unknown adapter",
        code="CX_DEMO_ADAPTER_NOT_FOUND",
        category="input",
        structured_data={"kind": kind, "adapter_id": adapter_id},
    )


def load_adapter_profile(root: Path, kind: str, adapter_id: str, *, require_implemented: bool = False) -> dict[str, Any]:
    entry = adapter_entry(root, kind, adapter_id)
    status = entry.get("support_status")
    if require_implemented and status != "implemented":
        raise DemoContractError(
            "Adapter is not implemented",
            code="CX_DEMO_ADAPTER_UNSUPPORTED",
            category="capability",
            structured_data={"kind": kind, "adapter_id": adapter_id, "support_status": status},
        )
    if status != "implemented":
        return {"id": adapter_id, "support_status": status}
    path = _require_relative_file(root / "runtime" / "adapters", entry.get("profile"), "Adapter profile")
    profile = read_json(path)
    if profile.get("id") != adapter_id or profile.get("support_status") != "implemented":
        raise DemoContractError("Implemented adapter profile identity is invalid")
    return profile


def load_external_call_policy(root: Path) -> dict[str, Any]:
    policy = read_json(root / EXTERNAL_POLICY_PATH)
    budget = policy.get("budget_usd")
    if policy.get("schema_version") != 1 or not isinstance(budget, (int, float)) or not 0 < float(budget) <= 1.0:
        raise DemoContractError("External-call policy must cap new execution at or below USD 1.00")
    if policy.get("local_generative_fallback_allowed") is not False:
        raise DemoContractError("External-call policy must prohibit local generative fallback")
    return policy


def describe_scenario(root: Path, scenario_id: str) -> dict[str, Any]:
    entry = scenario_entry(root, scenario_id)
    scenario_path = _require_relative_file(root / "scenarios", entry.get("scenario_contract"), "Scenario contract")
    technology_path = _require_relative_file(root / "scenarios", entry.get("technology_profile"), "Technology profile")
    scenario = read_json(scenario_path)
    technology = read_json(technology_path)
    if scenario.get("id") != scenario_id or technology.get("scenario_id") != scenario_id:
        raise DemoContractError("Scenario catalog identity does not match its contracts")
    baseline_id = technology.get("baseline", {}).get("adapter_id")
    llm_id = technology.get("llm", {}).get("adapter_id")
    if not isinstance(baseline_id, str) or not isinstance(llm_id, str):
        raise DemoContractError("Technology profile adapter identity is incomplete")
    baseline = load_adapter_profile(root, "baseline", baseline_id)
    llm = load_adapter_profile(root, "llm_provider", llm_id)
    policy = load_external_call_policy(root)
    accepted_path = _require_relative_file(technology_path.parent.parent, technology.get("accepted_evidence"), "Accepted evidence pointer")
    accepted = read_json(accepted_path)
    return {
        "schema_version": 1,
        "scenario": {
            "id": scenario_id,
            "display_name": scenario.get("display_name"),
            "version": scenario.get("scenario_version"),
            "status": entry.get("status"),
            "synthetic_data": scenario.get("synthetic_data"),
        },
        "technology_profile": technology,
        "adapter_support": {
            "baseline": {"id": baseline_id, "support_status": baseline.get("support_status")},
            "llm_provider": {"id": llm_id, "support_status": llm.get("support_status")},
        },
        "accepted_evidence": {
            "status": accepted.get("status"),
            "run_id": accepted.get("run_id"),
            "pointer": str(technology.get("accepted_evidence")),
        },
        "external_call_policy": {
            "budget_usd": policy["budget_usd"],
            "manual_authorization_required": policy.get("manual_authorization_required"),
            "local_generative_fallback_allowed": policy.get("local_generative_fallback_allowed"),
        },
        "lifecycle": ["discover", "describe", "validate", "preflight", "provision", "run", "inspect", "verify", "cleanup"],
        "review_gates": {
            "independent_clean_run": "required",
            "human_review_required_for": ["remote_publication"],
            "human_guide": entry.get("human_guide"),
        },
    }


def require_runnable_scenario(root: Path, scenario_id: str, compatibility_profile: str) -> dict[str, Any]:
    description = describe_scenario(root, scenario_id)
    technology = description["technology_profile"]
    profiles = technology.get("compatibility_profiles")
    if not isinstance(profiles, list) or compatibility_profile not in profiles:
        raise DemoContractError(
            "Scenario profile is not available",
            code="CX_DEMO_PROFILE_NOT_FOUND",
            category="input",
            structured_data={"scenario_id": scenario_id, "profile": compatibility_profile},
        )
    load_adapter_profile(root, "baseline", technology["baseline"]["adapter_id"], require_implemented=True)
    load_adapter_profile(root, "llm_provider", technology["llm"]["adapter_id"], require_implemented=True)
    return description


def validate_catalog(root: Path) -> list[str]:
    failures: list[str] = []
    try:
        scenarios = list_scenarios(root)
        if not scenarios:
            failures.append("Scenario registry is empty")
        for entry in scenarios:
            describe_scenario(root, entry["id"])
        registry = load_adapter_registry(root)
        for kind, key in (("baseline", "baselines"), ("llm_provider", "llm_providers")):
            ids: list[str] = []
            for entry in registry[key]:
                if not isinstance(entry, dict) or not isinstance(entry.get("id"), str):
                    failures.append(f"Adapter registry {key} contains an invalid entry")
                    continue
                ids.append(entry["id"])
                load_adapter_profile(root, kind, entry["id"])
            if len(ids) != len(set(ids)):
                failures.append(f"Adapter registry {key} contains duplicate IDs")
    except (DemoContractError, OSError, ValueError) as exc:
        failures.append(str(exc))
    return failures
