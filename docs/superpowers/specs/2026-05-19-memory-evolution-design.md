# Memory Evolution Design

**Goal:** Make the bot remember with evidence, keep same-day continuity across sessions and channels, and turn long-term memory into structured, retrievable background instead of a pile of raw fragments.

**Architecture:** Keep the current memory stack, but tighten the contract between extraction, storage, retrieval, and prompt assembly. Working memory stays session-scoped. Daily memory becomes the short-term continuity bridge. Episodic memory holds significant shared experiences. Semantic memory holds stable facts. Relationship state and user-understanding remain the durable personalization layer. On top of that, add provenance, conflict handling, and hierarchical rollups so memory can be inspected, corrected, and reused without stuffing everything into the prompt.

**Tech Stack:** Python 3.11, SQLite, existing Chroma embeddings, current `ai_companion.memory` modules, current test suite, and existing config/runtime storage under `data/bots/{bot_id}/memory/`.

---

## What Changes

The current system already has the right layers, but they are not yet behaving like one connected memory organism.

Today:
- working memory keeps the current session alive
- daily memory tracks short-lived continuity
- episodic memory stores notable scenes
- semantic memory stores facts
- relationship state tracks closeness and tension
- user-understanding stores editable long-term background

After this change:
- every durable memory has evidence and context
- the bot can continue a topic across days without rereading the whole chat log
- retrieval chooses the right layer based on intent instead of dumping all memory into the prompt
- long-term memory can be summarized into higher-level rollups instead of remaining only at the fragment level
- users can correct memory without fighting the automatic layer

## Core Design

### 1. Evidence-backed memory write

Every extracted memory candidate should carry:
- source turn or session reference
- bot_id and user_id
- confidence / importance
- optional expiration or decay
- relation to the original user message and bot reply

This lets the bot explain why it remembers something, and lets the governor reject weak guesses before they become durable state.

### 2. Daily continuity bridge

Daily memory becomes the short-term bridge between working memory and long-term memory.

It should answer:
- what happened today
- what topic is still open
- what emotional state or commitment carried forward
- whether the same issue appeared in another channel

This layer is not permanent memory. It is the bot’s “today context”, so the bot can stay coherent across restarts, platforms, and short gaps.

### 3. Intent-aware retrieval

Retrieval should not be one flat recall call.

The bot should inspect the user input and decide:
- whether the turn is casual chat, task help, planning, emotional support, or relationship repair
- which memory layers matter for that intent
- how much budget each layer gets in the prompt
- what should be active in consciousness versus merely queryable in the background

This is the biggest behavioral gain. The bot stops over-exposing memory and starts using it with judgment.

### 4. Hierarchical long-term summaries

OpenHuman’s tree idea is useful, but this project does not need its full generic pipeline.

Instead, build a lighter hierarchy:
- source or day summaries for local continuity
- topic rollups for recurring themes
- global rollups for the bot’s long-term understanding of the user and relationship

These rollups should be generated from already-approved memories, not directly from raw chat noise.

### 5. Maintenance and conflict control

Memory must decay, archive, and self-correct.

Rules:
- weak or contradictory facts should not overwrite stronger manual understanding
- old episodes should remain queryable but not always prompt-visible
- relationship changes should use hysteresis, not jump on single-turn mood swings
- user-edited understanding should win over auto-extracted guesses

## Bot Evolution

This design changes the bot in five visible ways:

1. It remembers with continuity, not just with fragments.
2. It becomes more stable across time, especially for relationships and recurring topics.
3. It starts following up instead of only replying.
4. It becomes explainable, because memory has provenance and structure.
5. It becomes safer to evolve, because memory can be corrected instead of silently drifting.

## Rollout Phases

### Phase 1: Memory Evidence and Retrieval Discipline

Add provenance to extracted memory candidates, tighten governor rules, and make prompt assembly respect intent-based budgets.

### Phase 2: Daily Continuity

Promote daily memory into a first-class cross-channel bridge and make it visible in retrieval diagnostics.

### Phase 3: Rollups

Add hierarchical summaries for recurring topics and long-running relationships so the bot can remember the shape of a story, not just the latest line.

### Phase 4: Maintenance

Add expiry, archive, conflict resolution, and user override paths that keep memory clean over time.

## Success Criteria

- The bot can answer a follow-up about something discussed earlier the same day without re-deriving it from scratch.
- The bot does not overwrite stable user understanding with low-confidence guesses.
- The bot uses less prompt space for irrelevant memory while keeping more useful context active.
- The bot can explain why a memory appears in context.
- Relationship state changes more slowly and more plausibly.

## Testing Strategy

- unit tests for extraction metadata and governor acceptance rules
- unit tests for daily continuity retrieval by intent
- unit tests for prompt assembly budgets and layer ordering
- regression tests for relationship stability and manual override precedence
- system tests for same-day continuity across multiple turns

