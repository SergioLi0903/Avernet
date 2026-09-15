# TC resource-only upload completion

## Summary

- Let TC send a `ready`-only upload-completed notification to ECB.
- Carry only the resource ID and business context.
- Use ECB to lookup the resource, create the share link, download the file, and build the knowledge products.
- Keep this integration direct and in-memory for the current phase.

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

## Acceptance criteria

### OCB / TC boundary

- [x] Upload intent still returns the same stable `resource_id`.
- [x] `materialize-status` is the trigger for the completion event.
- [x] A non-`ready` status never notifies ECB.
- [x] A `ready` status sends exactly one direct notification.
- [x] The outgoing payload contains only resource and business metadata.
- [x] The outgoing payload does not contain `transfer_id`, `oss_url`, `share_url`, `inline_file`, or any signed URL.
- [x] The context is held in memory. This phase does not create a durable event table.
- [x] The upload-intent context includes `mime_type`, `conversation_id`, `group_id`, and `members`; `mime_type` remains ephemeral and is not persisted in `ac_session_resource`.

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
- The eager context is in memory, so the current flow is direct-chain-first rather than restart-safe.
- OCB’s session-resource control plane remains unchanged. The coordinator keeps `mime_type` only in its ephemeral completion context so the event payload can forward it without a database schema change.
- Tests cover ready / not-ready, the resource-only payload shape, context capture, HTTP delivery, and the integration boundary.
