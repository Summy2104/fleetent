"""Minimal MCP-compatible HTTP server for local testing.

Exposes two tools:
  - echo: returns the input string as-is
  - add: adds two numbers

Start with: uv run python scripts/mock_mcp_server.py
"""

import json
from http.server import BaseHTTPRequestHandler, HTTPServer

TOOLS = [
    {
        "name": "echo",
        "description": "Echo the input text back.",
        "inputSchema": {
            "type": "object",
            "properties": {"text": {"type": "string"}},
            "required": ["text"],
        },
    },
    {
        "name": "add",
        "description": "Add two numbers and return the result.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "a": {"type": "number"},
                "b": {"type": "number"},
            },
            "required": ["a", "b"],
        },
    },
]


def _handle(body: dict) -> dict:
    method = body.get("method")
    rid = body.get("id", 1)

    if method == "tools/list":
        return {"jsonrpc": "2.0", "id": rid, "result": {"tools": TOOLS}}

    if method == "tools/call":
        params = body.get("params", {})
        name = params.get("name")
        args = params.get("arguments", {})

        if name == "echo":
            result = args.get("text", "")
        elif name == "add":
            result = str(args.get("a", 0) + args.get("b", 0))
        else:
            return {"jsonrpc": "2.0", "id": rid, "error": {"code": -32601, "message": f"unknown tool: {name}"}}

        return {"jsonrpc": "2.0", "id": rid, "result": {"content": [{"type": "text", "text": result}]}}

    return {"jsonrpc": "2.0", "id": rid, "error": {"code": -32601, "message": f"unknown method: {method}"}}


class Handler(BaseHTTPRequestHandler):
    def do_POST(self):
        length = int(self.headers.get("Content-Length", 0))
        body = json.loads(self.rfile.read(length))
        response = _handle(body)
        data = json.dumps(response).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def log_message(self, fmt, *args):
        print(f"[mock-mcp] {fmt % args}")


if __name__ == "__main__":
    server = HTTPServer(("0.0.0.0", 8001), Handler)
    print("Mock MCP server running on http://localhost:8001")
    server.serve_forever()
