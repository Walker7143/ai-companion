# Vector Memory Architecture

## Goal

Move bot knowledge toward a semantic recall model without making the vector
database the only source of truth. The system should be able to recall:

- user facts and preferences;
- the richer user-understanding dossier;
- relationship-relevant observations;
- bot life events and major life events;
- existing episodic memories.

SQLite and JSON remain authoritative for exact state, editing, deletion,
scheduler ticks, relationship scores, and configuration. Chroma is a recall
index built from those sources.

## Why Not Vector-Only

Vector stores are excellent for "what is related to this?" but weak for:

- exact state reads such as current date, score, cooldown, and tick time;
- deterministic updates and deletes by key;
- user/admin editing workflows;
- migration and conflict handling;
- field-level validation.

For this project, `LifeState`, `RelationshipStore`, `SemanticStore`, and
`UserUnderstandingStore` all contain exact state. Replacing them with only
vectors would make the bot less predictable. The safer design is a hybrid:
structured stores own truth, vectors provide associative recall.

## Data Model

Use a single Chroma collection named `unified_memory`.

Each vector document has:

- `id`: stable id, derived from `source_type`, `bot_id`, `user_id`, and source id.
- `document`: compact text used for embedding and prompt recall.
- `metadata`:
  - `source_type`: `semantic_fact`, `user_understanding`, `life_event`,
    `major_life_event`, `daily_summary`, `relationship_narrative`,
    `life_journal`, or future types.
  - `source_id`: fact key, event id, or section path.
  - `bot_id`
  - `user_id`
  - `category`
  - `importance`
  - `sensitivity`
  - `created_at`
  - `updated_at`
  - `archived`

## First Implementation Phase

1. Add `VectorMemoryStore`
   - Uses the same embedding settings as `EpisodicStore`.
   - Lazily loads Chroma and sentence-transformers.
   - Fails soft when embeddings are disabled or unavailable.
   - Supports `upsert`, `delete`, `search`, and lightweight status.

2. Index authoritative sources
   - `SemanticStore.set_fact` upserts one `semantic_fact`.
   - `SemanticStore.delete_fact` removes matching vector fact entries.
   - `UserUnderstandingStore` is indexed after maintenance refresh and engine init.
   - `DailyMemoryStore` summaries are indexed as `daily_summary`.
   - `RelationshipStore` narrative/posture/guidance are indexed as
     `relationship_narrative`.
   - `LifeState` exposes recent and major life events for indexing from the bot.

3. Retrieve unified memories
   - `MemoryRetriever` queries `VectorMemoryStore`.
   - Results are filtered by `bot_id`, `user_id`, `source_type`, and archived state.
   - Existing semantic/episodic retrieval remains in place.
   - Unified results are additive and deduped by source.

4. Prompt integration
   - Add a compact block for associative memories.
   - Keep wording soft: these are related context, not facts to recite.
   - Sensitive items only surface in emotional support, repair, or explicit recall.

5. Backfill
   - On `MemoryEngine.init`, index current semantic facts and user understanding.
   - Bot startup can index current life state after `LifeState` exists.
   - A future CLI migration command can scan all bots.

## Later Phases

- Add admin UI visibility for vector index diagnostics beyond count/size.
- Unify episodic Chroma and unified Chroma if operationally useful.
- Add per-source freshness scoring and decay.
- Add explicit "why recalled" diagnostics to memory status.

## Risks

- Duplicate prompt context if semantic and vector recall return the same fact.
  Mitigation: dedupe by `source_type/source_id` and skip facts already rendered.
- Embedding model load cost.
  Mitigation: lazy load and keep `embedding: none` fallback.
- Chroma metadata filtering limitations.
  Mitigation: use simple scalar metadata only.
- Stale vectors after manual JSON edits.
  Mitigation: re-index user understanding on init and after maintenance.

## Acceptance Criteria

- Existing memory behavior still works with `embedding: none`.
- With embeddings enabled, semantic facts and user understanding are present in
  unified recall.
- Life events can be indexed without making LifeState depend on Chroma.
- `python -m compileall -q ai_companion` passes.
- System tests remain compatible with existing SQLite/JSON stores.
