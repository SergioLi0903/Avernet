# TC File Upload Integrations

## Context Boundary

```yaml
purpose: Non-blocking best-effort ready-gated upload-completion notification.
provides:
  - UploadCompletionCoordinator
  - UploadCompletionContext
  - HttpUploadCompletedSender
consumes:
  - SessionUploadIntent
  - SessionResourceRecord
  - HttpClient
internal_dependencies:
  - agentclaw.community.core.session_resources
  - agentclaw.community.plugin_api
```

### Change impact

The primary TC upload and materialization paths continue to call the OCB
session-resource service directly. This module only observes a successful intent,
retains an ephemeral completion context, and schedules one best-effort
resource-only notification when `ready` is observed.

The internal TC and public OpenAPI upload surfaces keep their primary service
calls unchanged. The public request accepts an optional normalized upload MIME
type while the response remains the stable session-file contract. The upload
context, including the client-declared MIME type, stays in memory and is not
persisted in `ac_session_resource`. Context capture, task scheduling, and
ECB delivery failures are logged as sidecar failures; they do not change TC API
responses.
