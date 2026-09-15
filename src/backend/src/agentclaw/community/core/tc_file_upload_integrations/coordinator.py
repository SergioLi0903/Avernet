"""Non-blocking ready-gated upload-completion sidecar."""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Callable

from agentclaw.community.core.session_resources.types import (
    SessionResourceRecord,
    SessionUploadIntent,
)
from agentclaw.community.core.tc_file_upload_integrations.upload_completion_events import (
    UploadCompletedSender,
    UploadCompletionContext,
    build_completion_payload,
    should_notify,
)

logger = logging.getLogger("tc_upload_completion.coordinator")


class UploadCompletionCoordinator:
    """Hold upload context in memory and make best-effort ECB notifications.

    This coordinator is deliberately not a wrapper for the session-resource
    control plane. The primary TC flow calls that service directly; this module
    observes successful intents and schedules one best-effort, resource-only
    notification when a ready state is observed.
    """

    def __init__(
        self,
        *,
        completion_sender: UploadCompletedSender,
        event_id_factory: Callable[[], str],
    ) -> None:
        self._completion_sender = completion_sender
        self._event_id_factory = event_id_factory
        self._contexts: dict[str, UploadCompletionContext] = {}
        self._notified: set[str] = set()
        self._notification_tasks: set[asyncio.Task[None]] = set()

    def register_upload_context(
        self,
        *,
        intent: SessionUploadIntent,
        session_key: str,
        scope_type: str,
        mime_type: str | None = None,
        conversation_id: str | None = None,
        group_id: str | None = None,
        members: list[str] | None = None,
    ) -> None:
        """Capture ephemeral metadata without making a successful intent fail."""
        resource = intent.resource
        try:
            context = UploadCompletionContext(
                event_id=self._event_id_factory(),
                resource_id=resource.resource_id,
                user_id=resource.owner_id,
                bot_id=resource.bot_id,
                file_name=resource.filename,
                mime_type=mime_type,
                size_bytes=resource.size_bytes,
                session_id=session_key,
                conversation_id=conversation_id,
                scope_type=scope_type,
                group_id=group_id,
                members=list(members or []),
            )
            self._contexts[resource.resource_id] = context
        except Exception:
            logger.exception(
                "tc_upload_completion.context_capture_failed resource_id=%s",
                resource.resource_id,
            )

    def notify_in_background(self, resource: SessionResourceRecord) -> None:
        """Fire a detached task without affecting the TC response path."""
        try:
            if not self._is_pending(resource):
                return
            task = asyncio.create_task(self.notify_if_ready(resource))
            self._notification_tasks.add(task)
            task.add_done_callback(self._notification_tasks.discard)
        except Exception:
            logger.exception(
                "tc_upload_completion.notification_schedule_failed resource_id=%s",
                resource.resource_id,
            )

    async def notify_if_ready(self, resource: SessionResourceRecord) -> None:
        """Try to send once while never leaking a sidecar failure to TC."""
        if not self._is_pending(resource):
            return

        resource_id = resource.resource_id
        context = self._contexts[resource_id]
        # Mark before sending so concurrent polling cannot enqueue duplicate sends.
        self._notified.add(resource_id)
        payload = build_completion_payload(context)
        try:
            await self._completion_sender.send(payload)
        except Exception:
            logger.exception(
                "tc_upload_completion.send_failed "
                "event_id=%s resource_id=%s session_id=%s bot_id=%s",
                context.event_id,
                context.resource_id,
                context.session_id,
                context.bot_id,
            )
            return
        logger.info(
            "tc_upload_completion.sent "
            "event_id=%s resource_id=%s session_id=%s bot_id=%s",
            context.event_id,
            context.resource_id,
            context.session_id,
            context.bot_id,
        )

    def _is_pending(self, resource: SessionResourceRecord) -> bool:
        if not should_notify(resource):
            return False
        if resource.resource_id in self._notified:
            return False
        return resource.resource_id in self._contexts
