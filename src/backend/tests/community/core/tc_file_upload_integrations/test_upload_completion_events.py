from __future__ import annotations

import pytest

from agentclaw.community.core.session_resources.types import (
    SessionResourceRecord,
    SessionResourceStatus,
)
from agentclaw.community.core.tc_file_upload_integrations.upload_completion_events import (
    UploadCompletionContext,
    build_completion_payload,
    should_notify,
)


def _resource_record(status=SessionResourceStatus.READY):
    return SessionResourceRecord(
        resource_id="sr_001",
        owner_id="user-1",
        bot_id="bot-1",
        scope_type="session",
        scope_key_hash="scope-hash",
        session_key_hash="session-hash",
        engine_type="claude_code",
        tenant="tenant-1",
        bot_uuid="bot-uuid-1",
        display_name="report.pdf",
        filename="report.pdf",
        device_path="workspace/report.pdf",
        workspace_relative_path="report.pdf",
        transfer_id="transfer-internal-1",
        status=status,
        size_bytes=123,
    )


def _context():
    return UploadCompletionContext(
        event_id="evt_001",
        resource_id="sr_001",
        user_id="user-1",
        bot_id="bot-1",
        file_name="report.pdf",
        mime_type="application/pdf",
        size_bytes=123,
        session_id="session-raw",
        conversation_id="conversation-1",
        scope_type="session",
        group_id=None,
        members=[],
    )


@pytest.mark.asyncio
async def test_payload_is_resource_only_and_preserves_identity():
    payload = build_completion_payload(_context())

    assert payload == {
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
    assert "transfer_id" not in payload
    assert "oss_url" not in payload
    assert "share_url" not in payload
    assert "inline_file" not in payload


@pytest.mark.asyncio
async def test_only_ready_resources_should_notify():
    assert should_notify(_resource_record(SessionResourceStatus.READY)) is True
    assert should_notify(_resource_record(SessionResourceStatus.DEVICE_SYNCING)) is False
    assert should_notify(_resource_record(SessionResourceStatus.UPLOAD_URL_ISSUED)) is False
