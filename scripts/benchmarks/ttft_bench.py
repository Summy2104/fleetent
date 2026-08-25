"""Framework TTFT / throughput benchmark for the fleetent agent loop.

Measures the runtime's *own* streaming overhead — time-to-first-token (TTFT) and
per-turn latency — with the LLM client replaced by a near-zero-latency streaming
stub. Because model inference is stubbed out, the numbers isolate what the
framework itself contributes: route selection, context build, prompt assembly,
message hygiene, streaming plumbing. A separate `--model-delay` knob simulates
model first-byte latency so end-to-end shape can be inspected too.

Run:
    uv run python scripts/benchmarks/ttft_bench.py --iters 200 --concurrency 1 8 32

Everything runs against an isolated temp FLEETENT_HOME so it never touches
`data/`. Only the LLM client is stubbed; the rest of the loop runs for real.
"""

from __future__ import annotations

import argparse
import asyncio
import os
import statistics
import tempfile
import time
from dataclasses import dataclass, field
from pathlib import Path
from unittest.mock import MagicMock

# Home must be chosen BEFORE importing fleetent (path constants resolve at import).
# BENCH_E2E=1 drives the real demo agent against the configured relay (real API
# calls); otherwise an isolated temp home + stubbed LLM measures framework overhead.
_E2E = os.environ.get("BENCH_E2E") == "1"
if _E2E:
    _HOME = os.environ.get("FLEETENT_HOME") or str(Path(".fleetent-dev").resolve())
    os.environ["FLEETENT_HOME"] = _HOME
    _TMP_HOME = _HOME
else:
    _TMP_HOME = tempfile.mkdtemp(prefix="fleetent-bench-")
    os.environ["FLEETENT_HOME"] = _TMP_HOME
os.environ.setdefault("LOG_FORMAT", "console")


@dataclass
class Sample:
    ttft_ms: float
    total_ms: float


@dataclass
class Stats:
    label: str
    ttft: list[float] = field(default_factory=list)
    total: list[float] = field(default_factory=list)

    def add(self, s: Sample) -> None:
        self.ttft.append(s.ttft_ms)
        self.total.append(s.total_ms)


def _pct(values: list[float], p: float) -> float:
    if not values:
        return float("nan")
    ordered = sorted(values)
    k = (len(ordered) - 1) * p
    lo = int(k)
    hi = min(lo + 1, len(ordered) - 1)
    return ordered[lo] + (ordered[hi] - ordered[lo]) * (k - lo)


def _make_text_stream(text: str, model_delay: float):
    """Return a fresh async-generator factory yielding one text chunk.

    ``model_delay`` seconds simulate the model's first-byte latency; 0 isolates
    pure framework overhead.
    """

    async def _gen():
        if model_delay > 0:
            await asyncio.sleep(model_delay)
        c = MagicMock()
        c.usage = None
        c.choices = [MagicMock()]
        c.choices[0].delta.content = text
        c.choices[0].delta.tool_calls = None
        c.choices[0].delta.reasoning_content = None
        c.choices[0].finish_reason = "stop"
        yield c

    return _gen()


def _install_stub(loop_mod, model_delay: float) -> None:
    """Replace only the LLM client build point with a zero/low-latency stub."""

    def _build(resolved, api_key):  # noqa: ANN001
        client = MagicMock()

        async def _create(*_a, **_kw):  # the SDK's create() is awaited, returns a stream
            return _make_text_stream("ok", model_delay)

        client.chat.completions.create = _create
        return client

    loop_mod._build_async_client = _build  # type: ignore[attr-defined]


async def _one_run(loop_mod, prompt: str, agent_name: str | None = None) -> Sample:
    start = time.perf_counter()
    ttft: float | None = None
    async for event in loop_mod.run_stream(prompt, agent_name=agent_name):
        if ttft is None and event.get("type") == "text_delta":
            ttft = (time.perf_counter() - start) * 1000.0
    total = (time.perf_counter() - start) * 1000.0
    return Sample(ttft_ms=ttft if ttft is not None else total, total_ms=total)


async def _bench_serial(loop_mod, iters: int, warmup: int) -> Stats:
    st = Stats(label="serial")
    for i in range(iters + warmup):
        s = await _one_run(loop_mod, f"benchmark ping {i}")
        if i >= warmup:
            st.add(s)
    return st


async def _bench_concurrent(loop_mod, concurrency: int, iters: int) -> Stats:
    st = Stats(label=f"concurrency={concurrency}")
    for _ in range(iters):
        tasks = [_one_run(loop_mod, f"c ping {j}") for j in range(concurrency)]
        for s in await asyncio.gather(*tasks):
            st.add(s)
    return st


def _report(st: Stats) -> None:
    n = len(st.ttft)
    print(f"\n[{st.label}]  samples={n}")
    for name, vals in (("TTFT", st.ttft), ("TOTAL", st.total)):
        if not vals:
            continue
        print(
            f"  {name:5}  "
            f"mean={statistics.mean(vals):7.2f}ms  "
            f"p50={_pct(vals, 0.50):7.2f}ms  "
            f"p90={_pct(vals, 0.90):7.2f}ms  "
            f"p99={_pct(vals, 0.99):7.2f}ms  "
            f"max={max(vals):7.2f}ms"
        )


async def _main_async(args: argparse.Namespace) -> None:
    from fleetent.structured_logging import configure_structured_logging

    # Silence per-run info/warn noise so the report is readable; benchmark only.
    configure_structured_logging(console_level="error")

    import fleetent.runtime.loop as loop_mod

    print(f"FLEETENT_HOME={_TMP_HOME}")

    if _E2E:
        agent = os.environ.get("BENCH_AGENT", "demo")
        iters = args.iters if args.iters <= 30 else 20  # cap real paid calls

        # Load the named agent's own model policy — otherwise run_stream falls back to
        # the default active-agent policy (localhost:11434), which is not the relay.
        from fleetent import agent_config
        from fleetent.model.resolver import ModelPolicySnapshot

        agent_dir = Path(_HOME) / "tenants" / "default" / "agents" / agent
        agent_file = agent_config.load_agent_file(agent_dir)
        policy = ModelPolicySnapshot.from_agent(agent_file)
        target0 = next(iter(policy.targets.values()))
        print(f"MODE=e2e  agent={agent}  iters={iters} (real relay calls)")
        print(f"  base_url={target0.base_url}  model={target0.model}")

        async def _one_e2e(prompt: str) -> Sample:
            start = time.perf_counter()
            ttft: float | None = None
            async for event in loop_mod.run_stream(prompt, agent_name=agent, model_policy=policy):
                if ttft is None and event.get("type") == "text_delta":
                    ttft = (time.perf_counter() - start) * 1000.0
            total = (time.perf_counter() - start) * 1000.0
            return Sample(ttft_ms=ttft if ttft is not None else total, total_ms=total)

        st = Stats(label=f"e2e agent={agent}")
        errors: list[str] = []
        for i in range(iters + args.warmup):
            try:
                s = await _one_e2e(f"用一句话打个招呼 #{i}")
            except Exception as exc:  # noqa: BLE001 — surface, don't abort the whole run
                errors.append(f"{type(exc).__name__}: {exc}")
                continue
            if i >= args.warmup:
                st.add(s)
        if st.ttft:
            _report(st)
        if errors:
            print(f"\n{len(errors)} run(s) errored. First few:")
            for e in errors[:3]:
                print(f"  - {e}")
        return

    _install_stub(loop_mod, args.model_delay)

    # Post-reply memory extraction is best-effort background work that runs AFTER
    # the reply (never on the TTFT path). Unwired here (no facts_db), so no-op it to
    # keep the measurement to the core loop + streaming plumbing. Excluded from TOTAL.
    async def _noop_pipeline(*_a, **_kw):  # noqa: ANN002, ANN003
        return None

    loop_mod.run_pipeline_from_conversation = _noop_pipeline  # type: ignore[attr-defined]

    print(
        f"MODE=framework  model_delay={args.model_delay * 1000:.0f}ms  "
        f"iters={args.iters}  warmup={args.warmup}"
    )

    serial = await _bench_serial(loop_mod, args.iters, args.warmup)
    _report(serial)

    for c in args.concurrency:
        if c <= 1:
            continue
        per_iter = max(1, args.iters // c)
        st = await _bench_concurrent(loop_mod, c, per_iter)
        _report(st)


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--iters", type=int, default=200, help="measured iterations")
    ap.add_argument("--warmup", type=int, default=20, help="warmup iterations (discarded)")
    ap.add_argument(
        "--model-delay",
        type=float,
        default=0.0,
        help="simulated model first-byte latency in seconds (0 = pure framework)",
    )
    ap.add_argument(
        "--concurrency",
        type=int,
        nargs="+",
        default=[1, 8, 32],
        help="concurrency levels to test",
    )
    args = ap.parse_args()
    asyncio.run(_main_async(args))


if __name__ == "__main__":
    main()
