# TC resource-only upload completion

## Summary

- Let TC send a `ready`-only upload-completed notification to ECB.
- Carry only the resource ID and business context.
- Use ECB to lookup the resource, create the share link, download the file, and build the knowledge products.
- Keep this integration in-memory and non-blocking for the current phase.

## Motivation

The legacy flow exposes `transfer_id` or `oss_url` to downstream services.
That couples TC to the download mechanics and leaks sensitive materialization details.

The new boundary is:

```text
TC       -> ECB: resource ID + business context
ECB      -> TC DB: resource ID -> transfer_id
ECB/BaaS  -> share link -> download -> ingest
```

## User stories

- As TC, I want to notify ECB only after a upload is materialized to `ready`.
- As ECB, I want to use the resource ID and context and finish the download and ingestion myself.
- As a caller, I want the existing upload flow to stay compatible.
- As a TC user, I want ECB or sidecar failures to leave upload and materialization behavior unchanged.

## Acceptance criteria

### OCB / TC boundary

- [x] Upload intent still returns the same stable `resource_id`.
- [x] Upload intent still calls `SessionResourceServiceProtocol.create_upload_intent` directly.
- [x] `materialize-status` still calls `SessionResourceServiceProtocol.get_status` directly.
- [x] `materialize-status` is the trigger for the completion event.
- [x] A non-`ready` status never notifies ECB.
- [x] A `ready` status makes exactly one best-effort direct notification attempt.
- [x] Context capture, notification scheduling, and ECB delivery failures are logged and do not fail the primary TC response.
- [x] The outgoing payload contains only resource and business metadata.
- [x] The outgoing payload does not contain `transfer_id`, `oss_url`, `share_url`, `inline_file`, or any signed URL.
- [x] The context is held in memory. This phase does not create a durable event table.
- [x] The upload-intent context includes `mime_type`, `conversation_id`, `group_id`, and `members`; `mime_type` remains ephemeral and is not persisted in `ac_session_resource`.
- [x] The OpenAPI upload-intent contract accepts optional client-reported `mime_type`; the frontend sends `resolveUploadMime(file.name, file.type)` while the primary session-resource service call remains unchanged.

### ECB boundary

- [x] ECB receives the resource-only payload and trusts TC metadata for the upload context.
- [x] ECB resolves the resource by `resource_id`.
- [x] ECB creates a short-lived share link and downloads the object itself.
- [x] ECB still uses the standard ingestion pipeline to build knowledge products.
- [x] TC remains decoupled from `transfer_id` and `oss_url`.

## Out of scope

- Adding a persistent upload-event table
- Persisting retry state beyond the current process
- Making TC materialization relational
- TC-side share-link or OSS-URL acquisition
- Re-foldering BaaS or ECB into the open-source repo

## Current implementation notes

- The coordinator lives at `src/backend/src/agentclaw/community/core/tc_file_upload_integrations/`.
- The eager context is in memory, so the current flow is best-effort rather than restart-safe.
- The router calls the OCB session-resource service first for both upload intents and status polling. The coordinator never wraps that service.
- The ready notification is scheduled as a detached asyncio task after `get_status` succeeds, with a strong task reference until completion.
- The coordinator keeps `mime_type` only in its ephemeral completion context so the event payload can forward it without a database schema change.
- The public OpenAPI upload-intent request accepts optional client-reported `mime_type`, and the frontend sends `resolveUploadMime(file.name, file.type)`, without exposing that field in upload responses.
- Tests cover ready / not-ready, the resource-only payload shape, direct service calls, context capture, fire-and-forget delivery, sidecar failure isolation, HTTP delivery, and the integration boundary.
