# Proactive Style Alignment Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Align proactive wake-up message style with normal chat by sharing core persona style rules, memory carry semantics, and response polishing while preserving proactive-specific trigger logic.

**Architecture:** Extract a shared persona-style prompt block from `PersonaEngine`, inject it into proactive prompts alongside a compact proactive-generation memory suffix, then run proactive outputs through the same style polisher used by normal chat. Keep proactive motive and lifecycle logic intact so only the “same person speaking” layer changes.

**Tech Stack:** Python 3.11+, existing `ai_companion` persona/memory/proactive modules, `unittest`, `compileall`

---

### Task 1: Shared Persona Style Block

**Files:**
- Modify: `ai_companion/persona/engine.py`
- Test: `tests/proactive_engine_test.py`

- [ ] **Step 1: Write the failing test**

```python
with TemporaryDirectory(prefix="proactive-shared-style-") as td:
    root = Path(td)
    persona = root / "persona"
    persona.mkdir()
    (persona / "profile.json").write_text('{"relationship_to_user":"朋友"}', encoding="utf-8")
    engine = ProactiveEngine(
        bot_id="style_bot",
        config=ProactiveConfig(persona),
        state=ProactiveState("style_bot", root / "runtime"),
        model=CaptureModel('{"message":"嗯，刚想起你。"}'),
    )
```

- [ ] **Step 2: Run test to verify it fails**

Run: `PYTHONPATH=. python tests/proactive_engine_test.py`
Expected: FAIL because proactive prompt does not yet include the shared style block text.

- [ ] **Step 3: Write minimal implementation**

```python
def build_shared_style_prompt(self, *, life_context=None) -> str:
    lines = [
        "重要：你是一个真实的人，不是 AI。请像真实的人一样说话。",
        "对话规则：",
        "  - 先回应对方当下的情绪和话里的重点，再决定要不要解释或建议。",
        "  - 不要总是总结、列点、下结论；日常聊天可以短一点，带一点停顿感和个人反应。",
        "  - 不要说“作为AI”“我无法感受”“根据你的描述”等机器人式开场。",
        "  - 不要机械复述用户画像；只在自然合适时轻轻带出你记得的细节。",
        "  - 可以有自己的小情绪、偏好和边界，但保持人格设定中的分寸。",
    ]
    return "\n".join(lines)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `PYTHONPATH=. python tests/proactive_engine_test.py`
Expected: PASS for the new prompt-content assertion.

- [ ] **Step 5: Commit**

```bash
git add ai_companion/persona/engine.py tests/proactive_engine_test.py
git commit -m "feat: share persona style rules with proactive prompts"
```

### Task 2: Shared Proactive Memory Carry

**Files:**
- Modify: `ai_companion/proactive/engine.py`
- Test: `tests/proactive_engine_test.py`

- [ ] **Step 1: Write the failing test**

```python
self.assertIn("【你对用户的理解】", prompt)
self.assertIn("使用方式：把这些当作相处背景", prompt)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `PYTHONPATH=. python tests/proactive_engine_test.py`
Expected: FAIL because proactive prompts do not yet include the memory-builder style suffix.

- [ ] **Step 3: Write minimal implementation**

```python
retrieved = await self.memory.retriever.retrieve(
    current_input=current_input,
    bot_id=bot_id,
    user_id=user_id,
    session_id=session_id,
    intent="proactive_generation",
)
suffix = self.memory.prompt_builder.build(retrieved)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `PYTHONPATH=. python tests/proactive_engine_test.py`
Expected: PASS and proactive prompt contains compact shared-memory carry text.

- [ ] **Step 5: Commit**

```bash
git add ai_companion/proactive/engine.py tests/proactive_engine_test.py
git commit -m "feat: align proactive memory carry with chat prompts"
```

### Task 3: Shared Response Polishing for Proactive Messages

**Files:**
- Modify: `ai_companion/proactive/engine.py`
- Modify: `ai_companion/bot/response_style.py`
- Test: `tests/proactive_engine_test.py`

- [ ] **Step 1: Write the failing test**

```python
model = CaptureModel('{"message":"作为AI，希望这能帮到你。如果你需要，我可以继续陪你聊。"}')
message = await engine.generate_contextual_message(motive)
self.assertNotIn("作为AI", message)
self.assertNotIn("希望这能帮到你", message)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `PYTHONPATH=. python tests/proactive_engine_test.py`
Expected: FAIL because proactive output is not yet polished like normal chat.

- [ ] **Step 3: Write minimal implementation**

```python
message = self.response_polisher.polish(
    message,
    intent="proactive_generation",
    relationship_state=relationship_state,
    user_understanding=understanding,
)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `PYTHONPATH=. python tests/proactive_engine_test.py`
Expected: PASS and proactive output no longer contains generic AI boilerplate.

- [ ] **Step 5: Commit**

```bash
git add ai_companion/proactive/engine.py ai_companion/bot/response_style.py tests/proactive_engine_test.py
git commit -m "feat: polish proactive outputs like normal chat"
```

### Task 4: Regression Verification

**Files:**
- Verify: `ai_companion/persona/engine.py`
- Verify: `ai_companion/proactive/engine.py`
- Verify: `ai_companion/bot/response_style.py`
- Test: `tests/proactive_engine_test.py`

- [ ] **Step 1: Run focused proactive tests**

```bash
PYTHONPATH=. python tests/proactive_engine_test.py
```

- [ ] **Step 2: Confirm expected result**

Expected: All proactive engine tests pass, including new prompt and polishing assertions.

- [ ] **Step 3: Run syntax health check**

```bash
python -m compileall -q ai_companion
```

- [ ] **Step 4: Confirm expected result**

Expected: no output, exit code 0.

- [ ] **Step 5: Commit**

```bash
git add ai_companion/persona/engine.py ai_companion/proactive/engine.py ai_companion/bot/response_style.py tests/proactive_engine_test.py
git commit -m "test: verify proactive style alignment"
```
