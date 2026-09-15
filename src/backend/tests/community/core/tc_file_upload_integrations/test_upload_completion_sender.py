from __future__ import annotations

import httpx
import pytest

from agentclaw.community.core.tc_file_upload_integrations.upload_completion_sender import (
    HttpUploadCompletedSender,
)

_PAYLOAD = {
    "event_id": "evt_001",
    "user_id": "user-1",
    "bot_id": "bot-1",
    "res_id": "sr_001",
    "file_name": "report.pdf",
    "mime_type": "application/pdf",
    "size_bytes": 123,
    "session_id": "session-raw",
    "conversation_id": "conversation-1",
    "scope_type": "session",
    "group_id": None,
    "members": [],
}


class _HttpClient:
    def __init__(self, status_code: int = 200) -> None:
        self.status_code = status_code
        self.calls: list[tuple[str, dict, float]] = []

    def post(self, path, *, json, timeout):
        self.calls.append((path, json, timeout))
        return httpx.Response(
            self.status_code,
            request=httpx.Request("POST", path),
            json={"status": "accepted"},
        )


@pytest.mark.asyncio
async def test_http_sender_posts_resource_only_payload_to_contract_path():
    http_client = _HttpClient()
    sender = HttpUploadCompletedSender(
        base_url="http://knowledge.example",
        http_client=http_client,
        timeout=12.0,
    )

    await sender.send(_PAYLOAD)

    url, payload, timeout = http_client.calls[0]
    assert url == (
        "http://knowledge.example"
        "/api/v1/knowledge/integrations/tc/files/upload-completed"
    )
    assert payload == _PAYLOAD
    assert timeout == 12.0
    assert "transfer_id" not in payload
    assert "oss_url" not in payload


@pytest.mark.asyncio
async def test_http_sender_rejects_unconfigured_base_url():
    sender = HttpUploadCompletedSender(
        base_url="",
        http_client=_HttpClient(),
    )

    with pytest.raises(ValueError, match="ecb_base_url_not_configured"):
        await sender.send(_PAYLOAD)


@pytest.mark.asyncio
async def test_http_sender_surfaces_non_2xx_response():
    http_client = _HttpClient(status_code=502)
    sender = HttpUploadCompletedSender(
        base_url="http://knowledge.example",
        http_client=http_client,
    )

    with pytest.raises(httpx.HTTPStatusError):
        await sender.send(_PAYLOAD)
