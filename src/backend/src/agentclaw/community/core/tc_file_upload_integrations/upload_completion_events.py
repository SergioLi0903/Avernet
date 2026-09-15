"""Ephemeral context for one direct TC upload-completion notification."""
from __future__ import annotations

from dataclasses import dataclass, field

from agentclaw.community.core.session_resources.types import (
    SessionResourceRecord,
    SessionResourceStatus,
)


@dataclass(frozen=True)
class UploadCompletionContext:
    event_id: str
    resource_id: str
    user_id: str
    bot_id: str
    file_name: str
    mime_type: str | None
    size_bytes: int | None
    session_id: str
    conversation_id: str | None
    scope_type: str
    group_id: str | None
    members: list[str] = field(default_factory=list)


class UploadCompletedSender:
    """Minimal sender seam; production uses the HTTP adapter."""

    async def send(self, payload: dict) -> None:
        raise NotImplementedError


def build_completion_payload(context: UploadCompletionContext) -> dict:
    """Build the resource-only notification sent to the knowledge system."""
    return {
        "event_id": context.event_id,
        "user_id": context.user_id,
        "bot_id": context.bot_id,
        "res_id": context.resource_id,
        "file_name": context.file_name,
        "mime_type": context.mime_type,
        "size_bytes": context.size_bytes,
        "session_id": context.session_id,
        "conversation_id": context.conversation_id,
        "scope_type": context.scope_type,
        "group_id": context.group_id,
        "members": list(context.members),
    }


def should_notify(resource: SessionResourceRecord) -> bool:
    """Only a fully materialized resource is eligible for notification."""
    return resource.status is SessionResourceStatus.READY
