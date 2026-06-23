from __future__ import annotations

import os
import secrets
import time
from dataclasses import dataclass

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from fastapi import FastAPI, Form, HTTPException, Query, Request
from fastapi.responses import RedirectResponse
from joserfc import jwt
from joserfc.jwk import RSAKey

app = FastAPI(title="fleetent-e2e-oidc-stub")


@dataclass(frozen=True)
class _IssuedCode:
    nonce: str
    state: str


_PRIVATE_KEY = rsa.generate_private_key(public_exponent=65537, key_size=2048)
_PRIVATE_PEM = _PRIVATE_KEY.private_bytes(
    serialization.Encoding.PEM,
    serialization.PrivateFormat.PKCS8,
    serialization.NoEncryption(),
)
_PUBLIC_PEM = _PRIVATE_KEY.public_key().public_bytes(
    serialization.Encoding.PEM,
    serialization.PublicFormat.SubjectPublicKeyInfo,
)
_PUBLIC_JWK = RSAKey.import_key(_PUBLIC_PEM, parameters={"kid": "e2e-oidc-stub"}).as_dict()
_ISSUED_CODES: dict[str, _IssuedCode] = {}


def _issuer(request: Request) -> str:
    configured = os.environ.get("OIDC_STUB_ISSUER", "").strip()
    if configured:
        return configured.rstrip("/")
    return str(request.base_url).rstrip("/")


def _client_id() -> str:
    return os.environ.get("OIDC_STUB_CLIENT_ID", "fleetent-web")


def _client_secret() -> str:
    return os.environ.get("OIDC_STUB_CLIENT_SECRET", "oidc-secret")


def _subject() -> str:
    return os.environ.get("OIDC_STUB_SUBJECT", "oidc-user")


def _email() -> str:
    return os.environ.get("OIDC_STUB_EMAIL", "stub.person@example.com")


@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/.well-known/openid-configuration")
async def discovery(request: Request) -> dict[str, str]:
    issuer = _issuer(request)
    return {
        "issuer": issuer,
        "authorization_endpoint": f"{issuer}/oauth/authorize",
        "token_endpoint": f"{issuer}/oauth/token",
        "jwks_uri": f"{issuer}/oauth/jwks",
    }


@app.get("/oauth/authorize")
async def authorize(
    client_id: str = Query(...),
    redirect_uri: str = Query(...),
    response_type: str = Query(...),
    state: str = Query(...),
    nonce: str = Query(...),
) -> RedirectResponse:
    if client_id != _client_id():
        raise HTTPException(status_code=400, detail="bad client_id")
    if response_type != "code":
        raise HTTPException(status_code=400, detail="bad response_type")
    code = f"code-{secrets.token_hex(6)}"
    _ISSUED_CODES[code] = _IssuedCode(nonce=nonce, state=state)
    return RedirectResponse(f"{redirect_uri}?code={code}&state={state}", status_code=302)


@app.post("/oauth/token")
async def token(
    request: Request,
    grant_type: str = Form(...),
    code: str = Form(...),
    client_id: str = Form(...),
    client_secret: str = Form(""),
) -> dict[str, str]:
    if grant_type != "authorization_code":
        raise HTTPException(status_code=400, detail="bad grant_type")
    if client_id != _client_id():
        raise HTTPException(status_code=400, detail="bad client_id")
    if client_secret != _client_secret():
        raise HTTPException(status_code=401, detail="bad client_secret")
    issued = _ISSUED_CODES.get(code)
    if issued is None:
        raise HTTPException(status_code=400, detail="bad code")

    now = int(time.time())
    id_token = jwt.encode(
        {"alg": "RS256", "kid": "e2e-oidc-stub"},
        {
            "iss": _issuer(request),
            "sub": _subject(),
            "aud": _client_id(),
            "iat": now - 5,
            "exp": now + 300,
            "nonce": issued.nonce,
            "email": _email(),
            "email_verified": True,
        },
        RSAKey.import_key(_PRIVATE_PEM, parameters={"kid": "e2e-oidc-stub"}),
    )
    return {"access_token": "at-e2e-oidc-stub", "token_type": "Bearer", "id_token": id_token}


@app.get("/oauth/jwks")
async def jwks() -> dict[str, list[dict[str, object]]]:
    return {"keys": [_PUBLIC_JWK]}
