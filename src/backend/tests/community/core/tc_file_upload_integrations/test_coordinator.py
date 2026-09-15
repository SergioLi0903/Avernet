from __future__ import annotations

import pytest

from agentclaw.community.core.session_resources.types import (
    SessionResourceRecord,
    SessionResourceStatus,
    SessionUploadIntent,
    UploadGrant,
)
from agentclaw.community.core.tc_file_upload_integrations.coordinator import (
    UploadCompletionCoordinator,
)


def _resource(status=SessionResourceStatus.DEVICE_SYNCING):
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


class _ResourceService:
    def __init__(self, resource):
        self.resource = resource
        self.create_kwargs = None
        self.status_kwargs = None

    def create_upload_intent(self, **kwargs):
        self.create_kwargs = kwargs
        return SessionUploadIntent(
            resource=self.resource,
            grant=UploadGrant(transfer_id="transfer-internal-1", upload_type="SINGLE"),
        )

    def get_status(self, **kwargs):
        self.status_kwargs = kwargs
        return self.resource


class _Sender:
    def __init__(self):
        self.calls = []

    async def send(self, payload):
        self.calls.append(payload)


@pytest.fixture
def sender():
    return _Sender()


def _coordinator(resource_status, sender):
    return UploadCompletionCoordinator(
        resource_service=_ResourceService(_resource(resource_status)),
        completion_sender=sender,
        event_id_factory=lambda: "evt_generated",
    )


@pytest.mark.asyncio
async def test_coordinator_registers_context_at_upload_intent(sender):
    coordinator = _coordinator(SessionResourceStatus.UPLOAD_URL_ISSUED, sender)

    intent = coordinator.create_upload_intent(
        owner_id="user-1",
        bot_id="bot-1",
        session_key="session-raw",
        scope_type="session",
        engine_type="claude_code",
        filename="report.pdf",
        mime_type="application/pdf",
        size_bytes=123,
        conversation_id="conversation-1",
        group_id=None,
        members=[],
    )

    assert intent.resource.resource_id == "sr_001"
    assert coordinator._contexts["sr_001"].mime_type == "application/pdf"
    assert "mime_type" not in coordinator._resource_service.create_kwargs
    assert sender.calls == []


@pytest.mark.asyncio
async def test_coordinator_snapshots_group_context_at_upload_intent(sender):
    coordinator = _coordinator(SessionResourceStatus.UPLOAD_URL_ISSUED, sender)

    coordinator.create_upload_intent(
        owner_id="user-1",
        bot_id="bot-1",
        session_key="session-raw",
        scope_type="group",
        engine_type="claude_code",
        filename="report.pdf",
        mime_type="application/pdf",
        size_bytes=123,
        conversation_id="conversation-1",
        group_id="group-1",
        members=["user-2", "bot-2"],
    )

    assert coordinator._contexts["sr_001"].scope_type == "group"
    assert coordinator._contexts["sr_001"].group_id == "group-1"
    assert coordinator._contexts["sr_001"].members == ["user-2", "bot-2"]


@pytest.mark.asyncio
async def test_coordinator_non_ready_does_not_send(sender):
    coordinator = _coordinator(SessionResourceStatus.DEVICE_SYNCING, sender)
    coordinator.create_upload_intent(
        owner_id="user-1",
        bot_id="bot-1",
        session_key="session-raw",
        scope_type="session",
        engine_type="claude_code",
        filename="report.pdf",
        mime_type="application/pdf",
        size_bytes=123,
        conversation_id="conversation-1",
        group_id=None,
        members=[],
    )

    resource = await coordinator.poll_materialize_status(
        owner_id="user-1",
        bot_id="bot-1",
        session_key="session-raw",
        resource_id="sr_001",
    )

    assert resource.status is SessionResourceStatus.DEVICE_SYNCING
    assert sender.calls == []


@pytest.mark.asyncio
async def test_coordinator_ready_sends_resource_only_payload_once(sender):
    coordinator = _coordinator(SessionResourceStatus.READY, sender)
    coordinator.create_upload_intent(
        owner_id="user-1",
        bot_id="bot-1",
        session_key="session-raw",
        scope_type="session",
        engine_type="claude_code",
        filename="report.pdf",
        mime_type="application/pdf",
        size_bytes=123,
        conversation_id="conversation-1",
        group_id=None,
        members=[],
    )

    first = await coordinator.poll_materialize_status(
        owner_id="user-1",
        bot_id="bot-1",
        session_key="session-raw",
        resource_id="sr_001",
    )
    second = await coordinator.poll_materialize_status(
        owner_id="user-1",
        bot_id="bot-1",
        session_key="session-raw",
        resource_id="sr_001",
    )

    payload = sender.calls[0]
    assert payload["res_id"] == "sr_001"
    assert payload["event_id"] == "evt_generated"
    assert payload["session_id"] == "session-raw"
    assert first.status is SessionResourceStatus.READY
    assert second.status is SessionResourceStatus.READY
    assert len(sender.calls) == 1
