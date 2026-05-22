# Memory System Convergence Architecture Design

## Goal

Turn the current memory feature set into a clearer system architecture without replacing the existing memory core. The design goal is to reduce concept overlap between memory truth, derived read models, productized operations, and explainability surfaces.

This document is not a rewrite proposal for the whole memory engine. It is a convergence design: keep the current capabilities, make the boundaries explicit, and define where future work must land.

## Problem Statement

The current system is technically rich but conceptually crowded.

Today the following concepts are all visible at the same product level:

- Working
- Daily
- Semantic
- Relationship
- Episodic
- UserUnderstanding
- Vector Index
- Rollup
- ConsciousContext
- Dreaming
- Memory Trust View
- Doctor

They do not all play the same role, but users and developers can easily experience them as parallel "memory systems".

The core problem is not broken storage. The core problem is missing product and architecture stratification.

## Design Principle

The system should be described and evolved through four explicit layers:

1. Memory Authority Layer
2. Derived Projection and Retrieval Layer
3. Memory Operations Layer
4. Explainability Layer

Every current and future memory-related capability must belong to one of these layers.

## Layer Model

### 1. Memory Authority Layer

These modules own the canonical persisted state:

- `WorkingMemoryStore`
- `DailyMemoryStore`
- `SemanticStore`
- `RelationshipStore`
- `EpisodicStore`

Rules:

- all durable facts must resolve back to this layer
- no new product feature may create a second durable truth source
- user-facing reports may reference these stores but must not silently replace them

### 2. Derived Projection and Retrieval Layer

These modules exist to transform memory authority into more usable read forms:

- `UserUnderstandingStore`
- `VectorMemoryStore`
- `MemoryRollupStore`
- `ConsciousContextBuilder`
- `MemoryPromptBuilder`
- parts of `MemoryRetriever`

Rules:

- these layers may be rebuilt from authority
- they may shape retrieval and prompt context
- they must be documented as projections/read models, not as independent truth sources

### 3. Memory Operations Layer

These modules perform operations around memory:

- `MemoryGovernor`
- `MemoryMaintenance`
- `DreamingOrchestrator`
- vector rebuild entrypoints
- doctor entrypoints

Rules:

- `MemoryGovernor` decides whether a candidate becomes durable state
- `MemoryMaintenance` performs low-noise background housekeeping
- `DreamingOrchestrator` performs user-facing organization tasks
- doctor/rebuild operations do not own truth; they inspect or refresh it

### 4. Explainability Layer

These surfaces explain the state or behavior of memory:

- `memory_trust_view`
- `dreaming_report`
- `memory_prompt_diagnostics`
- admin debug context

Rules:

- this layer does not create new memory
- it explains current state or recent operations
- status views and event reports must remain separate concerns

## Core Architecture Decisions

### Decision 1: Keep truth in structured stores

Do not move authority into markdown files, dreaming reports, or user-facing explanation documents.

Canonical truth stays in:

- `semantic.db`
- `relationship.db`
- `episodic.db`
- `working.db`
- `daily.db`

`user_understanding.json` remains a durable projection and user-editable overlay, not the only truth source.

### Decision 2: Reframe UserUnderstanding as a projection

`UserUnderstandingStore` should be treated as:

- editable projection for humans
- prompt-oriented layered read model
- correction entrypoint

It should not be presented as a full duplicate of semantic memory.

This resolves the biggest conceptual confusion in the current system.

### Decision 3: Reframe Vector Memory as an index

`VectorMemoryStore` should be described and surfaced as a unified semantic recall index.

Implications:

- admin UI should favor "向量索引" instead of "向量记忆"
- rebuild actions should clearly state that they refresh an index, not raw memory
- error handling should separate "authority intact but index stale" from actual data loss

### Decision 4: Dreaming is a productized operation, not a new memory layer

`DreamingOrchestrator` is explicitly part of the operations layer.

It:

- collects candidates from existing layers
- decides and persists promotions through existing stores
- emits reports and status
- supports user-facing correction hooks

It does not:

- own a parallel long-term truth source
- replace semantic or episodic persistence
- define prompt assembly logic

### Decision 5: Trust View and Dreaming Report must not merge

They solve different questions:

- `Trust View`: what the system currently holds with what confidence
- `Dreaming Report`: what one organization run just did

They may live near each other in the UI, but they must remain distinct data products.

## Existing Code Mapping

### Authority

- `ai_companion/memory/stores/working.py`
- `ai_companion/memory/stores/daily.py`
- `ai_companion/memory/stores/semantic.py`
- `ai_companion/memory/stores/relationship.py`
- `ai_companion/memory/stores/episodic.py`

### Derived

- `ai_companion/memory/stores/user_understanding.py`
- `ai_companion/memory/stores/vector.py`
- `ai_companion/memory/stores/memory_rollup.py`
- `ai_companion/memory/conscious.py`
- `ai_companion/memory/prompt_builder.py`
- `ai_companion/memory/retriever.py`

### Operations

- `ai_companion/memory/governor.py`
- `ai_companion/memory/maintenance.py`
- `ai_companion/memory/dreaming.py`
- `ai_companion/main.py` vector rebuild entrypoints

### Explainability

- `MemoryEngine.get_memory_status()`
- `memory_trust_view`
- `dreaming status/report`
- admin memory and debug endpoints

## Runtime Data Flow

### Main chat flow

1. user turn enters
2. working and daily record the raw turn
3. extractor creates candidates
4. governor writes durable changes
5. retriever selects relevant memory by intent
6. conscious context activates a small set of memories
7. prompt builder converts retrieved memory into bounded prompt context

### Maintenance flow

1. periodic or light-turn trigger
2. decay/archive/rebuild projection/rollup/index actions
3. no user-facing report required

### Dreaming flow

1. user or admin or future scheduler triggers dreaming
2. orchestrator collects candidates from authority/projection layers
3. dreaming promotion governor classifies candidates
4. persistence facade writes approved changes through authority and projection entrypoints
5. report builder creates a user report and debug report
6. run store persists the event

### Explainability flow

1. status view reads authority and projections
2. trust view summarizes durable memory confidence and lifecycle
3. dreaming report explains a run event
4. prompt diagnostics explain one generation context

## Key Boundary Contracts

### Contract A: Authority before projection

Any projection or index must be refreshable from authority.

### Contract B: Product operations must not bypass core policy

Dreaming or admin actions should not bypass semantic/relationship/understanding governance rules when writing state.

### Contract C: Event views and state views stay separate

- event views are time-bound
- state views are current snapshots

### Contract D: New memory features require layer placement

Before adding any new memory-related feature, answer:

- Is it authority?
- Is it a derived projection?
- Is it an operation?
- Is it an explainability surface?

If it does not clearly fit one layer, the design is not ready.

## UI / Product Architecture Implication

The Memory page should evolve toward four product sections:

1. Current and Short-Term
   - working
   - daily

2. Long-Term and Relationship
   - semantic
   - episodic
   - relationship
   - user understanding

3. Projection and Index
   - vector index
   - rollups
   - prompt diagnostics

4. Organization and Explainability
   - dreaming
   - trust view
   - doctor

This is an information architecture decision, not merely a styling decision.

## Risks If No Convergence Work Happens

1. Dreaming, maintenance, and trust features keep growing independently.
2. UserUnderstanding continues to be perceived as a second truth store.
3. Vector rebuild gets mistaken for raw memory recovery.
4. Future automatic dreaming execution lands before operational boundaries are stable.
5. More features increase the system's explanatory burden faster than its usability.

## Recommended Rollout

### Phase 1: Concept Convergence

- update docs
- update terminology
- make layer model explicit

### Phase 2: UI and Entry Convergence

- reorganize memory page information architecture
- keep `/memory`, `/dream`, and doctor semantics distinct

### Phase 3: Operational Boundary Hardening

- formalize dreaming vs maintenance behavior
- define future auto-run triggers only after those boundaries are stable

### Phase 4: Scheduled Dreaming

- add automatic execution through one explicit scheduler path
- ensure it reuses the operations layer rather than creating a side system

## Architectural Summary

The current memory system is not chaotic at the storage level.

It is conceptually overloaded because:

- truth
- projection
- operation
- explanation

are not yet presented as different classes of capability.

The correct next move is convergence, not replacement.
