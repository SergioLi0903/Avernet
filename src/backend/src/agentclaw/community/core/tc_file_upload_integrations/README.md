# TC File Upload Integrations

## Context Boundary

```yaml
purpose: Direct ready-gated upload-completion notification.
provides:
  - UploadCompletionCoordinator
  - UploadCompletionContext
  - HttpUploadCompletedSender
consumes:
  - SessionResourceServiceProtocol
  - HttpClient
internal_dependencies:
  - agentclaw.community.core.session_resources
  - agentclaw.community.plugin_api
```

### Change impact

This module wraps the OCB session-resource control plane and sends a direct
resource-only notification once the observed materialization state is `ready`.

This is a direct-chain-first implementation. It intentionally keeps the upload
context, including the client-declared MIME type, in memory and does not persist
that metadata in `ac_session_resource`.
