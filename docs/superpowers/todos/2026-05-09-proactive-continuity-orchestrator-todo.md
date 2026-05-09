# Proactive Continuity Orchestrator TODO

Source plan: `docs/superpowers/plans/2026-05-09-proactive-continuity-orchestrator.md`

Goal: replace timer-like proactive wakeups with motive-driven continuity behavior while keeping process ownership, delivery paths, and user controls explicit.

Checkpoint rule: implement one task at a time, run that task's verification, update this document, then ask for confirmation before moving to the next task.

## Current Checkpoint

- Status: Task 15 completed.
- Current task: final verification.
- Next gate: pause for user confirmation after Task 15.

## Task List

- [x] Task 1: Add motive and task models.
- [x] Task 2: Persist conversation tasks.
- [x] Task 3: Add continuity config.
- [x] Task 4: Detect delayed reply promises.
- [x] Task 5: Run conversation closeout analysis after Bot replies.
- [x] Task 6: Add context-aware message generation.
- [x] Task 7: Implement orchestrator and scheduler delegation.
- [x] Task 8: Ensure same-chat delivery for deferred motives.
- [x] Task 9: Add topic continuation candidate.
- [x] Task 10: Expose config through admin API.
- [x] Task 11: Add Web UI controls and explanations.
- [x] Task 12: Add runtime status and debug visibility.
- [x] Task 13: Add end-to-end system scenario.
- [x] Task 14: Documentation and user-facing explanation.
- [x] Task 15: Final verification.

## Task 1 Details

Files:

- Create: `ai_companion/proactive/motives.py`
- Create or modify: `tests/proactive_orchestrator_test.py`

Steps:

- [x] Write failing serialization roundtrip test.
- [x] Run `PYTHONPATH=. python tests/proactive_orchestrator_test.py` and confirm missing model module.
- [x] Implement `ConversationTask`, `ProactiveMotive`, and related enums.
- [x] Run `PYTHONPATH=. python tests/proactive_orchestrator_test.py` and confirm pass.
- [x] Update this TODO and report the checkpoint.

## Task 2 Details

Files:

- Create: `ai_companion/proactive/conversation_task_store.py`
- Modify: `tests/proactive_orchestrator_test.py`

Steps:

- [x] Write failing SQLite task-store test.
- [x] Run `PYTHONPATH=. python tests/proactive_orchestrator_test.py` and confirm missing store module.
- [x] Implement `ConversationTaskStore` with `upsert`, `list_due`, `mark_completed`, and `mark_expired`.
- [x] Run `PYTHONPATH=. python tests/proactive_orchestrator_test.py` and confirm pass.
- [x] Update this TODO and report the checkpoint.

## Task 3 Details

Files:

- Modify: `ai_companion/proactive/config.py`
- Modify: `tests/proactive_orchestrator_test.py`

Steps:

- [x] Write continuity defaults and override test.
- [x] Run `PYTHONPATH=. python tests/proactive_orchestrator_test.py` and confirm missing config properties.
- [x] Add `conversation_continuity` defaults and typed accessors.
- [x] Run `PYTHONPATH=. python tests/proactive_orchestrator_test.py` and confirm pass.
- [x] Update this TODO and report the checkpoint.

## Task 4 Details

Files:

- Create: `ai_companion/proactive/deferred_detector.py`
- Modify: `tests/proactive_orchestrator_test.py`

Steps:

- [x] Write delayed-reply detector tests.
- [x] Run `PYTHONPATH=. python tests/proactive_orchestrator_test.py` and confirm missing detector module.
- [x] Implement rule-based `DeferredReplyDetector`.
- [x] Run `PYTHONPATH=. python tests/proactive_orchestrator_test.py` and confirm pass.
- [x] Update this TODO and report the checkpoint.

## Task 5 Details

Files:

- Modify: `ai_companion/bot/instance.py`
- Modify: `tests/bot_instance_test.py`

Steps:

- [x] Inspect existing dirty changes in target files before editing.
- [x] Write BotInstance deferred-task recording test.
- [x] Run targeted test and confirm no task is recorded yet.
- [x] Wire `ConversationTaskStore` and closeout analysis after normal replies.
- [x] Run targeted BotInstance test and proactive orchestrator tests.
- [x] Update this TODO and report the checkpoint.

## Task 6 Details

Files:

- Modify: `ai_companion/proactive/engine.py`
- Modify: `tests/proactive_engine_test.py`

Steps:

- [x] Inspect existing proactive generation and fallback helpers.
- [x] Write context-aware message prompt test.
- [x] Run `PYTHONPATH=. python tests/proactive_engine_test.py` and confirm missing method.
- [x] Implement `generate_contextual_message` and `send_contextual_proactive_message`.
- [x] Run proactive engine and orchestrator tests.
- [x] Update this TODO and report the checkpoint.

## Task 7 Details

Files:

- Create: `ai_companion/proactive/orchestrator.py`
- Modify: `ai_companion/proactive/scheduler.py`
- Modify: `ai_companion/bot/instance.py`
- Modify: `tests/proactive_orchestrator_test.py`

Steps:

- [x] Write due deferred task dispatch test.
- [x] Run `PYTHONPATH=. python tests/proactive_orchestrator_test.py` and confirm missing orchestrator module.
- [x] Implement `ProactiveOrchestrator`.
- [x] Delegate scheduler `_tick()` to orchestrator when available.
- [x] Wire orchestrator in `BotInstance`.
- [x] Run proactive orchestrator, engine, and BotInstance targeted tests.
- [x] Update this TODO and report the checkpoint.

## Task 8 Details

Files:

- Modify: `ai_companion/proactive/engine.py`
- Modify: `ai_companion/bot/instance.py`
- Modify: `tests/proactive_orchestrator_test.py`

Steps:

- [x] Inspect current platform sender and gateway wrapper behavior.
- [x] Write target override delivery test.
- [x] Confirm from code inspection that target was not passed yet.
- [x] Pass motive target through contextual send to platform sender.
- [x] Teach `BotInstance._wrap_gateway_send` to honor explicit target metadata.
- [x] Run proactive orchestrator, engine, and BotInstance targeted tests.
- [x] Update this TODO and report the checkpoint.

## Task 9 Details

Files:

- Modify: `ai_companion/proactive/orchestrator.py`
- Modify: `tests/proactive_orchestrator_test.py`

Steps:

- [x] Read the planned topic continuation trigger behavior.
- [x] Write topic continuation candidate tests.
- [x] Run targeted tests and confirm no topic continuation task is created yet.
- [x] Implement topic continuation closeout detection and orchestrator motive selection.
- [x] Run proactive orchestrator, engine, and BotInstance targeted tests.
- [x] Update this TODO and report the checkpoint.

## Task 10 Details

Files:

- Modify: `ai_companion/gateway/admin_services.py`
- Modify: `tests/system_test_suite.py`

Steps:

- [x] Read the existing Web config schema and proactive save/load paths.
- [x] Add continuity fields to the proactive schema description.
- [x] Map flattened proactive continuity fields back into `conversation_continuity`.
- [x] Extend T36 to assert the new fields round-trip through the admin API.
- [x] Run the targeted T36 system case and confirm the new continuity fields persist.
- [x] Update this TODO and report the checkpoint.

## Task 11 Details

Files:

- Modify: `ai-companion-ui/src/types/index.ts`
- Modify: `ai-companion-ui/src/pages/Settings/Settings.tsx`

Steps:

- [x] Extend `ProactiveConfig` with flattened continuity fields.
- [x] Add default continuity values in Settings normalization.
- [x] Add warnings for disabling delayed-reply fulfillment or topic continuation while idle pings remain enabled.
- [x] Add proactive continuity controls and timing explanation in the proactive settings section.
- [x] Run `npm run build` in `ai-companion-ui`.
- [x] Update this TODO and report the checkpoint.

## Task 12 Details

Files:

- Modify: `ai_companion/proactive/conversation_task_store.py`
- Modify: `ai_companion/bot/instance.py`
- Modify: `ai_companion/gateway/admin_services.py`
- Modify: `tests/proactive_orchestrator_test.py`
- Modify: `tests/system_test_suite.py`

Steps:

- [x] Add `ConversationTaskStore.count_pending(bot_id)`.
- [x] Include pending conversation task count in `BotInstance.get_proactive_status()`.
- [x] Expose `proactive_status` through admin diagnostics.
- [x] Extend focused proactive store test and T36 Web config diagnostics assertions.
- [x] Run proactive orchestrator test, targeted T36 case, and compile checks.
- [x] Update this TODO and report the checkpoint.

## Task 13 Details

Files:

- Modify: `tests/system_test_suite.py`

Steps:

- [x] Add async system case for deferred-reply proactive continuity.
- [x] Register the new case as `T52`.
- [x] Verify the case records a due conversation task after a promised delayed reply.
- [x] Verify orchestrator dispatches the follow-up to the original chat target and completes the task.
- [x] Run the new system case and related proactive/BotInstance tests.
- [x] Update this TODO and report the checkpoint.

## Task 14 Details

Files:

- Modify: `docs/DESIGN_phase5_proactive.md`
- Modify: `docs/GUIDE.md`

Steps:

- [x] Add a new proactive continuity section to the phase 5 design doc.
- [x] Add a user-facing explanation section to the guide.
- [x] Run `python -m compileall -q ai_companion`.
- [x] Update this TODO and report the checkpoint.

## Task 15 Details

Files:

- Verify: `ai_companion/bot/instance.py`
- Verify: `ai_companion/proactive/config.py`
- Verify: `ai_companion/proactive/deferred_detector.py`
- Verify: `ai_companion/proactive/orchestrator.py`
- Verify: `ai_companion/proactive/engine.py`
- Verify: `ai_companion/proactive/scheduler.py`
- Verify: `ai_companion/proactive/conversation_task_store.py`
- Verify: `ai_companion/proactive/motives.py`
- Verify: `ai_companion/gateway/admin_services.py`
- Verify: `ai-companion-ui/src/pages/Settings/Settings.tsx`
- Verify: `ai-companion-ui/src/types/index.ts`
- Verify: `tests/bot_instance_test.py`
- Verify: `tests/proactive_engine_test.py`
- Verify: `tests/proactive_orchestrator_test.py`
- Verify: `tests/system_test_suite.py`

Steps:

- [x] Run focused proactive, BotInstance, and Weixin gateway tests under the bundled venv.
- [x] Run `python -m compileall -q ai_companion`.
- [x] Run `cd ai-companion-ui && npm run build`.
- [x] Fix the T52 system-case timing window so it uses the actual stored `due_at`.
- [x] Run `PYTHONPATH=. '/Users/wangxiaowei/.ai-companion/.venv/bin/python' tests/system_test_suite.py` and confirm `PASS: 59  FAIL: 0  ERROR: 0`.
- [x] Update this TODO and report the checkpoint.

## Verification Log

- 2026-05-09: `PYTHONPATH=. python tests/proactive_orchestrator_test.py` failed as expected before implementation with `ModuleNotFoundError: No module named 'ai_companion.proactive.motives'`.
- 2026-05-09: `PYTHONPATH=. python tests/proactive_orchestrator_test.py` passed after adding `ai_companion/proactive/motives.py`.
- 2026-05-09: `python -m compileall -q ai_companion/proactive/motives.py` passed.
- 2026-05-09: `PYTHONPATH=. python tests/proactive_orchestrator_test.py` failed as expected before Task 2 implementation with `ModuleNotFoundError: No module named 'ai_companion.proactive.conversation_task_store'`.
- 2026-05-09: `PYTHONPATH=. python tests/proactive_orchestrator_test.py` passed after adding `ai_companion/proactive/conversation_task_store.py`.
- 2026-05-09: `python -m compileall -q ai_companion/proactive/conversation_task_store.py ai_companion/proactive/motives.py` passed.
- 2026-05-09: `PYTHONPATH=. python tests/proactive_orchestrator_test.py` failed as expected before Task 3 implementation with `AttributeError: 'ProactiveConfig' object has no attribute 'continuity_enabled'`.
- 2026-05-09: `PYTHONPATH=. python tests/proactive_orchestrator_test.py` passed after adding `conversation_continuity` defaults and typed accessors.
- 2026-05-09: `python -m compileall -q ai_companion/proactive/config.py ai_companion/proactive/conversation_task_store.py ai_companion/proactive/motives.py` passed.
- 2026-05-09: `PYTHONPATH=. python tests/proactive_orchestrator_test.py` failed as expected before Task 4 implementation with `ModuleNotFoundError: No module named 'ai_companion.proactive.deferred_detector'`.
- 2026-05-09: `PYTHONPATH=. python tests/proactive_orchestrator_test.py` passed after adding `ai_companion/proactive/deferred_detector.py`.
- 2026-05-09: `python -m compileall -q ai_companion/proactive/deferred_detector.py ai_companion/proactive/config.py ai_companion/proactive/conversation_task_store.py ai_companion/proactive/motives.py` passed.
- 2026-05-09: `PYTHONPATH=. python tests/bot_instance_test.py -k deferred` failed as expected before Task 5 implementation with `AttributeError: 'BotInstance' object has no attribute 'conversation_task_store'`.
- 2026-05-09: `PYTHONPATH=. python tests/bot_instance_test.py -k deferred && PYTHONPATH=. python tests/proactive_orchestrator_test.py` passed after wiring closeout task recording.
- 2026-05-09: `python -m compileall -q ai_companion/bot/instance.py ai_companion/proactive/deferred_detector.py ai_companion/proactive/conversation_task_store.py ai_companion/proactive/config.py ai_companion/proactive/motives.py` passed.
- 2026-05-09: `PYTHONPATH=. python tests/proactive_engine_test.py` failed as expected before Task 6 implementation with `AttributeError: 'ProactiveEngine' object has no attribute 'generate_contextual_message'`.
- 2026-05-09: `PYTHONPATH=. python tests/proactive_engine_test.py && PYTHONPATH=. python tests/proactive_orchestrator_test.py` passed after adding contextual proactive generation.
- 2026-05-09: `python -m compileall -q ai_companion/proactive/engine.py ai_companion/proactive/motives.py` passed.
- 2026-05-09: `PYTHONPATH=. python tests/proactive_orchestrator_test.py` failed as expected before Task 7 implementation with `ModuleNotFoundError: No module named 'ai_companion.proactive.orchestrator'`.
- 2026-05-09: `PYTHONPATH=. python tests/proactive_orchestrator_test.py && PYTHONPATH=. python tests/proactive_engine_test.py && PYTHONPATH=. python tests/bot_instance_test.py -k deferred` passed after adding orchestrator and scheduler delegation.
- 2026-05-09: `python -m compileall -q ai_companion/proactive/orchestrator.py ai_companion/proactive/scheduler.py ai_companion/bot/instance.py ai_companion/proactive/engine.py` passed.
- 2026-05-09: `PYTHONPATH=. python tests/proactive_orchestrator_test.py` passed after adding same-chat target override coverage.
- 2026-05-09: `PYTHONPATH=. python tests/proactive_orchestrator_test.py && PYTHONPATH=. python tests/proactive_engine_test.py && PYTHONPATH=. python tests/bot_instance_test.py -k deferred` passed after passing motive targets through the contextual send path.
- 2026-05-09: `python -m compileall -q ai_companion/proactive/engine.py ai_companion/bot/instance.py ai_companion/proactive/orchestrator.py ai_companion/proactive/scheduler.py` passed.
- 2026-05-09: `'/Users/wangxiaowei/.cache/codex-runtimes/codex-primary-runtime/dependencies/python/bin/python3' -m pip install aiohttp pyyaml psutil` passed in the bundled runtime so the system test harness could import its dependencies.
- 2026-05-09: `'/Users/wangxiaowei/.cache/codex-runtimes/codex-primary-runtime/dependencies/python/bin/python3' - <<'PY' ... case_web_config_center_roundtrip()` passed after the admin API continuity mapping update.
- 2026-05-09: `cd ai-companion-ui && npm run build` passed after adding proactive continuity settings UI.
- 2026-05-09: `PYTHONPATH=. python tests/proactive_orchestrator_test.py` passed after adding pending task count.
- 2026-05-09: `'/Users/wangxiaowei/.cache/codex-runtimes/codex-primary-runtime/dependencies/python/bin/python3' - <<'PY' ... case_web_config_center_roundtrip()` passed after exposing `diagnostics.proactive_status`.
- 2026-05-09: `python -m compileall -q ai_companion/proactive/conversation_task_store.py ai_companion/bot/instance.py ai_companion/gateway/admin_services.py tests/system_test_suite.py tests/proactive_orchestrator_test.py` passed.
- 2026-05-09: `PYTHONPATH=. python - <<'PY' ... case_deferred_reply_proactive_continuity()` passed after adding the T52 system scenario.
- 2026-05-09: `PYTHONPATH=. python tests/bot_instance_test.py -k deferred` passed after adding the T52 scenario.
- 2026-05-09: `PYTHONPATH=. python tests/proactive_orchestrator_test.py` passed after adding the T52 scenario.
- 2026-05-09: `python -m compileall -q tests/system_test_suite.py ai_companion/bot/instance.py ai_companion/proactive/orchestrator.py ai_companion/proactive/engine.py` passed.
- 2026-05-09: `python -m compileall -q ai_companion` passed after the documentation update.
- 2026-05-09: `PYTHONPATH=. '/Users/wangxiaowei/.ai-companion/.venv/bin/python' tests/weixin_gateway_test.py` passed after making `_wrap_gateway_send` compatible with adapters that do not accept `metadata`.
- 2026-05-09: `PYTHONPATH=. '/Users/wangxiaowei/.ai-companion/.venv/bin/python' tests/bot_instance_test.py` passed.
- 2026-05-09: `cd ai-companion-ui && npm run build` passed.
- 2026-05-09: `PYTHONPATH=. '/Users/wangxiaowei/.ai-companion/.venv/bin/python' tests/system_test_suite.py` initially failed only on `T52 Deferred proactive continuity` with `due=[] pending_before=1 pending_after=1 sent=[]`.
- 2026-05-09: `PYTHONPATH=. '/Users/wangxiaowei/.ai-companion/.venv/bin/python' tests/system_test_suite.py` passed after aligning T52 to the stored `due_at` window.
- 2026-05-09: `python -m compileall -q tests/system_test_suite.py` passed after the T52 timing fix.

## Notes

- Runtime data must remain under `~/.ai-companion/data/bots/{bot_id}/`; tests should use temporary directories.
- Deferred reply delivery must preserve same platform/session/chat in later tasks.
- Existing proactive scheduler ownership and platform sender path should remain intact.
