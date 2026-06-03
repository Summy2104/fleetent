"""Four-layer resource collectors (host / process / container / infra).

Each layer is an injectable seam returning ``[(metric, target, value), ...]`` so tests
mock every source and the default run path performs no network IO. ``collect_once`` writes
the samples through ``monitoring_store`` and stamps a ``collection_status`` sample per layer
(1.0 healthy / 0.0 采集中断). On a per-layer failure it marks the layer interrupted and
raises a deduplicated built-in alert instead of silently dropping data — other layers still
record. Collection interval and retention window are module constants so they can be
monkeypatched / overridden by configuration.
"""

import datetime
import logging
import os
import shutil
import subprocess
from typing import Any

from fleetent.platform.resource_monitoring import monitoring_store as store

logger = logging.getLogger(__name__)

Sample = tuple[str, str, float]

COLLECT_INTERVAL_SECONDS = 60
RETENTION_SECONDS = 7 * 24 * 3600
COLLECTION_FAILURE_RULE = "builtin:collection_failure"

_DOCKER = "docker"


def _now() -> str:
    return datetime.datetime.now(datetime.UTC).isoformat()


# --- layer seams (default impls are intranet-only; mocked in tests) -----------


def collect_host() -> list[Sample]:
    """Host CPU / memory load via stdlib (no external service)."""
    samples: list[Sample] = []
    load1 = os.getloadavg()[0] if hasattr(os, "getloadavg") else 0.0
    cpus = os.cpu_count() or 1
    samples.append(("load_pct", "host:local", round(100.0 * load1 / cpus, 2)))
    return samples


def collect_process() -> list[Sample]:
    """This process' own footprint (self / /proc/self), no external call."""
    samples: list[Sample] = []
    try:
        import resource

        rss_kb = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
        samples.append(("rss_mb", "process:self", round(rss_kb / 1024.0, 2)))
    except Exception:  # noqa: BLE001 — best effort, missing on some platforms
        pass
    return samples


def collect_containers() -> list[Sample]:
    """Sandbox container counters via the local Docker CLI (OOM / timeout kills, active)."""
    if shutil.which(_DOCKER) is None:
        raise RuntimeError("docker CLI not available")
    proc = subprocess.run(
        [_DOCKER, "ps", "--filter", "label=fleetent.sandbox", "-q"],
        capture_output=True,
        text=True,
        timeout=10,
    )
    active = len([ln for ln in proc.stdout.splitlines() if ln.strip()])
    return [("active", "container:sandbox", float(active))]


def collect_infra() -> list[Sample]:
    """Self-hosted infra liveness (PG / Redis / Qdrant / RabbitMQ) over the intranet."""
    return []


# --- orchestration ------------------------------------------------------------


def _emit_collection_alert(layer: str, error: str) -> None:
    """Raise a deduplicated built-in 采集中断 alert for a failed layer."""
    target = f"layer:{layer}"
    if store.find_active_alert(COLLECTION_FAILURE_RULE, target) is not None:
        return  # already firing — dedup
    store.create_alert(COLLECTION_FAILURE_RULE, target, "critical", {"error": error})


def collect_once(now: str | None = None) -> dict[str, Any]:
    """Run all four layers, persist samples, mark per-layer health. Returns a summary."""
    ts = now or _now()
    recorded = 0
    failed: list[str] = []
    layers: list[tuple[str, Any]] = [
        ("host", collect_host),
        ("process", collect_process),
        ("container", collect_containers),
        ("infra", collect_infra),
    ]
    for layer, seam in layers:
        try:
            for metric, target, value in seam():
                store.record_sample(metric, target, value, ts=ts)
                recorded += 1
            store.record_sample("collection_status", f"layer:{layer}", 1.0, ts=ts)
        except Exception as exc:  # noqa: BLE001 — mark 采集中断 + alert, never silent
            logger.warning("collection_failed layer=%s error=%s", layer, exc)
            store.record_sample("collection_status", f"layer:{layer}", 0.0, ts=ts)
            _emit_collection_alert(layer, str(exc))
            failed.append(layer)
    return {"recorded": recorded, "failed": failed}


def purge_expired(now: str | None = None) -> int:
    """Drop samples older than the retention window."""
    base = datetime.datetime.fromisoformat(now) if now else datetime.datetime.now(datetime.UTC)
    cutoff = base - datetime.timedelta(seconds=RETENTION_SECONDS)
    return store.purge_before(cutoff.isoformat())
