"""Interactive terminal TUI client + WebSocket gateway for fleetent.

The TUI is another *client* of the agent service (alongside the IM gateway and
SSE /chat), not embedded in the agent process. Backend: a bidirectional
newline-delimited JSON-RPC 2.0 protocol over a WebSocket ``/ws`` endpoint;
frontend: a pure-Python prompt_toolkit + rich terminal client.
"""
