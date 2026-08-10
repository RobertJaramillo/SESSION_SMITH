"""Shared ASGI test client for exercising backend.app directly, without httpx."""

from __future__ import annotations

import json
from typing import Any

import backend.app as campaign_api


async def request(method: str, path: str, body: dict[str, Any] | None = None, query: str = "") -> tuple[int, dict[str, Any]]:
    scope: dict[str, Any] = {
        "type": "http",
        "asgi": {"version": "3.0"},
        "http_version": "1.1",
        "method": method,
        "scheme": "http",
        "path": path,
        "raw_path": path.encode(),
        "query_string": query.encode(),
        "headers": [(b"host", b"test")],
        "client": ("test", 1),
        "server": ("test", 80),
    }
    raw_body = json.dumps(body).encode() if body is not None else b""
    if body is not None:
        scope["headers"].append((b"content-type", b"application/json"))

    messages: list[dict[str, Any]] = []
    received = False

    async def receive() -> dict[str, Any]:
        nonlocal received
        if received:
            return {"type": "http.disconnect"}
        received = True
        return {"type": "http.request", "body": raw_body, "more_body": False}

    async def send(message: dict[str, Any]) -> None:
        messages.append(message)

    await campaign_api.app(scope, receive, send)
    response_status = next(message["status"] for message in messages if message["type"] == "http.response.start")
    response_body = b"".join(message.get("body", b"") for message in messages if message["type"] == "http.response.body")
    return response_status, json.loads(response_body)


async def request_raw(method: str, path: str, query: str = "") -> tuple[int, dict[str, str], bytes]:
    """Like request(), but returns (status, headers, raw_body) without JSON
    parsing — for non-JSON responses (e.g. the world-export markdown/PDF)."""
    scope: dict[str, Any] = {
        "type": "http",
        "asgi": {"version": "3.0"},
        "http_version": "1.1",
        "method": method,
        "scheme": "http",
        "path": path,
        "raw_path": path.encode(),
        "query_string": query.encode(),
        "headers": [(b"host", b"test")],
        "client": ("test", 1),
        "server": ("test", 80),
    }
    messages: list[dict[str, Any]] = []
    received = False

    async def receive() -> dict[str, Any]:
        nonlocal received
        if received:
            return {"type": "http.disconnect"}
        received = True
        return {"type": "http.request", "body": b"", "more_body": False}

    async def send(message: dict[str, Any]) -> None:
        messages.append(message)

    await campaign_api.app(scope, receive, send)
    start = next(message for message in messages if message["type"] == "http.response.start")
    headers = {key.decode(): value.decode() for key, value in start["headers"]}
    body = b"".join(message.get("body", b"") for message in messages if message["type"] == "http.response.body")
    return start["status"], headers, body
