from pathlib import Path

from cortrix_live_demo.config import RuntimeConfig


def make_config(root: Path, *, external_calls=True):
    root = Path(root).resolve()
    return RuntimeConfig(
        bind_host="127.0.0.1", port=4186, operator_origin="http://127.0.0.1:4186",
        internal_bind_host="dedicated-gateway", internal_port=4187,
        core_callback_base_url="http://dedicated-gateway:4187",
        runtime_root=root / "runtime", helpers_root=root / "helpers", configs_root=root / "config",
        model_volume="cortrix-live-demo-models", cortrix_image="cortrix-live-demo-core:rc2",
        core_source_root=root / "source", container_prefix="cortrix-live-demo",
        network_subnet="dedicated-network", network_gateway="dedicated-gateway",
        embedding_port=18426, full_port=18427, pg_port=15436,
        harness_root=root / "harness", fixtures_root=root / "fixtures",
        allow_external_calls=external_calls, budget_total_usd=1.0,
        budget_deterministic_usd=0.3, budget_harness_usd=0.7,
        provider_input_cache_hit_usd_per_million=0.01,
        provider_input_cache_miss_usd_per_million=0.1,
        provider_output_usd_per_million=0.2,
    )
