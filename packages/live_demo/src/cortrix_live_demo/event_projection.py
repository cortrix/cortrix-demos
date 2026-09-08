"""Project actual component receipts without inventing progress or counts."""


def details(stage, value):
    response = value.get("response") if isinstance(value.get("response"), dict) else {}
    if stage.endswith("_failed") or response.get("error_code") or response.get("error_msg"):
        state = "failed"
    elif stage.endswith("_progress"):
        state = "completed" if str(response.get("status", "")).lower() in {"completed", "ready", "success", "succeeded"} else "processing"
    elif stage.endswith(("_started", "_submitting")):
        state = "started"
    else:
        state = value.get("state", "completed")
    result = {"state": state, "event_recorder": "demo_controller", "evidence_source": value.get("source", "unspecified")}
    for key in ("schema_version", "timing_scope", "step_id", "operation", "owner", "attempt_id", "parent_attempt_id", "process_instance_id", "request_id", "session_id", "task", "component", "stage_total_includes_setup"):
        if value.get(key) is not None:
            result[key] = value[key]
    if value.get("source") == "business_step" and value.get("step_id") in {"vectors_export", "query_vector_read"} and value.get("owner") == "cortrix":
        result.update(recorded_owner="cortrix", owner="application", owner_projection="package_vector_export_helper_v1")
    if value.get("source") in {"controller", "business_step", "runtime_control"}:
        for key in ("started_monotonic_ns", "ended_monotonic_ns"):
            if type(value.get(key)) is int and value[key] >= 0:
                # Nanoseconds are identifiers here; strings avoid JavaScript precision loss.
                result[key] = str(value[key])
    for key in ("document_id", "namespace", "task_id", "document_count"):
        if value.get(key) is not None:
            result[key] = value[key]
    observed = value.get("after") or value.get("durable") or {}
    if isinstance(observed, dict):
        if isinstance(observed.get("documents"), list):
            result["document_count"] = len([d for d in observed["documents"] if not d.get("deleted_at")])
        if isinstance(observed.get("text_blocks"), list):
            result["chunk_count"] = len(observed["text_blocks"])
        if isinstance(observed.get("row_count"), int):
            result["row_count"] = observed["row_count"]
    return result
