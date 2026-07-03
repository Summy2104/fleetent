"""Platform serve command — thin wrapper around uvicorn."""

from __future__ import annotations

import argparse

_DEFAULT_HOST = "127.0.0.1"
_DEFAULT_PORT = 8765


def _uvicorn_run(
    app: str, *, host: str, port: int, reload: bool = False, log_level: str = "info"
) -> None:
    import uvicorn

    uvicorn.run(app, host=host, port=port, reload=reload, log_level=log_level)


def register(subparsers: argparse._SubParsersAction[argparse.ArgumentParser]) -> None:
    """Register the serve subcommand."""
    parser = subparsers.add_parser("serve", help="Start the Platform control-plane HTTP server")
    parser.add_argument("--host", default=_DEFAULT_HOST, help="Bind host")
    parser.add_argument("--port", type=int, default=_DEFAULT_PORT, help="Bind port")
    parser.add_argument("--reload", action="store_true", help="Enable auto-reload for development")


def handle(args: argparse.Namespace) -> bool:
    """Handle the serve subcommand."""
    if args.cmd != "serve":
        return False
    from fleetent.build_info import log_service_startup

    log_service_startup("platform")
    _uvicorn_run(
        "fleetent.server:app",
        host=args.host,
        port=args.port,
        reload=args.reload,
        log_level="info",
    )
    return True
