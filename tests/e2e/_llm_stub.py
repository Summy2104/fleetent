from __future__ import annotations

import asyncio
import json
import threading
from collections.abc import AsyncIterator
from typing import Any

from fastapi import FastAPI
from fastapi.responses import JSONResponse, StreamingResponse
from pydantic import BaseModel, Field

app = FastAPI(title="fleetent-e2e-llm-stub")

_request_log: list[dict[str, Any]] = []
_log_lock = threading.Lock()


class ChatMessage(BaseModel):
    role: str
    content: str | None = None


class ChatRequest(BaseModel):
    model: str
    messages: list[ChatMessage] = Field(default_factory=list)
    stream: bool = False


def _reply_text(messages: list[ChatMessage]) -> str:
    user_parts = [message.content or "" for message in messages if message.role == "user"]
    prompt = " ".join(part.strip() for part in user_parts if part.strip()) or "empty prompt"
    return f"stub: {prompt}"


def _sse_chunk(payload: dict[str, Any]) -> bytes:
    return f"data: {json.dumps(payload, ensure_ascii=True)}\n\n".encode()


async def _stream_reply(reply: str, model: str) -> AsyncIterator[bytes]:
    chunk_id = "chatcmpl-stub"
    yield _sse_chunk(
        {
            "id": chunk_id,
            "object": "chat.completion.chunk",
            "model": model,
            "choices": [{"index": 0, "delta": {"role": "assistant"}, "finish_reason": None}],
        }
    )
    yield _sse_chunk(
        {
            "id": chunk_id,
            "object": "chat.completion.chunk",
            "model": model,
            "choices": [{"index": 0, "delta": {"content": reply}, "finish_reason": None}],
        }
    )
    await asyncio.sleep(0.01)
    yield _sse_chunk(
        {
            "id": chunk_id,
            "object": "chat.completion.chunk",
            "model": model,
            "choices": [{"index": 0, "delta": {}, "finish_reason": "stop"}],
        }
    )
    yield b"data: [DONE]\n\n"


@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/v1/requests")
async def get_requests() -> list[dict[str, Any]]:
    with _log_lock:
        return list(_request_log)


@app.delete("/v1/requests", status_code=204)
async def clear_requests() -> None:
    with _log_lock:
        _request_log.clear()


@app.post("/v1/chat/completions")
async def chat_completions(body: ChatRequest):
    with _log_lock:
        _request_log.append(body.model_dump())
    reply = _reply_text(body.messages)
    if body.stream:
        return StreamingResponse(_stream_reply(reply, body.model), media_type="text/event-stream")
    return JSONResponse(
        {
            "id": "chatcmpl-stub",
            "object": "chat.completion",
            "model": body.model,
            "choices": [
                {
                    "index": 0,
                    "message": {"role": "assistant", "content": reply},
                    "finish_reason": "stop",
                }
            ],
        }
    )
