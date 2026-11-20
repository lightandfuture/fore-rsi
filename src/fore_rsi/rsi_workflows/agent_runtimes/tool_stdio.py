# SPDX-License-Identifier: Apache-2.0
# SPDX-FileCopyrightText: Copyright contributors to the ForeRSI project

"""Connect a native MCP stdio client to its member's current stateless, JSON-response HTTP endpoint."""

import json
import sys
from http.client import HTTPConnection, HTTPException
from pathlib import Path
from time import monotonic, sleep
from urllib.parse import urlsplit


def forward_mcp_message(address_file: Path, message: bytes, version: str | None) -> bytes:
    """Forward one JSON-RPC message to the local workflow host without retaining its capability."""
    address = urlsplit(address_file.read_text(encoding="utf-8").strip())
    if address.scheme != "http" or address.hostname != "127.0.0.1" or address.port is None:
        raise ValueError("ForeRSI tools require a local workflow address.")
    connection = HTTPConnection("127.0.0.1", address.port)
    headers = {"Content-Type": "application/json", "Accept": "application/json, text/event-stream"}
    if version:
        headers["MCP-Protocol-Version"] = version
    try:
        connection.request("POST", address.path, message, headers)
        response = connection.getresponse()
        if response.status not in (200, 202, 204):
            raise HTTPException(f"Workflow tools returned HTTP {response.status}.")
        return response.read()
    finally:
        connection.close()


def relay_mcp_messages(address_file: Path) -> None:
    """Relay JSON-RPC messages until the native client closes stdin."""
    protocol_version = None
    for line in sys.stdin.buffer:
        message = json.loads(line)
        is_initialize = message.get("method") == "initialize"
        retry_deadline = monotonic() + 8 if is_initialize else None
        reply: dict[str, object] | None = None
        while retry_deadline is None or monotonic() < retry_deadline:
            try:
                raw = forward_mcp_message(address_file, line, protocol_version)
                reply = json.loads(raw) if raw else None
                if is_initialize and reply and "result" in reply:
                    protocol_version = reply["result"]["protocolVersion"]
                break
            except (OSError, HTTPException, ValueError) as error:
                retryable = isinstance(error, (FileNotFoundError, ConnectionError, HTTPException))
                if is_initialize and retryable:
                    sleep(0.1)
                    continue
                reply = {
                    "jsonrpc": "2.0",
                    "id": message.get("id"),
                    "error": {"code": -32603, "message": "The ForeRSI workflow tool service is unavailable."},
                }
                break
        if reply is None:
            reply = {
                "jsonrpc": "2.0",
                "id": message.get("id"),
                "error": {"code": -32603, "message": "The ForeRSI workflow tool service is unavailable."},
            }
        if "id" in message:
            print(json.dumps(reply), flush=True)


if __name__ == "__main__":
    relay_mcp_messages(Path(sys.argv[1]))
