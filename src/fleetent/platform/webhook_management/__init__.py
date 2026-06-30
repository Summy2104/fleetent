"""Platform-side managed webhook source management (live-webhooks).

Owns the management-DB ``webhook_sources`` table and the public inbound ``POST /webhook/{id}``
edge for managed deployments. Forwards accepted webhooks to the target agent through the
existing platform→node→agent transport. Agent runtime MUST NOT import this package.
"""
