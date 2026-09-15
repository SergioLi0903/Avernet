"""Direct ready-gated upload-completion coordinator."""
from __future__ import annotations

import logging
from collections.abc import Callable

from agentclaw.community.core.session_resources.session_resource_service_protocol import (
    SessionResourceServiceProtocol,
)
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
    """Keep upload context in memory and notify ECB once `ready` is observed.

    This is a direct end-to-end path for today's integration goal. It does not
    create or read a completion-event database table.
    """

    def __init__(
        self,
        *,
        resource_service: SessionResourceServiceProtocol,
        completion_sender: UploadCompletedSender,
        event_id_factory: Callable[[], str],
    ) -> None:
        self._resource_service = resource_service
        self._completion_sender = completion_sender
        self._event_id_factory = event_id_factory
        self._contexts: dict[str, UploadCompletionContext] = {}
        self._notified: set[str] = set()

    def create_upload_intent(
        self,
        *,
        owner_id: str,
        bot_id: str,
        session_key: str,
        scope_type: str,
        engine_type: str,
        filename: str,
        target_entity_id: str | None = None,
        binding_id: int | None = None,
        size_bytes: int | None = None,
        content_hash: str | None = None,
        mime_type: str | None = None,
        conversation_id: str | None = None,
        group_id: str | None = None,
        members: list[str] | None = None,
    ) -> SessionUploadIntent:
        intent = self._resource_service.create_upload_intent(
            owner_id=owner_id,
            bot_id=bot_id,
            session_key=session_key,
            scope_type=scope_type,
            engine_type=engine_type,
            filename=filename,
            target_entity_id=target_entity_id,
            binding_id=binding_id,
            size_bytes=size_bytes,
            content_hash=content_hash,
        )

        resource_id = intent.resource.resource_id
        self._register_context(
            resource_id=resource_id,
            user_id=owner_id,
            bot_id=bot_id,
            file_name=filename,
            mime_type=mime_type,
            size_bytes=size_bytes,
            session_id=session_key,
            conversation_id=conversation_id,
            scope_type=scope_type,
            group_id=group_id,
            members=list(members or []),
        )
        return intent

    async def poll_materialize_status(
        self,
        *,
        owner_id: str,
        bot_id: str,
        session_key: str,
        resource_id: str,
    ) -> SessionResourceRecord:
        resource = self._resource_service.get_status(
            owner_id=owner_id,
            bot_id=bot_id,
            session_key=session_key,
            resource_id=resource_id,
        )
        context = self._contexts.get(resource_id)
        if (
            context is not None
            and should_notify(resource)
            and resource_id not in self._notified
        ):
            payload = build_completion_payload(context)
            await self._completion_sender.send(payload)
            self._notified.add(resource_id)
            logger.info(
                "tc_upload_completion.sent "
                "event_id=%s resource_id=%s session_id=%s bot_id=%s",
                context.event_id,
                context.resource_id,
                context.session_id,
                context.bot_id,
            )
        return resource

    def _register_context(
        self,
        *,
        resource_id: str,
        user_id: str,
        bot_id: str,
        file_name: str,
        mime_type: str | None,
        size_bytes: int | None,
        session_id: str,
        conversation_id: str | None,
        scope_type: str,
        group_id: str | None,
        members: list[str],
    ) -> None:
        context = UploadCompletionContext(
            event_id=self._event_id_factory(),
            resource_id=resource_id,
            user_id=user_id,
            bot_id=bot_id,
            file_name=file_name,
            mime_type=mime_type,
            size_bytes=size_bytes,
            session_id=session_id,
            conversation_id=conversation_id,
            scope_type=scope_type,
            group_id=group_id,
            members=members,
        )
        self._contexts[resource_id] = context
