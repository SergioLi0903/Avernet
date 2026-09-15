"""HTTP-backed sender for resource-only upload-completed events."""
from __future__ import annotations

import asyncio

from agentclaw.community.plugin_api.http_client import HttpClient

_UPLOAD_COMPLETED_PATH = (
    "/api/v1/knowledge/integrations/tc/files/upload-completed"
)


class HttpUploadCompletedSender:
    def __init__(
        self,
        *,
        base_url: str,
        http_client: HttpClient,
        timeout: float = 30.0,
    ) -> None:
        self._base_url = base_url.rstrip("/")
        self._http_client = http_client
        self._timeout = timeout

    async def send(self, payload: dict) -> None:
        if not self._base_url:
            raise ValueError("ecb_base_url_not_configured")

        def request() -> None:
            response = self._http_client.post(
                f"{self._base_url}{_UPLOAD_COMPLETED_PATH}",
                json=payload,
                timeout=self._timeout,
            )
            response.raise_for_status()

        await asyncio.to_thread(request)
