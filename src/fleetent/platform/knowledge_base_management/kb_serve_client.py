from __future__ import annotations

from typing import Any, cast

import httpx

from fleetent.config import KBServeSettings
from fleetent.identity import INGRESS_PRINCIPAL_HEADER, Principal, encode_ingress_principal
from fleetent.platform.knowledge_base_management.auth import resolve_service_key_ref

_PLATFORM_KB_USER_ID = "platform"


class KBServeClient:
    def __init__(
        self,
        settings: KBServeSettings,
        *,
        transport: httpx.BaseTransport | None = None,
    ) -> None:
        self._settings = settings
        self._transport = transport

    def list_knowledge_bases(self, tenant_id: str) -> list[dict[str, Any]]:
        return cast(list[dict[str, Any]], self._request("GET", "/kb", tenant_id=tenant_id).json())

    def create_knowledge_base(
        self, tenant_id: str, kb_id: str, description: str, extraction_enabled: bool = False
    ) -> dict[str, Any]:
        return cast(
            dict[str, Any],
            self._request(
                "POST",
                "/kb",
                tenant_id=tenant_id,
                json={
                    "kb_id": kb_id,
                    "description": description,
                    "extraction_enabled": extraction_enabled,
                },
            ).json(),
        )

    def update_knowledge_base(
        self,
        tenant_id: str,
        kb_id: str,
        *,
        description: str | None = None,
        extraction_enabled: bool | None = None,
    ) -> dict[str, Any]:
        payload = {
            key: value
            for key, value in {
                "description": description,
                "extraction_enabled": extraction_enabled,
            }.items()
            if value is not None
        }
        return cast(
            dict[str, Any],
            self._request("PATCH", f"/kb/{kb_id}", tenant_id=tenant_id, json=payload).json(),
        )

    def archive_knowledge_base(self, tenant_id: str, kb_id: str) -> dict[str, Any]:
        return cast(
            dict[str, Any], self._request("DELETE", f"/kb/{kb_id}", tenant_id=tenant_id).json()
        )

    def list_documents(self, tenant_id: str, kb_id: str) -> list[dict[str, Any]]:
        return cast(
            list[dict[str, Any]],
            self._request("GET", f"/kb/{kb_id}/documents", tenant_id=tenant_id).json(),
        )

    def preview_document_chunks(
        self, tenant_id: str, kb_id: str, document_id: str
    ) -> list[dict[str, Any]]:
        return cast(
            list[dict[str, Any]],
            self._request(
                "GET",
                f"/kb/{kb_id}/documents/{document_id}/chunks",
                tenant_id=tenant_id,
            ).json(),
        )

    def delete_document(self, tenant_id: str, kb_id: str, document_id: str) -> dict[str, Any]:
        return cast(
            dict[str, Any],
            self._request(
                "DELETE",
                f"/kb/{kb_id}/documents/{document_id}",
                tenant_id=tenant_id,
            ).json(),
        )

    def upload_document(
        self,
        tenant_id: str,
        kb_id: str,
        *,
        filename: str,
        content: bytes,
        content_type: str,
    ) -> dict[str, Any]:
        return cast(
            dict[str, Any],
            self._request(
                "POST",
                f"/kb/{kb_id}/documents",
                tenant_id=tenant_id,
                files={"file": (filename, content, content_type)},
            ).json(),
        )

    def run_evaluation(self, tenant_id: str, kb_id: str) -> dict[str, Any]:
        return cast(
            dict[str, Any],
            self._request(
                "POST", "/evaluations", tenant_id=tenant_id, json={"kb_id": kb_id}
            ).json(),
        )

    def search(
        self,
        *,
        tenant_id: str,
        query: str,
        kb_ids: list[str],
        limit: int,
        mode: str,
        rerank: bool,
        use_planner: bool,
    ) -> dict[str, Any]:
        principal = self._principal(tenant_id)
        return cast(
            dict[str, Any],
            self._request(
                "POST",
                "/search",
                tenant_id=tenant_id,
                json={
                    "principal": {"user_id": principal.user_id, "tenant_id": principal.tenant_id},
                    "query": query,
                    "kb_ids": kb_ids,
                    "limit": limit,
                    "mode": mode,
                    "rerank": rerank,
                    "use_planner": use_planner,
                },
            ).json(),
        )

    def _request(
        self,
        method: str,
        path: str,
        *,
        tenant_id: str,
        json: dict[str, Any] | None = None,
        files: dict[str, tuple[str, bytes, str]] | None = None,
    ) -> httpx.Response:
        with httpx.Client(
            base_url=self._settings.url.rstrip("/"),
            headers=self._headers(tenant_id),
            timeout=self._settings.timeout_seconds,
            transport=self._transport,
        ) as client:
            response = client.request(method, path, json=json, files=files)
        response.raise_for_status()
        return response

    def _headers(self, tenant_id: str) -> dict[str, str]:
        return {
            "Authorization": f"Bearer {resolve_service_key_ref(self._settings.service_key_ref)}",
            INGRESS_PRINCIPAL_HEADER: encode_ingress_principal(self._principal(tenant_id)),
        }

    def _principal(self, tenant_id: str) -> Principal:
        return Principal(user_id=_PLATFORM_KB_USER_ID, tenant_id=tenant_id)
