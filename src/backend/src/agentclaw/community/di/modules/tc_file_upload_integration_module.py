"""DI wiring for direct TC upload-completion notifications."""
from __future__ import annotations

from typing import Annotated
import uuid

from injector import Module, inject, provider, singleton

from agentclaw.community.core.tc_file_upload_integrations.coordinator import (
    UploadCompletionCoordinator,
)
from agentclaw.community.core.tc_file_upload_integrations.upload_completion_sender import (
    HttpUploadCompletedSender,
)
from agentclaw.community.di.config import EcbConfig
from agentclaw.community.plugin_api.http_client import (
    QUALIFIER_GENERAL,
    HttpClient,
)
from agentclaw.community.utils.env_utils import get_current_env


class TcFileUploadIntegrationModule(Module):
    @singleton
    @provider
    @inject
    def upload_completed_sender(
        self,
        ecb_config: EcbConfig,
        http_client: Annotated[HttpClient, QUALIFIER_GENERAL],
    ) -> HttpUploadCompletedSender:
        base_url = (
            ecb_config.base_url_pre
            if get_current_env() == "pre"
            else ecb_config.base_url
        )
        return HttpUploadCompletedSender(
            base_url=base_url,
            http_client=http_client,
        )

    @singleton
    @provider
    @inject
    def upload_completion_coordinator(
        self,
        completion_sender: HttpUploadCompletedSender,
    ) -> UploadCompletionCoordinator:
        return UploadCompletionCoordinator(
            completion_sender=completion_sender,
            event_id_factory=lambda: f"evt_{uuid.uuid4().hex}",
        )
