# Dreaming Memory Architecture Design

## Goal

Implement the "记忆整理 / 梦境" product capability on top of the current memory stack without rewriting the main memory engine. The design must unify command entrypoints, runtime status, user-readable reports, correction operations, and admin visibility while keeping long-term memory truth in the existing stores.

## Scope

This design covers:

- runtime architecture for dreaming orchestration
- data model for config, runs, reports, candidates, and decisions
- command and admin API surfaces
- persistence boundaries and failure recovery
- integration points with existing `Working / Daily / Episodic / Semantic / Relationship / UserUnderstanding`

This design does not replace the current memory truth sources and does not redesign prompt assembly as part of V1.

## Recommendation

Use a **middle orchestration layer**:

- keep existing memory stores as the authority
- add a dedicated `DreamingOrchestrator`
- expose dreaming through CLI, gateway commands, and admin endpoints
- persist dreaming runtime state and reports separately from long-term memory truth

This gives a clean product surface without dragging all product behavior into `gateway/commands.py` or the Web UI.

## Architecture

### Layer 1: Entry surfaces

- CLI command handlers
- gateway slash commands
- admin HTTP endpoints
- optional scheduled trigger

These surfaces must remain thin. They should call one orchestrator-facing API and render the result.

### Layer 2: Dreaming orchestration

Introduce the following internal modules:

- `DreamingOrchestrator`
  - public entrypoint for `on/off/status/run/doctor/report/delete-last-run-items`
- `DreamingCandidateCollector`
  - assemble normalized candidates from current memory layers
- `DreamingPromotionGovernor`
  - choose `promote / keep_short_term / discard / hold_sensitive`
- `DreamingPersistenceFacade`
  - write approved promotions into semantic, episodic, relationship, and understanding projection layers
- `DreamingReportBuilder`
  - build both user-facing and debug-facing reports
- `DreamingDoctor`
  - summarize index/runtime/store health and recovery suggestions

### Layer 3: Existing memory authority

- `WorkingMemoryStore`
- `DailyMemoryStore`
- `EpisodicStore`
- `SemanticStore`
- `RelationshipStore`
- `UserUnderstandingStore`

Dreaming is allowed to read from these stores and write approved long-term promotions back into them, but it must not clone them into a separate truth source.

## Data model

### DreamingConfig

Stored under `models.yaml.memory.dreaming`.

Fields:

- `enabled`
- `auto_run_enabled`
- `min_interval_minutes`
- `max_candidates`
- `max_promotions`
- `report_retention`
- `show_sensitive_reason_only`

V1 requires only a minimal config surface:

- `enabled`
- `auto_run_enabled`
- `report_retention`
- `max_candidates`
- `max_promotions`

### DreamingRunRecord

Represents one run:

- `run_id`
- `bot_id`
- `user_id`
- `trigger_source`
- `trigger_reason`
- `status`
- `started_at`
- `finished_at`
- `failed_stage`
- `error_code`
- `error_message`
- `candidate_count`
- `promoted_count`
- `kept_short_term_count`
- `discarded_count`
- `held_sensitive_count`

### DreamingCandidate

Normalized candidate protocol:

- `candidate_id`
- `source_layer`
- `source_ref`
- `summary`
- `detail`
- `confidence`
- `importance`
- `sensitivity`
- `proposed_target`
- `reason_tags`

### PromotionDecision

- `candidate_id`
- `action`
- `target_store`
- `reason_tags`
- `written_ref`

### DreamingReport

Stores:

- `run_id`
- `user_summary`
- `debug_summary`
- `promoted_items`
- `kept_short_term_items`
- `discarded_items`
- `held_sensitive_items`

Important:

`DreamingReport` stores references to written memory items instead of duplicating the long-term truth payload.

## Persistence strategy

### Keep truth where it already lives

Long-term truth remains in:

- `semantic.db`
- `episodic.db`
- `relationship.db`
- `user_understanding.json`

### Add dreaming-specific runtime persistence

Under `~/.ai-companion/data/bots/{bot_id}/memory/`, add dreaming-owned persistence for:

- latest config snapshot if needed at runtime
- run history
- report history
- latest status snapshot

Preferred V1 storage:

- `dreaming_runs.db`
- `dreaming_reports.db`

This matches the repo's existing SQLite-heavy operational style and keeps structured querying easy for admin endpoints.

## Consistency strategy

Do not attempt a single cross-store global transaction over SQLite plus JSON projection writes.

Use staged consistency instead:

1. collect candidates
2. compute decisions
3. persist approved promotions
4. build report from actual write results
5. persist run/report state

This ensures:

- reports only claim writes that actually succeeded
- failed runs show the precise failed stage
- correction actions can rely on stored write references

## Runtime flow

### Manual run

1. command or admin endpoint calls orchestrator
2. orchestrator creates run context
3. candidate collector reads recent memory signals
4. governor grades candidates
5. persistence facade writes approved items
6. report builder builds user/debug report
7. run store persists record
8. caller returns formatted response

### Status

Status must come from the dreaming run store, not from ad hoc UI composition.

Required status fields:

- enabled
- last run time
- last run status
- latest summary
- latest counts
- latest failure

### Doctor

Doctor must provide one unified response from:

- dreaming run store health
- memory engine availability
- vector/understanding path availability
- latest failure stage
- recommended recovery action

## Product surface mapping

### Gateway commands

Support:

- `/dream on`
- `/dream off`
- `/dream status`
- `/dream run`
- `/dream doctor`
- `/dream report`

### CLI

Support the same operational surface where feasible.

### Admin API

Add endpoints for:

- `GET /admin/memory/{bot_id}/dreaming/status`
- `POST /admin/memory/{bot_id}/dreaming/run`
- `GET /admin/memory/{bot_id}/dreaming/report`
- `POST /admin/memory/{bot_id}/dreaming/doctor`
- `DELETE /admin/memory/{bot_id}/dreaming/run/{run_id}/items`

V1 may simplify delete semantics to "delete promoted items from latest run" if full historical selective deletion is too wide for the first cut.

## UI integration

Integrate in the Memory page first, not as a separate app section.

Add:

- dreaming status card
- latest report summary
- run now button
- doctor button
- latest promoted items list
- delete latest promoted items action

Config editing can live under existing memory settings as `memory.dreaming`.

## Boundaries

### What dreaming owns

- orchestration
- status/report persistence
- user-readable explanation
- correction workflow entrypoint

### What dreaming does not own

- main chat prompt assembly
- raw working memory ingestion
- existing long-term truth schema ownership
- relationship rendering inside live chat generation

## Testing

Add:

- unit tests for orchestrator run lifecycle
- unit tests for command parsing and replies
- unit tests for config admin roundtrip
- regression tests for latest report/status admin endpoints
- UI build verification after type and page updates

## Implementation preference

Land in this order:

1. dreaming data store and orchestrator
2. memory engine exposure
3. gateway command support
4. admin endpoints
5. settings roundtrip
6. memory page UI
7. tests and build verification
