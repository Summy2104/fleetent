"""Provider connectivity testing implementation.

Actually tests provider endpoints with minimal requests to verify connectivity,
authentication, and model availability without recording usage or costs.
"""

import asyncio
import time
from typing import Any

import httpx
from openai import APIError, AsyncOpenAI, AuthenticationError, NotFoundError
from openai.types.chat import ChatCompletionMessageParam


async def test_provider_connectivity(provider: dict[str, Any]) -> dict[str, Any]:
    """Test provider connectivity with a minimal request.

    Returns:
        dict with keys:
        - reachable: bool
        - latency_ms: int or None
        - model: str
        - error: str or None
    """
    if not provider.get("base_url") or not provider.get("model"):
        return {
            "reachable": False,
            "latency_ms": None,
            "model": provider.get("model"),
            "error": "Missing base_url or model configuration",
        }

    # Use a very small test prompt to minimize tokens/cost
    test_messages: list[ChatCompletionMessageParam] = [{"role": "user", "content": "Hi"}]

    try:
        # Create client with provider config
        client = AsyncOpenAI(
            base_url=provider["base_url"],
            api_key=provider.get("api_key") or "dummy-key-for-test",
            timeout=10.0,  # 10 second timeout for connectivity test
        )

        start_time = time.monotonic()

        # Try to make a completion with minimal tokens
        await client.chat.completions.create(
            model=provider["model"],
            messages=test_messages,
            max_tokens=1,  # Minimal tokens to reduce cost
            temperature=0.0,
        )

        latency_ms = int((time.monotonic() - start_time) * 1000)

        # If we get here, the provider is reachable and model exists
        return {
            "reachable": True,
            "latency_ms": latency_ms,
            "model": provider["model"],
            "error": None,
        }

    except AuthenticationError as e:
        # Auth error means provider is reachable but key is invalid
        return {
            "reachable": True,
            "latency_ms": None,
            "model": provider["model"],
            "error": f"Authentication failed: {str(e)}",
        }

    except NotFoundError as e:
        # Model not found
        return {
            "reachable": True,
            "latency_ms": None,
            "model": provider["model"],
            "error": f"Model not found: {str(e)}",
        }

    except APIError as e:
        # API error (rate limit, server error, etc)
        return {
            "reachable": False,
            "latency_ms": None,
            "model": provider["model"],
            "error": f"API error: {str(e)}",
        }

    except httpx.ConnectError as e:
        # Connection failed
        return {
            "reachable": False,
            "latency_ms": None,
            "model": provider["model"],
            "error": f"Connection failed: {str(e)}",
        }

    except httpx.TimeoutException:
        # Request timed out
        return {
            "reachable": False,
            "latency_ms": None,
            "model": provider["model"],
            "error": "Request timed out (10s)",
        }

    except Exception as e:
        # Unexpected error
        return {
            "reachable": False,
            "latency_ms": None,
            "model": provider["model"],
            "error": f"Unexpected error: {type(e).__name__}: {str(e)}",
        }


def test_provider_connectivity_sync(provider: dict[str, Any]) -> dict[str, Any]:
    """Synchronous wrapper for test_provider_connectivity."""
    try:
        asyncio.get_running_loop()
    except RuntimeError:
        # No running loop, create one
        return asyncio.run(test_provider_connectivity(provider))
    else:
        # Running in async context, need to handle differently
        # This is called from sync FastAPI endpoint, so we create a new loop
        import concurrent.futures

        with concurrent.futures.ThreadPoolExecutor() as executor:
            future = executor.submit(asyncio.run, test_provider_connectivity(provider))
            return future.result(timeout=15)
