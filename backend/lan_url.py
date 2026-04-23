"""Resolve a **non-loopback** base URL for QR codes and "open on phone" links.

When the operator opens the app via ``127.0.0.1``, we still want phones on the same LAN
to use ``http://<this-hosts-LAN-IP>:port``. Use the request Host when the client already
reached the server on a real interface IP; otherwise guess the primary IPv4 via UDP.
"""
from __future__ import annotations

import socket
from typing import Any

from starlette.requests import Request


def _guess_lan_ipv4() -> str | None:
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        try:
            s.settimeout(0.25)
            s.connect(("8.8.8.8", 80))
            ip = s.getsockname()[0]
        finally:
            s.close()
    except OSError:
        return None
    if not ip or ip.startswith("127."):
        return None
    return ip


def public_http_base(request: Request, port: int) -> str:
    """
    Public ``http://host:port`` (no trailing slash) for other devices on the network to use.

    * If the request arrived on a non-loopback hostname, reuse that (same as browser URL).
    * Else guess LAN IPv4; else fall back to 127.0.0.1.
    """
    h = (request.url.hostname or "").lower().strip("[]")
    loop = {"127.0.0.1", "localhost", "::1"}
    if h and h not in loop and h not in ("testserver",):
        return str(request.base_url).rstrip("/")
    g = _guess_lan_ipv4()
    if g:
        return f"http://{g}:{port}"
    return f"http://127.0.0.1:{port}"


def public_http_base_info(request: Request, port: int) -> dict[str, Any]:
    h = (request.url.hostname or "").lower().strip("[]")
    loop = ("127.0.0.1", "localhost", "::1")
    guess = _guess_lan_ipv4()
    base = public_http_base(request, port)
    if h and h not in loop and h not in ("testserver", "testclient"):
        via = "host_header"
    elif guess and base == f"http://{guess}:{port}":
        via = "lan_guess"
    else:
        via = "loopback"
    return {
        "public_http_base": base,
        "public_http_base_source": via,
        "scorekeeper_url": f"{base}/scorekeeper",
    }
