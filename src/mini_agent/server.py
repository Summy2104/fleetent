"""FastAPI HTTP server: POST /chat (SSE), GET /health."""

import json
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

from fastapi import Depends, FastAPI, Header, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from mini_agent.agent_loop import run_stream
from mini_agent.skill_registry import scan as scan_skills
from mini_agent.user_store import get_by_api_key


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    scan_skills()
    yield


app = FastAPI(title="mini-agent", lifespan=lifespan)


class ChatRequest(BaseModel):
    message: str


async def _require_auth(authorization: str = Header()) -> str:
    """Extract user_id from Bearer token. Raises 401 if invalid."""
    if not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Bearer token required")
    api_key = authorization.removeprefix("Bearer ").strip()
    user = get_by_api_key(api_key)
    if user is None:
        raise HTTPException(status_code=401, detail="Invalid API key")
    return user.id


@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}


@app.post("/chat")
async def chat(
    req: ChatRequest, user_id: str = Depends(_require_auth)
) -> StreamingResponse:
    async def _stream() -> AsyncGenerator[str, None]:
        try:
            async for event in run_stream(req.message, user_id=user_id):
                yield f"data: {json.dumps(event, ensure_ascii=False)}\n\n"
        except Exception as exc:
            error = {"type": "error", "content": str(exc)}
            yield f"data: {json.dumps(error, ensure_ascii=False)}\n\n"

    return StreamingResponse(_stream(), media_type="text/event-stream")
