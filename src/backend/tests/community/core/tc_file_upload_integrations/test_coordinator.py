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


def _intent(resource=_resource(SessionResourceStatus.UPLOAD_URL_ISSUED)):
    return SessionUploadIntent(
        resource=resource,
        grant=UploadGrant(transfer_id="transfer-internal-1", upload_type="SINGLE"),
    )


class _Sender:
    def __init__(self, failures: int = 0):
        self.calls = []
        self.failures = failures

    async def send(self, payload):
        self.calls.append(payload)
        if self.failures > 0:
            self.failures -= 1
            raise RuntimeError("ecb unavailable")


@pytest.fixture
def sender():
    return _Sender()


def _coordinator(sender):
    return UploadCompletionCoordinator(
        completion_sender=sender,
        event_id_factory=lambda: "evt_generated",
    )


def _register(coordinator, **overrides):
    values = {
        "intent": _intent(),
        "session_key": "session-raw",
        "scope_type": "session",
        "mime_type": "application/pdf",
        "conversation_id": "conversation-1",
        "group_id": None,
        "members": [],
    }
    values.update(overrides)
    return coordinator.register_upload_context(**values)


@pytest.mark.asyncio
async def test_coordinator_registers_context_without_wrapping_resource_service(sender):
    coordinator = _coordinator(sender)

    _register(coordinator)

    assert coordinator._contexts["sr_001"].mime_type == "application/pdf"
    assert sender.calls == []


@pytest.mark.asyncio
async def test_coordinator_snapshots_group_context_at_upload_intent(sender):
    coordinator = _coordinator(sender)

    _register(
        coordinator,
        scope_type="group",
        group_id="group-1",
        members=["user-2", "bot-2"],
    )

    assert coordinator._contexts["sr_001"].scope_type == "group"
    assert coordinator._contexts["sr_001"].group_id == "group-1"
    assert coordinator._contexts["sr_001"].members == ["user-2", "bot-2"]


@pytest.mark.asyncio
async def test_coordinator_non_ready_does_not_send(sender):
    coordinator = _coordinator(sender)
    _register(coordinator)

    await coordinator.notify_if_ready(_resource(SessionResourceStatus.DEVICE_SYNCING))

    assert sender.calls == []


@pytest.mark.asyncio
async def test_coordinator_ready_sends_resource_only_payload_once(sender):
    coordinator = _coordinator(sender)
    _register(coordinator)

    first = await coordinator.notify_if_ready(_resource(SessionResourceStatus.READY))
    second = await coordinator.notify_if_ready(_resource(SessionResourceStatus.READY))

    payload = sender.calls[0]
    assert first is None
    assert second is None
    assert payload["res_id"] == "sr_001"
    assert payload["event_id"] == "evt_generated"
    assert payload["session_id"] == "session-raw"
    assert len(sender.calls) == 1


@pytest.mark.asyncio
async def test_sender_failure_does_not_escape_the_sidecar():
    sender = _Sender(failures=1)
    coordinator = _coordinator(sender)
    _register(coordinator)

    await coordinator.notify_if_ready(_resource(SessionResourceStatus.READY))
    await coordinator.notify_if_ready(_resource(SessionResourceStatus.READY))

    assert len(sender.calls) == 1


@pytest.mark.asyncio
async def test_background_notification_is_fire_and_forget(sender, monkeypatch):
    coordinator = _coordinator(sender)
    _register(coordinator)

    def create_task(coro):
        coro.close()
        raise RuntimeError("event loop unavailable")

    monkeypatch.setattr("agentclaw.community.core.tc_file_upload_integrations.coordinator.asyncio.create_task", create_task)

    coordinator.notify_in_background(_resource(SessionResourceStatus.READY))

    assert sender.calls == []
