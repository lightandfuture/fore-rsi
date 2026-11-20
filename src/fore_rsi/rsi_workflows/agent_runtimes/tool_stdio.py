# SPDX-License-Identifier: Apache-2.0
# SPDX-FileCopyrightText: Copyright contributors to the ForeRSI project

"""Connect a native MCP stdio client to its member's current stateless, JSON-response HTTP endpoint."""

from http.client import HTTPConnection, HTTPException
import json
from pathlib import Path
import sys
from time import monotonic, sleep
from urllib.parse import urlsplit


def forward(address_file: Path, message: bytes, version: str | None) -> bytes:
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


def serve(address_file: Path) -> None:
    """Relay until the native client closes stdin. Only the initial handshake may be retried."""
    version = None
    for line in sys.stdin.buffer:
        message = json.loads(line)
        initialize = message.get("method") == "initialize"
        deadline = monotonic() + 8 if initialize else 0
        while True:
            try:
                raw = forward(address_file, line, version)
                reply = json.loads(raw) if raw else None
                if initialize and reply and "result" in reply:
                    version = reply["result"]["protocolVersion"]
                break
            except (OSError, HTTPException, ValueError) as error:
                # A restored PTY can start before its workflow republishes the address.
                if isinstance(error, (FileNotFoundError, ConnectionError, HTTPException)) and monotonic() < deadline:
                    sleep(0.1)
                    continue
                reply = {"jsonrpc": "2.0", "id": message.get("id"),
                         "error": {"code": -32603, "message": "The ForeRSI workflow tool service is unavailable."}}
                break
        if "id" in message and reply is not None:
            print(json.dumps(reply), flush=True)


if __name__ == "__main__":
    serve(Path(sys.argv[1]))
