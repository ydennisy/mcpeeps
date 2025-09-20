#!/usr/bin/env python3
"""Serve the local game UI and optionally expose it through ngrok."""

from __future__ import annotations

import argparse
import contextlib
import shlex
import shutil
import signal
import subprocess
import sys
import threading
import time
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Iterable

SERVER_SHUTDOWN_POLL_SECONDS = 0.2


class IframeFriendlyHandler(SimpleHTTPRequestHandler):
    """HTTP handler that adds headers suitable for iframe embedding."""

    def __init__(self, *args, directory: str | None = None, **kwargs) -> None:
        super().__init__(*args, directory=directory, **kwargs)

    def end_headers(self) -> None:  # type: ignore[override]
        # Cache headers keep things fresh during development.
        self.send_header("Cache-Control", "no-store, must-revalidate")
        self.send_header("Pragma", "no-cache")
        # Allow the page to be embedded by other origins.
        self.send_header("X-Frame-Options", "ALLOWALL")
        # Make MIME type sniffing less likely to break the iframe.
        self.send_header("X-Content-Type-Options", "nosniff")
        super().end_headers()


def parse_arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Run the local game server and (optionally) tunnel it with ngrok.",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    default_dir = Path(__file__).resolve().parent
    parser.add_argument(
        "--directory",
        type=Path,
        default=default_dir,
        help="Directory to serve. Defaults to the game-server folder.",
    )
    parser.add_argument(
        "--host",
        default="0.0.0.0",
        help="Host interface to bind the HTTP server to.",
    )
    parser.add_argument(
        "--port",
        type=int,
        default=8000,
        help="Local port used for the HTTP server.",
    )
    parser.add_argument(
        "--no-ngrok",
        action="store_true",
        help="Skip launching ngrok and only serve locally.",
    )
    parser.add_argument(
        "--ngrok-template",
        default="ngrok http {port}",
        help=(
            "Command template used to start ngrok. The string is formatted with the local port "
            "(e.g. 'ngrok http 127.0.0.1:{port}')."
        ),
    )
    parser.add_argument(
        "--ngrok-extra",
        nargs="*",
        default=(),
        help="Additional arguments appended to the ngrok command after template expansion.",
    )
    parser.add_argument(
        "--open-browser",
        action="store_true",
        help="Open the served page in the default browser after startup.",
    )
    return parser.parse_args()


def ensure_directory(directory: Path) -> Path:
    directory = directory.expanduser().resolve()
    if not directory.exists():
        raise FileNotFoundError(f"Directory '{directory}' does not exist.")
    if not directory.is_dir():
        raise NotADirectoryError(f"'{directory}' is not a directory.")
    return directory


def start_http_server(host: str, port: int, directory: Path) -> ThreadingHTTPServer:
    handler = partial(IframeFriendlyHandler, directory=str(directory))
    try:
        httpd = ThreadingHTTPServer((host, port), handler)
    except OSError as exc:  # pragma: no cover - networking edge case
        print(f"[server] Failed to bind {host}:{port} -> {exc}", file=sys.stderr)
        raise SystemExit(2) from exc

    thread = threading.Thread(target=httpd.serve_forever, name="http-server", daemon=True)
    thread.start()
    return httpd


def resolve_executable(command: str) -> str | None:
    path = Path(command)
    if path.exists():
        return str(path.resolve())
    return shutil.which(command)


def build_ngrok_command(template: str, port: int, extra_args: Iterable[str]) -> list[str]:
    try:
        rendered = template.format(port=port)
    except KeyError as exc:  # pragma: no cover - runtime misconfiguration
        print(f"[ngrok] Could not format template: missing key {exc}", file=sys.stderr)
        raise SystemExit(2) from exc

    parts = shlex.split(rendered)
    if not parts:
        print("[ngrok] The command template produced an empty command.", file=sys.stderr)
        raise SystemExit(2)

    executable = resolve_executable(parts[0])
    if executable is None:
        print(
            f"[ngrok] Could not find executable '{parts[0]}'. Set --ngrok-template to the correct binary.",
            file=sys.stderr,
        )
        raise SystemExit(2)

    parts[0] = executable
    return [*parts, *extra_args]


def stream_subprocess_output(prefix: str, process: subprocess.Popen[str]) -> None:
    assert process.stdout is not None
    for line in process.stdout:
        print(f"[{prefix}] {line.rstrip()}")


def launch_ngrok(command: list[str]) -> subprocess.Popen[str] | None:
    try:
        process = subprocess.Popen(
            command,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            bufsize=1,
        )
    except FileNotFoundError:  # pragma: no cover - handled earlier
        return None

    thread = threading.Thread(target=stream_subprocess_output, args=("ngrok", process), daemon=True)
    thread.start()
    return process


def wait_for_interrupt(httpd: ThreadingHTTPServer, ngrok_process: subprocess.Popen[str] | None) -> None:
    try:
        while True:
            time.sleep(SERVER_SHUTDOWN_POLL_SECONDS)
            if ngrok_process and ngrok_process.poll() is not None:
                print("[ngrok] Tunnel process exited. Press Ctrl+C to stop the server.")
                ngrok_process = None
    except KeyboardInterrupt:
        print("\n[server] Caught interrupt, shutting down…")
    finally:
        httpd.shutdown()
        if ngrok_process and ngrok_process.poll() is None:
            with contextlib.suppress(ProcessLookupError):
                ngrok_process.send_signal(signal.SIGINT)
            try:
                ngrok_process.wait(timeout=2)
            except subprocess.TimeoutExpired:
                ngrok_process.kill()



def maybe_open_browser(host: str, port: int) -> None:
    try:
        import webbrowser
    except Exception as exc:  # pragma: no cover - extremely unlikely
        print(f"[server] Could not open browser automatically: {exc}")
        return

    url = f"http://{host}:{port}/"
    opened = webbrowser.open(url, new=2)
    if opened:
        print(f"[server] Opened {url} in your browser.")
    else:
        print(f"[server] Please open {url} manually.")



def main() -> None:
    args = parse_arguments()
    directory = ensure_directory(args.directory)

    httpd = start_http_server(args.host, args.port, directory)
    print(f"[server] Serving {directory} at http://{args.host}:{args.port}/")

    ngrok_process: subprocess.Popen[str] | None = None
    if not args.no_ngrok:
        command = build_ngrok_command(args.ngrok_template, args.port, args.ngrok_extra)
        print(f"[ngrok] Launching: {' '.join(shlex.quote(part) for part in command)}")
        ngrok_process = launch_ngrok(command)
        if ngrok_process is None:
            print("[ngrok] Failed to start the ngrok process.", file=sys.stderr)

    if args.open_browser:
        maybe_open_browser(args.host if args.host != "0.0.0.0" else "127.0.0.1", args.port)

    wait_for_interrupt(httpd, ngrok_process)


if __name__ == "__main__":
    main()
