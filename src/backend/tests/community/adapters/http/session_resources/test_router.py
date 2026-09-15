from __future__ import annotations

from collections.abc import AsyncIterator
from dataclasses import replace

from fastapi import HTTPException
import pytest
from pydantic import ValidationError

from agentclaw.community.adapters.http.auth.models import AuthenticatedUser
from agentclaw.community.adapters.http.session_resources.router import (
    list_pending_session_resources,
    materialize_status,
    materialized_callback,
    stream_content,
)
from agentclaw.community.adapters.http.session_resources.schemas import (
    MaterializedCallbackRequest,
    UploadIntentRequest,
)
from agentclaw.community.adapters.http.session_resources.router import (
    create_upload_intents,
)
from agentclaw.community.core.session_resources.types import (
    SessionResourceRecord,
    SessionResourceStatus,
    SessionUploadIntent,
    UploadGrant,
)
from agentclaw.community.core.tc_file_upload_integrations.coordinator import (
    UploadCompletionCoordinator,
)
from agentclaw.community.plugin_api.device_adapter_transport import (
    DeviceAdapterStreamResponse,
)


def _record(**overrides):
    values = {
        "resource_id": "sr_001",
        "owner_id": "owner-1",
        "bot_id": "bot-1",
        "scope_type": "personal_bot_chat",
        "scope_key_hash": "scope-hash",
        "session_key_hash": "session-hash",
        "engine_type": "claude_code",
        "tenant": "tenant",
        "bot_uuid": "uuid",
        "display_name": "a.txt",
        "filename": "a.txt",
        "device_path": "workspace/.teamclaw/session-files/scope/session/sr_001/a.txt",
        "workspace_relative_path": ".teamclaw/session-files/scope/session/sr_001/a.txt",
        "transfer_id": "transfer-1",
        "status": SessionResourceStatus.DEVICE_SYNCING,
        "task_id": "task-1",
        "task_version": 1,
    }
    values.update(overrides)
    return SessionResourceRecord(**values)


class _RecordingSender:
    def __init__(self) -> None:
        self.payloads: list[dict] = []

    async def send(self, payload: dict) -> None:
        self.payloads.append(payload)


class _NoopSender:
    async def send(self, payload: dict) -> None:
        return None


class _RecordingSender:
    def __init__(self) -> None:
        self.payloads: list[dict] = []

    async def send(self, payload: dict) -> None:
        self.payloads.append(payload)


class _Service:
    def __init__(self) -> None:
        self.callback_kwargs = None

    def create_upload_intent(self, **kwargs):
        self.intent_kwargs = kwargs
        return SessionUploadIntent(
            resource=_record(),
            grant=UploadGrant(transfer_id="transfer-1", upload_type="SINGLE"),
        )

    def get_status(self, **kwargs):
        self.status_kwargs = kwargs
        return _record()

    def list_pending(self, **kwargs):
        self.pending_kwargs = kwargs
        return [_record()]

    def materialized_callback(self, **kwargs):
        self.callback_kwargs = kwargs
        return replace(_record(), status=SessionResourceStatus.READY)

    async def open_content(self, **kwargs):
        self.content_kwargs = kwargs

        async def chunks() -> AsyncIterator[bytes]:
            yield b"hello"

        async def close() -> None:
            self.content_closed = True

        self.content_closed = False
        return (
            replace(_record(), status=SessionResourceStatus.READY),
            DeviceAdapterStreamResponse(
                status_code=200,
                headers={
                    "content-type": "text/plain",
                    "content-length": "5",
                    "content-disposition": 'inline; filename="a.txt"',
                    "x-internal-token": "hidden",
                },
                body=chunks(),
                close=close,
            ),
        )


@pytest.mark.asyncio
async def test_upload_intent_keeps_client_mime_type_out_of_resource_service():
    service = _Service()
    body = UploadIntentRequest(
        bot_id="bot-1",
        session_key="session-raw",
        scope_type="friend_bot_chat",
        engine_type="openclaw",
        files=[
            {
                "filename": "report.pdf",
                "size_bytes": 12,
                "content_hash": "hash-1",
                "mime_type": "application/pdf",
            }
        ],
        conversation_id="conversation-1",
        group_id=None,
        members=[],
    )
    service.get_status = lambda **kwargs: replace(  # type: ignore[method-assign]
        _record(), status=SessionResourceStatus.READY
    )
    sender = _RecordingSender()
    coordinator = UploadCompletionCoordinator(
        resource_service=service,
        completion_sender=sender,
        event_id_factory=lambda: "evt_generated",
    )

    result = await create_upload_intents(
        body=body,
        user=AuthenticatedUser("id", "owner-1", "owner-1"),
        coordinator=coordinator,
    )

    assert "mime_type" not in service.intent_kwargs
    assert "mime_type" not in result["files"][0]
    await materialize_status(
        "sr_001",
        "bot-1",
        "session-raw",
        user=AuthenticatedUser("id", "owner-1", "owner-1"),
        coordinator=coordinator,
    )
    assert sender.payloads[0]["mime_type"] == "application/pdf"


def test_upload_intent_request_accepts_positive_binding_id_only():
    body = UploadIntentRequest(
        bot_id="bot-1",
        session_key="session-raw",
        scope_type="friend_bot_chat",
        engine_type="openclaw",
        binding_id=91,
        files=[{"filename": "report.txt"}],
    )

    assert body.binding_id == 91

    with pytest.raises(ValidationError, match="binding_id"):
        UploadIntentRequest(
            bot_id="bot-1",
            session_key="session-raw",
            scope_type="friend_bot_chat",
            engine_type="openclaw",
            binding_id=True,
            files=[{"filename": "report.txt"}],
        )



@pytest.mark.asyncio
async def test_polling_only_reads_backend_service_state():
    service = _Service()
    user = AuthenticatedUser("id", "owner-1", "owner-1")

    coordinator = UploadCompletionCoordinator(
        resource_service=service,
        completion_sender=_NoopSender(),
        event_id_factory=lambda: "evt_unused",
    )
    result = await materialize_status(
        "sr_001",
        "bot-1",
        "session-raw",
        user=user,
        coordinator=coordinator,
    )

    assert result["status"] == "device_syncing"
    assert service.status_kwargs == {
        "owner_id": "owner-1",
        "bot_id": "bot-1",
        "session_key": "session-raw",
        "resource_id": "sr_001",
    }


@pytest.mark.asyncio
async def test_ready_status_sends_full_resource_only_context():
    service = _Service()
    service.get_status = lambda **kwargs: replace(  # type: ignore[method-assign]
        _record(), status=SessionResourceStatus.READY
    )
    sender = _RecordingSender()
    coordinator = UploadCompletionCoordinator(
        resource_service=service,
        completion_sender=sender,
        event_id_factory=lambda: "evt_generated",
    )
    coordinator.create_upload_intent(
        owner_id="owner-1",
        bot_id="bot-1",
        session_key="session-raw",
        scope_type="friend_bot_chat",
        engine_type="openclaw",
        filename="report.pdf",
        mime_type="application/pdf",
        size_bytes=12,
        conversation_id="conversation-1",
        group_id=None,
        members=[],
    )

    result = await materialize_status(
        "sr_001",
        "bot-1",
        "session-raw",
        user=AuthenticatedUser("id", "owner-1", "owner-1"),
        coordinator=coordinator,
    )

    payload = sender.payloads[0]
    assert result["status"] == "ready"
    assert payload["res_id"] == "sr_001"
    assert payload["session_id"] == "session-raw"
    assert payload["conversation_id"] == "conversation-1"
    assert "transfer_id" not in payload
    assert "oss_url" not in payload


@pytest.mark.asyncio
async def test_pending_lists_only_control_plane_records():
    service = _Service()
    user = AuthenticatedUser("id", "owner-1", "owner-1")

    result = await list_pending_session_resources(
        "bot-1",
        "session-raw",
        user=user,
        service=service,
    )

    assert result["files"][0]["resource_id"] == "sr_001"
    assert service.pending_kwargs == {
        "owner_id": "owner-1",
        "bot_id": "bot-1",
        "session_key": "session-raw",
    }


@pytest.mark.asyncio
async def test_callback_uses_task_capability_and_does_not_store_absolute_path():
    service = _Service()
    body = MaterializedCallbackRequest(
        transfer_id="transfer-1",
        task_id="task-1",
        task_version=1,
        ready=True,
        canonical_bot_absolute_path="/home/admin/private/workspace/a.txt",
        relative_path=".teamclaw/session-files/scope/session/sr_001/a.txt",
        size_bytes=1,
        content_hash="hash",
    )

    result = await materialized_callback(
        "sr_001",
        body,
        x_materialization_task_id="task-1",
        service=service,
    )

    assert result == {"applied": True, "status": "ready"}
    stored = service.callback_kwargs["materialized_ref"]
    assert "canonical_bot_absolute_path" not in stored
    assert stored["path_hash"]


@pytest.mark.asyncio
async def test_callback_rejects_wrong_task_capability():
    with pytest.raises(HTTPException) as exc:
        await materialized_callback(
            "sr_001",
            MaterializedCallbackRequest(
                transfer_id="transfer-1",
                task_id="task-1",
                task_version=1,
                ready=False,
                error_code="pull_failed",
            ),
            x_materialization_task_id="wrong",
            service=_Service(),
        )

    assert exc.value.status_code == 401


@pytest.mark.asyncio
async def test_content_proxies_only_safe_headers_and_closes_upstream():
    service = _Service()
    user = AuthenticatedUser("id", "owner-1", "owner-1")

    response = await stream_content(
        "sr_001",
        "bot-1",
        "session-raw",
        disposition="inline",
        user=user,
        service=service,
    )

    assert service.content_kwargs["disposition"] == "inline"
    assert response.headers["content-type"] == "text/plain"
    assert response.headers["content-length"] == "5"
    assert "x-internal-token" not in response.headers
    assert [chunk async for chunk in response.body_iterator] == [b"hello"]
    assert service.content_closed is True
