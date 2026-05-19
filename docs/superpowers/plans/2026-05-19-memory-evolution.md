# Memory Evolution Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Upgrade memory so the bot writes durable memories with evidence, carries same-day continuity across sessions and channels, and uses intent-aware retrieval plus hierarchical rollups instead of flattening everything into one prompt block.

**Architecture:** Keep the existing memory engine and store layout, but make each layer more explicit. Working memory remains session-scoped. Daily memory becomes the short-lived continuity bridge. Episodic memory remains shared-experience storage. Semantic memory remains stable fact storage. Relationship and user-understanding keep owning durable personalization. Add provenance on extracted items, tighten governor decisions, enrich daily retrieval, and introduce lightweight rollup summaries that sit above raw fragments. The result should make memory more explainable, more stable, and less noisy without replacing the current engine.

**Tech Stack:** Python 3.11, SQLite, Chroma embeddings already used by episodic memory, current `ai_companion.memory` modules, current unittest-based tests under `tests/`, and existing runtime storage under `data/bots/{bot_id}/memory/`.

---

## Scope Boundaries

This plan deliberately does **not** rewrite the whole memory system or import a separate tree pipeline.

In this phase we will:
- add evidence/provenance to extracted memories
- make daily continuity more visible and queryable
- improve retrieval budgeting and layer ordering
- preserve manual understanding over weak auto-extraction
- add a first lightweight rollup path for recurring themes

We will **not**:
- replace the existing bot runtime
- redesign gateway delivery
- build a new full tree pipeline like OpenHuman
- change persona generation beyond what memory retrieval needs

## File Structure

Create:
- `ai_companion/memory/stores/memory_rollup.py`: lightweight rollup store for day/topic/global summaries
- `tests/memory_evolution_test.py`: focused coverage for provenance, retrieval intent, rollups, and continuity

Modify:
- `ai_companion/memory/extractor.py`: emit provenance-rich candidates and stronger relationship / episode metadata
- `ai_companion/memory/governor.py`: enforce evidence, expiry, and manual-vs-auto precedence more explicitly
- `ai_companion/memory/stores/daily.py`: expose richer daily continuity data and summary candidates
- `ai_companion/memory/stores/semantic.py`: persist source metadata and confidence fields for facts
- `ai_companion/memory/stores/episodic.py`: persist richer episode metadata and recall cues
- `ai_companion/memory/stores/relationship.py`: keep stability, expose more structured state for retrieval
- `ai_companion/memory/stores/user_understanding.py`: keep manual overrides authoritative and expose layer summaries cleanly
- `ai_companion/memory/retriever.py`: make retrieval more intent-aware and rollup-aware
- `ai_companion/memory/prompt_builder.py`: budget prompt layers around the revised retrieval shape
- `ai_companion/memory/conscious.py`: surface the most relevant memory candidates more intentionally
- `ai_companion/memory/engine.py`: wire the new rollup store, enrich turn contexts, and report diagnostics
- `tests/daily_memory_test.py`: add integration coverage for the improved continuity path
- `tests/system_test_suite.py`: add one end-to-end memory continuity regression

## Data Model

Use the existing schema where possible, but extend it so memory rows can answer:
- where did this come from
- why was it kept
- how stable is it
- when should it fade

For new rollup summaries, store:
- scope: `day`, `topic`, or `global`
- source keys or related entity keys
- summary text
- supporting evidence ids
- confidence / freshness
- created_at / updated_at

## Task 1: Add Provenance To Memory Candidates

**Files:**
- Modify: `ai_companion/memory/extractor.py`
- Modify: `ai_companion/memory/governor.py`
- Test: `tests/memory_evolution_test.py`

- [ ] **Step 1: Write the failing tests**

Add tests that verify:
- a fact candidate keeps evidence from the source turn
- an episode candidate carries summary, cue tags, and sensitivity
- a relationship candidate does not overwrite stable state on weak evidence
- a manual understanding key blocks auto-write for the same concept

- [ ] **Step 2: Run the tests and confirm failure**

Run:

```bash
python -m pytest tests/memory_evolution_test.py -q
```

Expected: missing candidate metadata handling or governor precedence failures.

- [ ] **Step 3: Implement provenance-preserving extraction**

Update `MemoryCandidate` production so the extractor attaches:
- source session/turn evidence
- confidence and importance for every candidate
- episode cue tags for later recall
- stable relationship metadata with hysteresis-friendly signals

Make governor decisions reject weak or conflicting candidates before they hit durable stores.

- [ ] **Step 4: Re-run the tests**

Run:

```bash
python -m pytest tests/memory_evolution_test.py -q
```

Expected: pass.

## Task 2: Make Daily Memory A First-Class Continuity Layer

**Files:**
- Modify: `ai_companion/memory/stores/daily.py`
- Modify: `ai_companion/memory/retriever.py`
- Modify: `ai_companion/memory/prompt_builder.py`
- Test: `tests/daily_memory_test.py`

- [ ] **Step 1: Write the failing tests**

Add coverage for:
- same-day context appears in retrieval for a later session
- open threads and commitments surface before long-term episodic fragments
- daily summaries are intent-sensitive and stay compact

- [ ] **Step 2: Run the tests and confirm failure**

Run:

```bash
python -m pytest tests/daily_memory_test.py -q
```

Expected: daily context either missing from retrieval or over-budget in prompt assembly.

- [ ] **Step 3: Implement richer daily retrieval**

Expose structured daily context with:
- recent messages
- daily summary blocks
- open threads
- commitments
- mood / state hints

Make prompt assembly prefer this layer for planning, emotional support, and follow-up continuity.

- [ ] **Step 4: Re-run the tests**

Run:

```bash
python -m pytest tests/daily_memory_test.py -q
```

Expected: pass.

## Task 3: Add Lightweight Rollups

**Files:**
- Create: `ai_companion/memory/stores/memory_rollup.py`
- Modify: `ai_companion/memory/engine.py`
- Modify: `ai_companion/memory/retriever.py`
- Test: `tests/memory_evolution_test.py`

- [ ] **Step 1: Write the failing tests**

Add coverage for:
- a rollup summary can be created from approved memories
- rollups are retrievable by scope
- rollups do not replace raw memories, they summarize them

- [ ] **Step 2: Run the tests and confirm failure**

Run:

```bash
python -m pytest tests/memory_evolution_test.py -q
```

- [ ] **Step 3: Implement the rollup store**

Create a minimal SQLite-backed rollup table and a small API to:
- append rollups
- fetch by scope
- fetch latest by topic or day

Wire it into `MemoryEngine` and retrieval as an additional, lower-priority layer.

- [ ] **Step 4: Re-run the tests**

Run:

```bash
python -m pytest tests/memory_evolution_test.py -q
```

Expected: pass.

## Task 4: Tighten Prompt Budgeting And Conscious Activation

**Files:**
- Modify: `ai_companion/memory/prompt_builder.py`
- Modify: `ai_companion/memory/conscious.py`
- Modify: `ai_companion/memory/engine.py`
- Test: `tests/memory_evolution_test.py`

- [ ] **Step 1: Write the failing tests**

Add coverage for:
- task help gets less episodic noise and more semantic/understanding weight
- relationship repair gets relationship and daily continuity first
- recall-past gets more episodic and rollup context

- [ ] **Step 2: Run the tests and confirm failure**

Run:

```bash
python -m pytest tests/memory_evolution_test.py -q
```

- [ ] **Step 3: Implement intent-aware budgets**

Tune prompt block ordering and budgets so the prompt gets:
- the relevant memory layer first
- a small conscious working set
- only the strongest supporting background

- [ ] **Step 4: Re-run the tests**

Run:

```bash
python -m pytest tests/memory_evolution_test.py -q
```

Expected: pass.

## Task 5: Verify End-To-End Memory Continuity

**Files:**
- Modify: `tests/system_test_suite.py`
- Modify: `tests/daily_memory_test.py`
- Modify: `tests/memory_evolution_test.py`

- [ ] **Step 1: Write the regression test**

Cover a sequence where:
- the bot learns a fact
- the same user returns later the same day from another channel or session
- retrieval carries forward the daily context and stable fact
- manual understanding still wins if the user corrects it

- [ ] **Step 2: Run the system test**

Run:

```bash
python tests/system_test_suite.py
```

- [ ] **Step 3: Fix any regressions**

Adjust extraction, retrieval, or prompt budgeting until the system test passes.

- [ ] **Step 4: Run the full memory test slice**

Run:

```bash
python -m pytest tests/daily_memory_test.py tests/memory_evolution_test.py -q
```

Expected: pass.

## Bot-Level Outcome

After this plan is implemented, the bot should behave like this:
- it remembers because something happened, not because it was mentioned once
- it keeps the thread of a day alive even if the user changes session or channel
- it stops overreacting to one-off emotion or one weak turn
- it can tell the difference between a stable fact, a recent state, and a durable relationship pattern
- it becomes easier to trust because the memory is structured, explainable, and editable

