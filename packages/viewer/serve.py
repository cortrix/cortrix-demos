from __future__ import annotations

import argparse
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
import json
from pathlib import Path
import re
import sys
from urllib.parse import urlsplit


LOOPBACK = "127.0.0.1"
CANDIDATE_QA_ROUTE = "/packages/viewer/candidate-qa.html"
CANDIDATE_QA_CONFIG_ROUTE = "/__cortrix_candidate_qa_config__.json"
HARNESS_ROUTE = "/packages/viewer/harness.html"
HARNESS_CONFIG_ROUTE = "/__cortrix_harness_viewer_config__.json"
RUN_ID_PATTERN = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]{0,127}")
HARNESS_SCENARIOS = {"database-change-conflict-guardian", "api-version-drift-coding-agent", "payment-incident-shift-handoff", "migration-decision-recovery"}


class CandidateQAError(ValueError):
    """Raised when a local candidate cannot satisfy the read-only QA contract."""


class HarnessViewerError(ValueError):
    """Raised when an accepted Harness run cannot satisfy the viewer contract."""


def _relative_url(path: Path, root: Path) -> str:
    return "/" + path.relative_to(root).as_posix()


def _required_candidate_file(run_dir: Path, relative_path: object, label: str) -> Path:
    if not isinstance(relative_path, str) or not relative_path:
        raise CandidateQAError(f"Candidate manifest is missing {label}.")
    candidate = (run_dir / relative_path).resolve()
    try:
        candidate.relative_to(run_dir)
    except ValueError as exc:
        raise CandidateQAError(f"Candidate {label} escapes its run directory.") from exc
    if not candidate.is_file():
        raise CandidateQAError(f"Candidate {label} does not exist.")
    return candidate


def create_candidate_qa_config(root: Path, run_id: str) -> dict[str, object]:
    """Validate a candidate and return paths for a local, non-acceptance QA projection."""
    root = root.resolve()
    if not RUN_ID_PATTERN.fullmatch(run_id):
        raise CandidateQAError("Candidate run ID contains unsupported characters.")
    runs_root = (root / ".runs").resolve()
    run_dir = (runs_root / run_id).resolve()
    try:
        run_dir.relative_to(runs_root)
    except ValueError as exc:
        raise CandidateQAError("Candidate run directory escapes .runs.") from exc
    if not run_dir.is_dir():
        raise CandidateQAError("Candidate run directory does not exist.")
    manifest_path = (run_dir / "run-manifest.json").resolve()
    try:
        manifest_path.relative_to(run_dir)
    except ValueError as exc:
        raise CandidateQAError("Candidate run manifest escapes its run directory.") from exc
    if not manifest_path.is_file():
        raise CandidateQAError("Candidate run manifest does not exist.")
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise CandidateQAError("Candidate run manifest is not valid JSON.") from exc
    if manifest.get("run_id") != run_id or manifest.get("state") != "candidate":
        raise CandidateQAError("Candidate run identity or state does not match the requested QA run.")
    if manifest.get("screenshot_eligible") is not False or manifest.get("human_review_required") is not True:
        raise CandidateQAError("Candidate run does not preserve the review and screenshot eligibility gates.")
    if manifest.get("acceptance") is not None:
        raise CandidateQAError("Candidate QA cannot render a run with acceptance metadata.")
    run_a = _required_candidate_file(run_dir, manifest.get("run_a", {}).get("path"), "Run A evidence")
    resolver = _required_candidate_file(run_dir, manifest.get("resolver", {}).get("path"), "resolver evidence")
    base_config_path = root / "packages" / "viewer" / "viewer-config.json"
    try:
        base_config = json.loads(base_config_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise CandidateQAError("Viewer configuration is unavailable or invalid.") from exc

    def viewer_path(name: str) -> str:
        value = base_config.get(name)
        if not isinstance(value, str) or not value:
            raise CandidateQAError(f"Viewer configuration is missing {name}.")
        resolved = (base_config_path.parent / value).resolve()
        try:
            resolved.relative_to(root)
        except ValueError as exc:
            raise CandidateQAError(f"Viewer configuration path {name} escapes the repository.") from exc
        if not resolved.is_file():
            raise CandidateQAError(f"Viewer configuration path {name} does not exist.")
        return _relative_url(resolved, root)

    config: dict[str, object] = {
        "schema_version": 1,
        "mode": "candidate_qa",
        "scenario": base_config.get("scenario"),
        "scenario_metadata": viewer_path("scenario_metadata"),
        "technology_profile": viewer_path("technology_profile"),
        "candidate": {
            "run_id": run_id,
            "manifest": _relative_url(manifest_path, root),
            "run_a": _relative_url(run_a, root),
            "resolver": _relative_url(resolver, root),
        },
    }
    if base_config.get("locale"):
        config["locale"] = viewer_path("locale")
    return config


def create_harness_config(root: Path, scenario_id: str) -> dict[str, object]:
    """Validate one accepted Harness pointer and return a read-only viewer projection."""
    root = root.resolve()
    scenario_root = root / "scenarios" / scenario_id
    if scenario_id not in HARNESS_SCENARIOS:
        raise HarnessViewerError("Harness viewer scenario is not preregistered.")
    pointer_path = scenario_root / "evidence" / "accepted-run.json"
    try:
        pointer = json.loads(pointer_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise HarnessViewerError("Harness accepted-run pointer is unavailable or invalid.") from exc
    run_id = pointer.get("run_id")
    if pointer.get("status") != "accepted" or not isinstance(run_id, str) or not RUN_ID_PATTERN.fullmatch(run_id):
        raise HarnessViewerError("Harness scenario does not have an accepted run.")
    run_dir = (scenario_root / "evidence" / "runs" / run_id).resolve()
    try:
        run_dir.relative_to(root)
    except ValueError as exc:
        raise HarnessViewerError("Harness accepted run escapes the repository.") from exc

    def require_file(path: Path, label: str) -> str:
        resolved = path.resolve()
        try:
            resolved.relative_to(root)
        except ValueError as exc:
            raise HarnessViewerError(f"Harness viewer {label} escapes the repository.") from exc
        if not resolved.is_file() or resolved.is_symlink():
            raise HarnessViewerError(f"Harness viewer {label} is missing.")
        return _relative_url(resolved, root)

    manifest_path = run_dir / "run-manifest.json"
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise HarnessViewerError("Harness accepted manifest is unavailable or invalid.") from exc
    acceptance = manifest.get("acceptance")
    if manifest.get("state") != "accepted" or manifest.get("run_id") != run_id or manifest.get("scenario_id") != scenario_id or manifest.get("screenshot_eligible") is not True or manifest.get("human_review_required") is not False:
        raise HarnessViewerError("Harness accepted manifest identity or state is invalid.")
    if not isinstance(acceptance, dict) or acceptance.get("method") != "independent_clean_room" or acceptance.get("verdict") != "pass":
        raise HarnessViewerError("Harness accepted manifest has no passing independent Clean Room review.")
    paths = {
        "manifest": manifest_path,
        "run_a_summary": run_dir / "run-a" / "summary.json",
        "run_a_answer": run_dir / "run-a" / "answer.json",
        "run_a_resolver": run_dir / "run-a" / "resolver.json",
        "run_a_evidence": run_dir / "run-a" / "evidence.json",
        "run_b_summary": run_dir / "run-b" / "summary.json",
        "run_b_answer": run_dir / "run-b" / "answer.json",
        "run_b_resolver": run_dir / "run-b" / "resolver.json",
        "run_b_evidence": run_dir / "run-b" / "evidence-01.json",
        "runtime": run_dir / "runtime.json",
        "cleanup": run_dir / "cleanup.json",
        "review": run_dir / "clean-room-review.json",
        "scenario_metadata": scenario_root / "web" / "scenario.json",
        "locale": scenario_root / "web" / "locales" / "en-US.json",
        "technology_profile": scenario_root / "profiles" / "technology-profile.json",
    }
    result = {
        "schema_version": 1,
        "mode": "accepted_harness",
        "scenario_id": scenario_id,
        "run_id": run_id,
        **{name: require_file(path, name) for name, path in paths.items()},
    }
    position_variants = manifest.get("position_variants")
    if isinstance(position_variants, dict):
        result["position_variants"] = require_file(run_dir / str(position_variants.get("path", "")), "position variants")
    return result


def create_handler(root: Path, candidate_config: dict[str, object] | None, harness_config: dict[str, object] | None = None) -> type[SimpleHTTPRequestHandler]:
    index_path = root / "packages" / "viewer" / "index.html"
    harness_path = root / "packages" / "viewer" / "harness.html"

    class ViewerRequestHandler(SimpleHTTPRequestHandler):
        def _send_bytes(self, content: bytes, content_type: str) -> None:
            self.send_response(200)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(len(content)))
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(content)

        def do_GET(self) -> None:
            request_path = urlsplit(self.path).path
            if request_path == CANDIDATE_QA_ROUTE:
                if candidate_config is None:
                    self.send_error(404, "Candidate QA mode is not enabled.")
                    return
                self._send_bytes(index_path.read_bytes(), "text/html; charset=utf-8")
                return
            if request_path == CANDIDATE_QA_CONFIG_ROUTE:
                if candidate_config is None:
                    self.send_error(404, "Candidate QA mode is not enabled.")
                    return
                payload = json.dumps(candidate_config, sort_keys=True).encode("utf-8")
                self._send_bytes(payload, "application/json; charset=utf-8")
                return
            if request_path == HARNESS_ROUTE:
                if harness_config is None:
                    self.send_error(404, "Harness accepted viewer mode is not enabled.")
                    return
                self._send_bytes(harness_path.read_bytes(), "text/html; charset=utf-8")
                return
            if request_path == HARNESS_CONFIG_ROUTE:
                if harness_config is None:
                    self.send_error(404, "Harness accepted viewer mode is not enabled.")
                    return
                payload = json.dumps(harness_config, sort_keys=True).encode("utf-8")
                self._send_bytes(payload, "application/json; charset=utf-8")
                return
            super().do_GET()

    return ViewerRequestHandler


def create_server(
    preferred_bind: str,
    port: int,
    handler: type[SimpleHTTPRequestHandler] | partial = SimpleHTTPRequestHandler,
) -> tuple[ThreadingHTTPServer, str, bool]:
    try:
        return ThreadingHTTPServer((preferred_bind, port), handler), preferred_bind, False
    except OSError:
        if preferred_bind == LOOPBACK:
            raise
        return ThreadingHTTPServer((LOOPBACK, port), handler), LOOPBACK, True


def main() -> int:
    parser = argparse.ArgumentParser(description="Serve a read-only Cortrix demo evidence viewer from the repository root.")
    parser.add_argument("--bind", default=LOOPBACK)
    parser.add_argument("--port", type=int, default=18765)
    parser.add_argument("--candidate-run-id", help="Enable the local Candidate QA route for one validated .runs entry.")
    parser.add_argument("--harness-scenario", help="Enable the accepted Harness viewer for one registered scenario.")
    args = parser.parse_args()
    root = Path.cwd().resolve()
    candidate_config = None
    harness_config = None
    if args.candidate_run_id and args.harness_scenario:
        print(json.dumps({"error": {"code": "CX_DEMO_VIEWER_MODE_CONFLICT", "category": "permanent", "retryable": False, "message": "Candidate QA and accepted Harness modes cannot be enabled together.", "structured_data": {}}}), file=sys.stderr)
        return 1
    if args.candidate_run_id:
        try:
            candidate_config = create_candidate_qa_config(root, args.candidate_run_id)
        except CandidateQAError as exc:
            print(
                json.dumps(
                    {
                        "error": {
                            "code": "CX_DEMO_CANDIDATE_QA_INVALID",
                            "category": "permanent",
                            "retryable": False,
                            "message": str(exc),
                            "structured_data": {
                                "run_id": args.candidate_run_id,
                                "next_action": "Use a complete local candidate run that still requires human review.",
                            },
                        }
                    }
                ),
                file=sys.stderr,
            )
            return 1
    if args.harness_scenario:
        try:
            harness_config = create_harness_config(root, args.harness_scenario)
        except HarnessViewerError as exc:
            print(json.dumps({"error": {"code": "CX_DEMO_HARNESS_VIEWER_INVALID", "category": "permanent", "retryable": False, "message": str(exc), "structured_data": {"scenario_id": args.harness_scenario, "next_action": "Use an independently accepted Harness run."}}}), file=sys.stderr)
            return 1
    handler = partial(create_handler(root, candidate_config, harness_config), directory=str(root))
    try:
        server, actual_bind, used_fallback = create_server(args.bind, args.port, handler)
    except OSError as exc:
        print(
            json.dumps(
                {
                    "error": {
                        "code": "CX_DEMO_VIEWER_BIND_FAILED",
                        "category": "transient",
                        "retryable": True,
                        "retry_after_ms": 1000,
                        "message": str(exc),
                        "structured_data": {
                            "requested_bind": args.bind,
                            "port": args.port,
                            "next_action": "Choose an available local address or port and rerun the viewer.",
                        },
                    }
                }
            ),
            file=sys.stderr,
        )
        return 1
    mode = "candidate_qa" if candidate_config else "accepted_harness" if harness_config else "accepted"
    route = CANDIDATE_QA_ROUTE if candidate_config else f"{HARNESS_ROUTE}?scenario={args.harness_scenario}" if harness_config else "/packages/viewer/index.html"
    print(
        json.dumps(
            {
                "status": "serving",
                "mode": mode,
                "bind": actual_bind,
                "port": args.port,
                "route": route,
                "run_id": args.candidate_run_id or (harness_config or {}).get("run_id"),
                "scenario_id": args.harness_scenario,
                "fallback_used": used_fallback,
            }
        ),
        flush=True,
    )
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
