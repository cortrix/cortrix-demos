"""Read-only, source-bound application inventory for the live demo.

Python ownership follows AST function and method spans. JavaScript adapters are
assigned as complete files; their comments are classified lexically, not by an
invented JavaScript AST. SQL is a non-additive view of the same source lines.
"""

from __future__ import annotations

import ast
import hashlib
import io
from pathlib import Path
import re
import tokenize
from typing import Any
from .config import PACKAGE_ROOT


ROOT = Path(__file__).resolve().parent
ALL_PATHS = ("a0", "a1", "pg", "b")
PG_PATHS = ("a0", "a1", "pg")
HARNESS_PATHS = ("pg", "b")
CURRENT_PATHS = ("a1", "pg", "b")
ASSIST_PATHS = ("a1", "pg")
MEASURES = ("lines", "blank_lines", "comment_lines", "code_lines")

PG_SYMBOLS = {
    "sql_quote", "vector_literal", "Engines._sql", "Engines._sql_json",
    "Engines._export", "Engines._pg_snapshot", "Engines._pg_write",
    "Engines._pg_search", "Engines._pg_query", "Engines.cleanup_exports",
}
FULL_SYMBOLS = {"Engines._wait_enrichment", "Engines._cortrix_query"}
A0_SYMBOLS = {"resolve_vector_first"}
CURRENT_SYMBOLS = {"resolve_current_candidates"}
CURRENT_PG_SYMBOLS = {"pg_current_filter"}
SHARED_SYMBOLS = {
    "namespace_for", "schema_name", "content_hash", "validate_files",
    "extract_field", "_resolution", "resolve_candidates", "Engines.__init__",
    "Engines.restore_pending_tasks", "Engines._emit", "Engines._command",
    "Engines._http", "Engines._durable", "Engines._metrics",
    "Engines._metric_values", "Engines._embedding_receipt", "Engines._namespace",
    "Engines._upload", "Engines.ingest", "Engines.query", "Engines.snapshot",
    "Engines.cleanup",
}
SERVER_ASSIST_SYMBOLS = {"Controller.application_model_call", "Controller.pg_assist"}
SERVER_HARNESS_SYMBOLS = {"Controller.run_harness", "Controller.tool_projection"}

# Only these sources can be read. No runtime directory or glob is traversed.
SOURCE_SPECS = (
    ("engines.py", "engines.py", "application", ALL_PATHS, "engine_ast"),
    ("server.py", "server.py", "application", ALL_PATHS, "server_ast"),
    ("llm_assist.py", "llm_assist.py", "application", ASSIST_PATHS, "whole_file"),
    ("answer_normalization.py", "answer_normalization.py", "application", HARNESS_PATHS, "whole_file"),
    ("answer_contract.py", "answer_contract.py", "application", HARNESS_PATHS, "whole_file"),
    ("harness/tools.mjs", PACKAGE_ROOT / "harness/tools.mjs", "application", HARNESS_PATHS, "whole_file"),
    ("harness/driver.mjs", PACKAGE_ROOT / "harness/driver.mjs", "application", HARNESS_PATHS, "whole_file"),
    ("harness/phase.mjs", PACKAGE_ROOT / "harness/phase.mjs", "application", HARNESS_PATHS, "whole_file"),
    ("harness/transport.mjs", PACKAGE_ROOT / "harness/transport.mjs", "application", HARNESS_PATHS, "whole_file"),
    ("harness/runtime.mjs", PACKAGE_ROOT / "harness/runtime.mjs", "application", HARNESS_PATHS, "whole_file"),
    ("harness/launch.mjs", PACKAGE_ROOT / "harness/launch.mjs", "configuration", HARNESS_PATHS, "harness_overlay"),
    ("provision.py", "provision.py", "configuration", ("b",), "full_config_ast"),
    ("runtime-support/helpers/extract_vectors.py", PACKAGE_ROOT / "runtime-support/helpers/extract_vectors.py", "application", PG_PATHS, "whole_file"),
    ("runtime-support/config/cortrix.embedding-only.yaml", PACKAGE_ROOT / "runtime-support/config/cortrix.embedding-only.yaml", "configuration", PG_PATHS, "whole_file"),
    ("runtime-support/config/cortrix.full-stack.yaml", PACKAGE_ROOT / "runtime-support/config/cortrix.full-stack.yaml", "configuration", ("b",), "whole_file"),
    ("tests/test_engines.py", PACKAGE_ROOT / "tests/test_engines.py", "tests", ALL_PATHS, "whole_file"),
    ("tests/test_llm_assist.py", PACKAGE_ROOT / "tests/test_llm_assist.py", "tests", ASSIST_PATHS, "whole_file"),
    ("tests/test_answer_contract.py", PACKAGE_ROOT / "tests/test_answer_contract.py", "tests", HARNESS_PATHS, "whole_file"),
    ("tests/harness-tests.mjs", PACKAGE_ROOT / "tests/harness-tests.mjs", "tests", HARNESS_PATHS, "whole_file"),
    ("tests/harness-contract-tests.mjs", PACKAGE_ROOT / "tests/harness-contract-tests.mjs", "tests", HARNESS_PATHS, "whole_file"),
    ("tests/harness-fixtures-http.mjs", PACKAGE_ROOT / "tests/harness-fixtures-http.mjs", "tests", HARNESS_PATHS, "whole_file"),
)

EXCLUSIONS = (
    {"path": "event_projection.py", "reason": "Shared presentation of immutable component receipts; no retrieval, write, or business decision logic."},
    {"path": "state.py", "reason": "Generic workspace persistence, consent, and budget accounting; excluded from path application LOC."},
    {"path": "server.py", "reason": "Generic HTTP, authentication, persistence and scheduling are excluded; complete Harness adapter and application LLM assistance methods are assigned to their actual workflow consumers."},
    {"path": "operation_timing.py", "reason": "Generic execution measurement is excluded from path application LOC; complete timed engine functions still include their observation calls without prorating."},
    {"path": "provision.py", "reason": "Container provisioning and runtime binding excluded; only RuntimeManager.full_config is included as configuration source."},
    {"path": "harness/launch.mjs", "reason": "Launcher, runtime checks, and process lifecycle excluded; only overlay() is included as configuration source."},
    {"path": "tests/test_state.py; tests/test_controller_timing.py; tests/test_operation_timing.py", "reason": "Tests of excluded generic controller, state, and timing infrastructure."},
    {"path": "fixtures.py", "reason": "Default source documents and input construction are fixtures, not retrieval application code."},
    {"path": "code_inventory.py; tests/test_code_inventory.py", "reason": "Inventory implementation and its tests do not count toward the measured application."},
    {"path": "runtime/**; originals/**; artifacts/**; sessions/**; __pycache__/**", "reason": "Generated state, logs, model responses, and original documents are never scanned."},
    {"path": "node_modules/**; Core/PostgreSQL/Harness internals; model weights", "reason": "Dependency implementations and models are excluded. The mounted PG vector-export helper is explicitly included as reused application glue."},
)


def sha256(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def _owner(owners: tuple[str, ...] | list[str]) -> str:
    values = tuple(owners)
    if len(values) == 1:
        return values[0]
    if values == PG_PATHS:
        return "postgresql_family"
    if values == HARNESS_PATHS:
        return "harness_shared"
    return "shared"


def _span(node: ast.AST) -> tuple[int, int]:
    decorators = getattr(node, "decorator_list", [])
    start = min([node.lineno] + [decorator.lineno for decorator in decorators])
    return start, node.end_lineno


def _python_kinds(content: str, tree: ast.AST) -> list[str]:
    lines = content.splitlines()
    code: set[int] = set()
    comments: set[int] = set()
    docstrings: set[tuple[int, int]] = set()
    for node in ast.walk(tree):
        body = getattr(node, "body", None)
        if isinstance(node, (ast.Module, ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)) and body and isinstance(body[0], ast.Expr) and isinstance(body[0].value, ast.Constant) and isinstance(body[0].value.value, str):
            docstrings.add((body[0].value.lineno, body[0].value.end_lineno))
    ignored = {tokenize.ENCODING, tokenize.ENDMARKER, tokenize.INDENT, tokenize.DEDENT, tokenize.NEWLINE, tokenize.NL}
    for token in tokenize.generate_tokens(io.StringIO(content).readline):
        if token.type in ignored:
            continue
        target = comments if token.type == tokenize.COMMENT or (token.type == tokenize.STRING and (token.start[0], token.end[0]) in docstrings) else code
        target.update(range(token.start[0], token.end[0] + 1))
    return ["blank_lines" if not line.strip() else "code_lines" if number in code else "comment_lines" if number in comments else "code_lines" for number, line in enumerate(lines, 1)]


def _javascript_kinds(content: str) -> list[str]:
    """Classify physical lines without mistaking quoted URLs for comments."""
    lines = content.splitlines()
    code: set[int] = set()
    comments: set[int] = set()
    state = "normal"
    quote = ""
    escaped = False
    line = 1
    i = 0
    while i < len(content):
        char = content[i]
        following = content[i + 1:i + 2]
        if char == "\n":
            line += 1
            if state == "line_comment":
                state = "normal"
            escaped = False
            i += 1
            continue
        if state == "line_comment":
            comments.add(line)
        elif state == "block_comment":
            comments.add(line)
            if char == "*" and following == "/":
                state = "normal"
                i += 1
        elif state == "string":
            code.add(line)
            if escaped:
                escaped = False
            elif char == "\\":
                escaped = True
            elif char == quote:
                state = "normal"
        elif char in "'\"`":
            code.add(line)
            quote = char
            state = "string"
        elif char == "/" and following == "/":
            comments.add(line)
            state = "line_comment"
            i += 1
        elif char == "/" and following == "*":
            comments.add(line)
            state = "block_comment"
            i += 1
        elif not char.isspace():
            code.add(line)
        i += 1
    return ["blank_lines" if not text.strip() else "code_lines" if number in code else "comment_lines" if number in comments else "code_lines" for number, text in enumerate(lines, 1)]


def _counts(kinds: list[str], numbers: list[int] | range | None = None) -> dict[str, int]:
    selected = list(numbers if numbers is not None else range(1, len(kinds) + 1))
    result = {key: 0 for key in MEASURES}
    result["lines"] = len(selected)
    for number in selected:
        result[kinds[number - 1]] += 1
    return result


def _overlay_span(content: str) -> tuple[int, int]:
    # This fixed, whole function contains configuration strings, not JS control
    # flow to apportion. Fail visibly if its source boundary changes.
    lines = content.splitlines()
    starts = [i for i, line in enumerate(lines, 1) if line == "export function overlay() {"]
    if len(starts) != 1:
        raise ValueError("The frozen Harness overlay function boundary changed")
    start = starts[0]
    end = next((i for i in range(start + 1, len(lines) + 1) if lines[i - 1] == "}"), None)
    if end is None:
        raise ValueError("The Harness overlay function has no visible closing boundary")
    return start, end


def _assignments(content: str, tree: ast.AST | None, mode: str, category: str, owners: tuple[str, ...]) -> tuple[list[tuple[str, str, tuple[str, ...], bool]], list[str]]:
    default = ("module_and_class_boilerplate", category, owners, True)
    assignments = [default for _ in content.splitlines()]
    warnings = []

    def assign(symbol: str, start: int, end: int, assigned: tuple[str, ...], assigned_category: str = category) -> None:
        for number in range(start, end + 1):
            assignments[number - 1] = (symbol, assigned_category, assigned, True)

    if mode == "engine_ast":
        functions = [(node.name, node) for node in tree.body if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))]
        for cls in [node for node in tree.body if isinstance(node, ast.ClassDef)]:
            functions.extend((cls.name + "." + node.name, node) for node in cls.body if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)))
        for name, node in functions:
            if name in PG_SYMBOLS:
                assigned = PG_PATHS
            elif name in FULL_SYMBOLS:
                assigned = ("b",)
            elif name in A0_SYMBOLS:
                assigned = ("a0",)
            elif name in CURRENT_SYMBOLS:
                assigned = CURRENT_PATHS
            elif name in CURRENT_PG_SYMBOLS:
                assigned = ASSIST_PATHS
            else:
                assigned = ALL_PATHS
            known = PG_SYMBOLS | FULL_SYMBOLS | A0_SYMBOLS | CURRENT_SYMBOLS | CURRENT_PG_SYMBOLS | SHARED_SYMBOLS
            if name not in known:
                warnings.append(f"Unmapped callable {name} is conservatively charged to all paths; review ownership before comparing totals.")
            assign(name, *_span(node), assigned)
    elif mode == "harness_overlay":
        assignments = [("excluded_launcher", "excluded", (), False) for _ in assignments]
        assign("overlay", *_overlay_span(content), owners)
    elif mode == "full_config_ast":
        assignments = [("excluded_provisioning", "excluded", (), False) for _ in assignments]
        matches = [method for cls in tree.body if isinstance(cls, ast.ClassDef) and cls.name == "RuntimeManager" for method in cls.body if isinstance(method, ast.FunctionDef) and method.name == "full_config"]
        if len(matches) != 1:
            raise ValueError("RuntimeManager.full_config source boundary changed")
        assign("RuntimeManager.full_config", *_span(matches[0]), owners)
    elif mode == "server_ast":
        assignments = [("excluded_controller", "excluded", (), False) for _ in assignments]
        methods = {"Controller." + method.name: method for cls in tree.body if isinstance(cls, ast.ClassDef) and cls.name == "Controller" for method in cls.body if isinstance(method, ast.FunctionDef)}
        expected = SERVER_ASSIST_SYMBOLS | SERVER_HARNESS_SYMBOLS
        if not expected <= set(methods):
            raise ValueError("Server application adapter boundaries changed")
        for name in expected:
            assigned = ASSIST_PATHS if name in SERVER_ASSIST_SYMBOLS else HARNESS_PATHS
            assign(name, *_span(methods[name]), assigned)
    elif mode == "whole_file":
        assignments = [("complete_file", category, owners, True) for _ in assignments]
    else:
        raise ValueError("Unknown source inventory mode")
    return assignments, warnings


SQL_START = re.compile(r"^\s*(SELECT|INSERT\s+INTO|UPDATE|DELETE\s+FROM|CREATE|DROP|TRUNCATE|BEGIN\s*;|SET\s|WHERE\s)", re.I)


def _string_text(node: ast.AST) -> str | None:
    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        return node.value
    if isinstance(node, ast.JoinedStr):
        return "".join(part.value if isinstance(part, ast.Constant) and isinstance(part.value, str) else "{expression}" for part in node.values)
    return None


def _sql_fragments(tree: ast.AST, *, line_offset: int = 0) -> list[dict[str, Any]]:
    fragments = []

    def visit(node: ast.AST) -> None:
        text = _string_text(node)
        if text is not None and SQL_START.match(text):
            fragments.append({"start_line": node.lineno + line_offset, "end_line": node.end_lineno + line_offset, "text": text, "text_lines": len(text.splitlines()), "sha256": sha256(text.encode()), "parameter_placeholders": "{expression}", "executable_sql": False})
            return
        if isinstance(node, ast.Assign) and any(isinstance(target, ast.Name) and target.id == "DURABLE_SCRIPT" for target in node.targets):
            value = _string_text(node.value)
            if value is not None:
                fragments.extend(_sql_fragments(ast.parse(value), line_offset=node.value.lineno - 1 + line_offset))
            return
        # F-string children are fragments of a single source literal, not extra
        # independent SQL statements to count again.
        if isinstance(node, ast.JoinedStr):
            return
        for child in ast.iter_child_nodes(node):
            visit(child)

    visit(tree)
    return fragments


def _regions(path: str, content: str, kinds: list[str], assignments: list[tuple[str, str, tuple[str, ...], bool]]) -> list[dict[str, Any]]:
    lines = content.splitlines(keepends=True)
    result = []
    start = 1
    for end in range(1, len(assignments) + 1):
        if end < len(assignments) and assignments[end] == assignments[start - 1]:
            continue
        symbol, category, owners, included = assignments[start - 1]
        result.append({"symbol": symbol, "start_line": start, "end_line": end, "source_ref": f"{path}:{start}", "category": category, "owners": list(owners), "path_owner": _owner(owners) if owners else "excluded", "included": included, "sha256": sha256("".join(lines[start - 1:end]).encode()), **_counts(kinds, range(start, end + 1))})
        start = end + 1
    return result


RESPONSIBILITY_META = {
    "necessary_shared_engine": ("Required shared engine", "Input validation, ingestion, query orchestration, runtime adapters, and complete in-function observations used by every path.", "shared_foundation"),
    "shared_business_resolution": ("Shared business resolution", "Field extraction and candidate resolution contracts used by every path.", "business_rule"),
    "postgresql_foundation": ("PostgreSQL foundation", "Vector export, PostgreSQL writes, ranking, and cleanup adapters shared by A0, A1, and Harness PG.", "retrieval_foundation"),
    "a0_vector_first_policy": ("A0 first-result policy", "A0 selects the first item in native vector order without applying current-version filtering.", "business_rule"),
    "current_version_resolution": ("Current-version resolution", "A1, Harness PG, and B apply the current-version rule to candidates returned by their respective backends.", "business_rule"),
    "current_version_pg_filter": ("PostgreSQL current-version filter", "A1 and Harness PG apply the current-version predicate in their native PostgreSQL query.", "business_rule"),
    "application_llm_assist": ("Application LLM assistance", "Bounded query expansion, lexical retrieval, fusion, reranking, request, and receipt adapters for A1 and Harness PG.", "application_assist"),
    "cortrix_full_stack_adapter": ("Cortrix B adapter", "Enhanced-readiness checks, Cortrix retrieval, evidence mapping, and result handling for path B.", "cortrix_adapter"),
    "harness_shared_adapter": ("Shared Harness adapter", "Tools, session handling, answer contracts, and driver integration used only by Harness PG and B.", "harness_adapter"),
}


def _responsibility_id(path: str, symbol: str, owners: list[str]) -> str:
    if path == "llm_assist.py" or symbol in SERVER_ASSIST_SYMBOLS:
        return "application_llm_assist"
    if symbol in SERVER_HARNESS_SYMBOLS or owners == list(HARNESS_PATHS):
        return "harness_shared_adapter"
    if path == "engines.py":
        if symbol in A0_SYMBOLS:
            return "a0_vector_first_policy"
        if symbol in CURRENT_SYMBOLS:
            return "current_version_resolution"
        if symbol in CURRENT_PG_SYMBOLS:
            return "current_version_pg_filter"
        if symbol in {"extract_field", "_resolution", "resolve_candidates"}:
            return "shared_business_resolution"
        if symbol in PG_SYMBOLS:
            return "postgresql_foundation"
        if symbol in FULL_SYMBOLS:
            return "cortrix_full_stack_adapter"
        return "necessary_shared_engine"
    if path == "reused/extract_vectors.py":
        return "postgresql_foundation"
    if owners == list(PG_PATHS):
        return "postgresql_foundation"
    if owners == ["b"]:
        return "cortrix_full_stack_adapter"
    if owners == list(ALL_PATHS):
        return "necessary_shared_engine"
    raise ValueError(f"Application source range has no responsibility: {path}:{symbol}")


def _responsibilities(files: list[dict[str, Any]], expected_code_lines: int) -> list[dict[str, Any]]:
    grouped: dict[str, dict[str, Any]] = {}
    covered: set[tuple[str, int]] = set()
    for file in files:
        for region in file["source_ranges"]:
            if not region["included"] or region["category"] != "application":
                continue
            responsibility_id = _responsibility_id(file["path"], region["symbol"], region["owners"])
            label, description, category = RESPONSIBILITY_META[responsibility_id]
            consumers = region["consumers"]
            item = grouped.setdefault(responsibility_id, {"id": responsibility_id, "label": label, "description": description, "category": category, "owners": region["owners"], "consumers": consumers, "code_lines": 0, "source_ranges": []})
            if item["owners"] != region["owners"] or item["consumers"] != consumers:
                raise ValueError(f"Responsibility mixes incompatible consumers: {responsibility_id}")
            for number in range(region["start_line"], region["end_line"] + 1):
                identity = (file["path"], number)
                if identity in covered:
                    raise ValueError("Responsibility source ranges overlap")
                covered.add(identity)
            item["code_lines"] += region["code_lines"]
            item["source_ranges"].append({"path": file["path"], "file": file["path"], "symbol": region["symbol"], "start_line": region["start_line"], "end_line": region["end_line"], "source_ref": region["source_ref"], "code_lines": region["code_lines"], "sha256": region["sha256"]})
    result = [grouped[key] for key in RESPONSIBILITY_META if key in grouped]
    if sum(item["code_lines"] for item in result) != expected_code_lines:
        raise ValueError("Responsibility code lines do not match the complete application inventory")
    return result


def inventory(root: Path | str = ROOT, config=None) -> dict[str, Any]:
    """Inspect the fixed source set without importing engines or touching data."""
    root = Path(root)
    packaged_helpers = PACKAGE_ROOT / "runtime-support/helpers"
    packaged_configs = PACKAGE_ROOT / "runtime-support/config"
    configured_sources = {
        "runtime-support/helpers/extract_vectors.py": (config.helpers_root if config else packaged_helpers) / "extract_vectors.py",
        "runtime-support/config/cortrix.embedding-only.yaml": (config.configs_root if config else packaged_configs) / "cortrix.embedding-only.yaml",
        "runtime-support/config/cortrix.full-stack.yaml": (config.configs_root if config else packaged_configs) / "cortrix.full-stack.yaml",
    }
    files = []
    warnings = []
    category_counts = {category: {key: 0 for key in MEASURES} for category in ("application", "configuration", "tests")}
    by_path = {path: {category: {"exclusive": 0, "shared": 0, "total": 0} for category in category_counts} for path in ALL_PATHS}
    mode_paths = {"deterministic": ("a0", "a1", "b"), "harness": ("pg", "b")}
    by_mode = {mode: {path: {category: {"exclusive": 0, "shared": 0, "total": 0} for category in category_counts} for path in paths} for mode, paths in mode_paths.items()}
    sql_lines: set[tuple[str, int]] = set()
    sql_by_path = {path: set() for path in ALL_PATHS}
    pg_family = {"exclusive": 0, "shared_with_cortrix": 0, "total": 0}
    for label, source, category, owners, mode in SOURCE_SPECS:
        source = configured_sources.get(label, source)
        source_path = source if isinstance(source, Path) else root / source
        if source_path.is_symlink():
            raise ValueError("Inventory source files must not be symlinks")
        raw = source_path.read_bytes()
        content = raw.decode("utf-8")
        suffix = source_path.suffix
        tree = ast.parse(content, filename=label) if suffix == ".py" else None
        if tree is not None:
            kinds, parser = _python_kinds(content, tree), "python_ast_and_tokenize"
        elif suffix == ".mjs":
            kinds, parser = _javascript_kinds(content), "javascript_lexical_whole_file"
        else:
            kinds = ["blank_lines" if not line.strip() else "comment_lines" if line.lstrip().startswith("#") else "code_lines" for line in content.splitlines()]
            parser = "yaml_physical_lines"
        assignments, source_warnings = _assignments(content, tree, mode, category, owners)
        warnings.extend(f"{label}: {warning}" for warning in source_warnings)
        regions = _regions(label, content, kinds, assignments)
        for region in regions:
            if mode == "server_ast" and region["symbol"] in SERVER_HARNESS_SYMBOLS:
                consumer_modes = ("harness",)
            elif mode != "server_ast" and region["owners"] == list(HARNESS_PATHS):
                consumer_modes = ("harness",)
            else:
                consumer_modes = ("deterministic", "harness")
            region["consumers"] = [{"mode": consumer_mode, "path": path} for consumer_mode in consumer_modes for path in region["owners"] if path in mode_paths[consumer_mode]]
        fragments = _sql_fragments(tree) if tree is not None else []
        for fragment in fragments:
            fragment["source_ref"] = f"{label}:{fragment['start_line']}"
            fragment["non_additive"] = True
            selected = set()
            for number in range(fragment["start_line"], fragment["end_line"] + 1):
                if not 1 <= number <= len(assignments):
                    raise ValueError("Embedded SQL source pointer escaped the containing file")
                _, assigned_category, assigned_owners, included = assignments[number - 1]
                if included and assigned_category == "application":
                    sql_lines.add((label, number))
                    selected.update(assigned_owners)
                    for path in assigned_owners:
                        sql_by_path[path].add((label, number))
            fragment["owners"] = [path for path in ALL_PATHS if path in selected]
        counted = {key: 0 for key in MEASURES}
        for region in regions:
            if not region["included"]:
                continue
            assigned_category = region["category"]
            for measure in MEASURES:
                counted[measure] += region[measure]
                category_counts[assigned_category][measure] += region[measure]
            for path in region["owners"]:
                target = by_path[path][assigned_category]
                target["exclusive" if region["owners"] == [path] else "shared"] += region["code_lines"]
                target["total"] += region["code_lines"]
            for consumer in region["consumers"]:
                target = by_mode[consumer["mode"]][consumer["path"]][assigned_category]
                mode_owners = [path for path in region["owners"] if path in mode_paths[consumer["mode"]]]
                target["exclusive" if mode_owners == [consumer["path"]] else "shared"] += region["code_lines"]
                target["total"] += region["code_lines"]
            if assigned_category == "application" and set(region["owners"]) & set(PG_PATHS):
                pg_family["exclusive" if set(region["owners"]) <= set(PG_PATHS) else "shared_with_cortrix"] += region["code_lines"]
                pg_family["total"] += region["code_lines"]
        all_owners = [path for path in ALL_PATHS if any(path in region["owners"] for region in regions if region["included"])]
        modes = [consumer_mode for consumer_mode in mode_paths if any(consumer["mode"] == consumer_mode for region in regions for consumer in region["consumers"])]
        file_owners = {region["path_owner"] for region in regions if region["included"]}
        files.append({"path": label, "content": content, **_counts(kinds), "category": category, "path_owner": next(iter(file_owners)) if len(file_owners) == 1 else "mixed", "owners": all_owners, "modes": list(modes), "sha256": sha256(raw), "parser": parser, "counted": counted, "source_ranges": regions, "sql_fragments": fragments, "provenance": "package_source"})
    for path in ALL_PATHS:
        by_path[path]["sql"] = {"source_lines": len(sql_by_path[path]), "non_additive": True}
    identity = "\n".join(f"{item['path']} {item['sha256']}" for item in files)
    responsibilities = _responsibilities(files, category_counts["application"]["code_lines"])
    return {
        "schema_version": 2, "files": files, "responsibilities": responsibilities,
        "counts": {**category_counts, "by_path": by_path, "by_mode": by_mode, "postgresql_family_application": pg_family, "sql": {"source_lines": len(sql_lines), "non_additive": True}, "total_application_code_lines": category_counts["application"]["code_lines"]},
        "source_manifest_sha256": sha256(identity.encode()), "inventory_implementation_sha256": sha256(Path(__file__).read_bytes()), "excluded": list(EXCLUSIONS), "warnings": warnings,
        "capabilities_equivalent": False, "savings_percentage": None,
        "methodology": {
            "unit": "physical source lines; per-path exclusive/shared/total values count code_lines",
            "partition": "lines = blank_lines + comment_lines + code_lines; inline comments remain code lines; Python docstrings count as comments",
            "ownership": "Python AST function/method spans and fixed whole JavaScript adapter files; module/class boilerplate is shared",
            "shared_accounting": "Each path includes the full code of each routine it consumes. Shared code counts once in each path total, and once in the unique category total. Per-path totals must not be summed into a unique repo total.",
            "mode_accounting": "by_path is the union of implemented consumers. Use by_mode for a comparison within the deterministic or Harness workflow; deterministic B excludes Harness adapter files. Exclusive/shared are relative to the paths participating in that view.",
            "postgresql_family": "PG-only SQL, writes, queries, and vector-export glue belong to a0/a1/pg. They are exclusive to the PostgreSQL family but shared between its individual paths.",
            "conditional_branches": "Whole shared entry-point functions are counted for their consumers; conditional branches are not prorated or presented as tiny call-site LOC.",
            "responsibilities": "Responsibility cards aggregate disjoint included application ranges only when owners and mode/path consumers are identical. Their code_lines sum to the complete unique application count; per-path cards sum to that path's complete application total.",
            "observation": "Generic operation_timing.py is excluded. Timed engine and application functions are counted as complete callable spans, including their real observation adapter calls; no branch lines are silently removed.",
            "javascript": "No JavaScript AST is claimed. Complete adapter files use lexical comment classification; the fixed overlay configuration function uses explicit source boundaries.",
            "sql": "SQL string text and source pointers are displayed separately. Their physical source lines already belong to application code and must not be added again. F-string expressions appear as non-executable placeholders.",
            "configuration": "Static reused Cortrix YAML templates plus the local full_config factory and Harness overlay are counted separately from application code. Provisioning and launcher control flow remain excluded.",
            "comparison_boundary": "These implementations have different capabilities and dependencies. Counts do not establish an advantage, a savings percentage, or equivalent production capability.",
            "read_boundary": "Only the fixed SOURCE_SPECS paths are read. No engine is imported, no command is executed, and no runtime, original document, credential, or dependency tree is scanned.",
        },
    }


if __name__ == "__main__":
    import json
    print(json.dumps(inventory(), ensure_ascii=False, indent=2))
