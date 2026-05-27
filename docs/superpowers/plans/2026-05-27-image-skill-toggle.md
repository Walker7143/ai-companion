# Image Skill Toggle Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add independent WebUI enable toggles for image understanding and image generation so disabling either prevents both auto-routing and explicit `/skill` execution.

**Architecture:** Expose each image skill's `enabled` field through the admin config API, preserve it in the simplified UI skill payload, and enforce disable checks in explicit skill command execution using runtime capability state. Keep existing global-plus-bot config merge behavior and do not clear saved API settings when toggles are off.

**Tech Stack:** Python 3.11, React 19, TypeScript, unittest

---

### Task 1: Backend skill config exposure and command enforcement

**Files:**
- Modify: `ai_companion/gateway/admin_services.py`
- Modify: `ai_companion/skill/command.py`
- Test: `tests/bot_instance_test.py`
- Test: `tests/image_understanding_flow_test.py`

- [ ] Preserve and publish `enabled` for simplified image skills, then reject explicit `/skill image_generation` and `/skill image_understanding` when runtime capability says disabled or unavailable.

### Task 2: WebUI toggle persistence

**Files:**
- Modify: `ai-companion-ui/src/pages/Settings/Settings.tsx`
- Modify: `ai-companion-ui/src/types/index.ts`

- [ ] Add independent toggles for both image skill cards and keep `enabled` in the simplified skill payload written back to the admin API.

### Task 3: Verification

**Files:**
- Test: `tests/bot_instance_test.py`
- Test: `tests/image_understanding_flow_test.py`

- [ ] Run targeted Python tests plus a frontend build to verify the toggles save and the disable logic blocks both auto-routing and explicit skill commands.
