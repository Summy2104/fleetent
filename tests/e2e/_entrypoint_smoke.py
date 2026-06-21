from __future__ import annotations

import contextlib
import os
import socket
import subprocess
import sys
import time
from collections.abc import Iterator
from pathlib import Path

import httpx


def repo_root() -> Path:
    return Path(__file__).resolve().parents[2]


def child_env(*, extra: dict[str, str]) -> dict[str, str]:
    env = os.environ.copy()
    src = str(repo_root() / "src")
    env["PYTHONPATH"] = f"{src}{os.pathsep}{env['PYTHONPATH']}" if env.get("PYTHONPATH") else src
    env.update(extra)
    return env


def reserve_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        sock.listen(1)
        return int(sock.getsockname()[1])


def wait_for_http_ready(proc: subprocess.Popen[str], url: str, *, timeout: float = 15.0) -> None:
    deadline = time.monotonic() + timeout
    last_error: str | None = None
    while time.monotonic() < deadline:
        if proc.poll() is not None:
            out, err = proc.communicate(timeout=1.0)
            raise AssertionError(
                f"process exited before {url} was ready: code={proc.returncode}\nstdout:\n{out}\n"
                f"stderr:\n{err}"
            )
        try:
            response = httpx.get(url, timeout=0.5)
            if response.status_code == 200:
                return
            last_error = f"unexpected status {response.status_code}"
        except httpx.HTTPError as exc:
            last_error = str(exc)
        time.sleep(0.2)
    raise AssertionError(f"timed out waiting for {url}: {last_error or 'no response'}")


@contextlib.contextmanager
def running_process(
    argv: list[str],
    *,
    env: dict[str, str],
    cwd: Path | None = None,
) -> Iterator[subprocess.Popen[str]]:
    proc = subprocess.Popen(
        argv,
        cwd=str(cwd) if cwd is not None else None,
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    try:
        yield proc
    finally:
        if proc.poll() is None:
            proc.terminate()
            try:
                proc.wait(timeout=5.0)
            except subprocess.TimeoutExpired:
                proc.kill()
                proc.wait(timeout=5.0)
        if proc.stdout is not None:
            proc.stdout.close()
        if proc.stderr is not None:
            proc.stderr.close()
