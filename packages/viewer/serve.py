from __future__ import annotations

import argparse
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
import json
import sys


LOOPBACK = "127.0.0.1"


def create_server(preferred_bind: str, port: int) -> tuple[ThreadingHTTPServer, str, bool]:
    try:
        return ThreadingHTTPServer((preferred_bind, port), SimpleHTTPRequestHandler), preferred_bind, False
    except OSError:
        if preferred_bind == LOOPBACK:
            raise
        return ThreadingHTTPServer((LOOPBACK, port), SimpleHTTPRequestHandler), LOOPBACK, True


def main() -> int:
    parser = argparse.ArgumentParser(description="Serve the accepted Cortrix demo viewer from the repository root.")
    parser.add_argument("--bind", default=LOOPBACK)
    parser.add_argument("--port", type=int, default=18765)
    args = parser.parse_args()
    try:
        server, actual_bind, used_fallback = create_server(args.bind, args.port)
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
    print(json.dumps({"status": "serving", "bind": actual_bind, "port": args.port, "fallback_used": used_fallback}), flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
