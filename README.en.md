# AI Companion / AI 知己

Open-source AI companion product for macOS / Linux / Windows. Each bot has an independent personality and memory system, interacting with you like a real person.

## Key Features

| Feature | Description |
|---------|-------------|
| **Multi-Model Support** | MiniMax / OpenAI / Claude / MiMo / Ollama / Custom API |
| **Independent Personality** | Each bot has unique personality, backstory, and speaking style (tsundere / lively / gentle / aloof...) |
| **Intelligent Memory System** | Working memory + user model + relationship state + episodic memory + user understanding file + conscious workspace, recalled by intent and budget rather than mechanically stuffing context |
| **Local Vector Embedding** | sentence-transformers local vector semantic recall, Chinese-friendly |
| **Life Trajectory** | Each bot has an independent timeline, generating daily events, major life events, birthdays, and low-probability surprise events |
| **Proactive Messaging** | Proactively chats with you, reminds you of things, occasionally acts cute; based on LLM reasoning to judge timing, with proactive source metadata and self-memory to continue the same topic |
| **Token Budget Control** | Memory layers injected into prompt by intent block, with debug diagnostics output for easy token consumption tracking |
| **Relationship Evolution** | Bot behavior evolves based on interaction depth (stranger → lover) |
| **Personality-Based Refusal** | Decides whether to respond based on personality, not simple keyword filtering |
| **Multimedia Skills** | Image generation, voice synthesis |
| **Multi-Platform Gateway** | Local CLI / Feishu / Webhook, multiple message delivery methods |

---

## Quick Start

### Prerequisites

Before running the installation commands, make sure you have the following:

- **Python 3.11+**: Required for the backend and CLI tool.
- **Git**: The installation script will clone the project code.
- **Network connection**: Required to download Python dependencies, frontend dependencies, and project code.
- **A model source**: Any one of MiniMax / OpenAI / Claude / MiMo / Ollama / Custom API. Cloud models require an API Key; Ollama requires a running Ollama service on your machine.
- **Node.js + npm (recommended)**: Used to launch the admin web UI. You can skip this if you only want the CLI; install when you need the Web UI.

Dependencies are automatically handled by the installation scripts and `ai-companion setup`.

### Installation

**macOS / Linux (China users):**
```bash
curl -fsSL https://raw.githubusercontent.com/Walker7143/ai-companion/master/scripts/install-cn.sh | bash
```

**Windows (China users):**
```powershell
irm https://raw.githubusercontent.com/Walker7143/ai-companion/master/scripts/install-cn.ps1 -UseBasicParsing | iex
```

**Overseas users** please visit [GitHub Release](https://github.com/Walker7143/ai-companion/releases) to download the corresponding scripts.

### First-Time Configuration

```bash
source ~/.ai-companion/.venv/bin/activate  # If using a virtual environment
ai-companion setup
```

Running `setup` again will merge configuration updates: parts you choose not to reconfigure or overwrite will retain their old values. For example, changing only the model won't rewrite existing Bot, life trajectory, or proactive messaging configurations.

### Update

To update without reinstalling:

```bash
ai-companion update
```

For China network, you can use the Tsinghua PyPI mirror:

```bash
ai-companion update --cn
```

The update command preserves Bot configurations, memory, and logs under `~/.ai-companion/`. If the Gateway is running, it will be stopped first and automatically restarted after the update completes.

---

## Project Architecture

```
ai_companion/
├── bot/              # Bot core instances
│   ├── instance.py   # BotInstance - core runtime
│   └── manager.py    # BotManager - multi-bot management
├── memory/           # Memory system
│   ├── engine.py     # MemoryEngine - memory write, recall, maintenance coordination
│   ├── extractor.py  # MemoryExtractor - extract candidate memories from conversations
│   ├── governor.py   # MemoryGovernor - decide whether candidates are worth long-term storage
│   ├── retriever.py  # MemoryRetriever - plan recall based on current intent
│   ├── conscious.py  # ConsciousContext - current-turn conscious workspace
│   ├── prompt_builder.py  # MemoryPromptBuilder - build memory context
│   ├── maintenance.py     # MemoryMaintenance - expiry, archival, projection refresh
│   └── stores/
│       ├── working.py    # Working memory / raw message log
│       ├── episodic.py   # Episodic memory - important shared experiences
│       ├── semantic.py   # User model - structured user facts
│       ├── relationship.py       # Relationship state - affinity, intimacy, tension, key moments
│       └── user_understanding.py # User-editable understanding file
├── persona/          # Personality system
│   ├── loader.py     # PersonaLoader - personality loading
│   ├── engine.py     # PersonaEngine - System Prompt construction
│   └── refusal_engine.py  # Refusal engine - personality-based refusal
├── proactive/        # Proactive messaging system
│   ├── engine.py     # ProactiveEngine - LLM reasoning + message generation
│   ├── scheduler.py   # ProactiveScheduler - proactive messaging scheduled checks
│   ├── platform.py   # Platform adapters (CLI/Feishu/Webhook)
│   ├── life_engine.py     # LifeEngine - life trajectory event generation
│   ├── life_scheduler.py  # LifeScheduler - independent life trajectory scheduling
│   ├── life_config.py     # life.json config loading
│   └── life_state.py      # life_state.json state persistence
├── context/          # Context management
│   ├── compressor.py  # ContextCompressor - context compression
│   └── tokenizer.py   # TokenEstimator - token estimation
├── skill/            # Skill system
│   ├── dispatcher.py  # SkillDispatcher - skill dispatch
│   ├── registry.py    # SkillRegistry - skill registration
│   ├── image_gen.py   # Image generation skill
│   └── tts.py         # Voice synthesis skill
├── model/            # Model system
│   ├── factory.py    # ModelFactory - model factory
│   └── adapters/     # Model adapters
│       ├── base.py        # ModelAdapter abstract base class
│       ├── minimax_adapter.py  # MiniMax
│       ├── openai_adapter.py   # OpenAI GPT
│       ├── claude_adapter.py   # Anthropic Claude
│       ├── mimo_adapter.py     # Xiaomi MiMo
│       ├── ollama_adapter.py   # Ollama local
│       └── custom_adapter.py   # Custom HTTP API
├── gateway/          # Message gateway
│   ├── cmd.py        # Admin API + gateway entry
│   ├── control.py    # Gateway process management (start/stop)
│   └── platforms/    # Platform adapters
└── _vendor/          # Third-party libraries (vendored)
    └── gw_cli/       # Gateway CLI tool

ai-companion-ui/      # Admin web UI
├── src/
│   ├── pages/        # Pages (Dashboard/Session/Memory/Settings)
│   ├── stores/       # Zustand state management
│   └── api/          # Frontend API layer
└── vite.config.ts   # Vite build config
```

---

## Intelligent Memory System

The memory system doesn't simply "store more". It first judges what's worth remembering, then selects relevant memories based on the current conversation intent, and compresses the results into a small set of clues that can actually enter conscious awareness this turn. Complete memories are preserved, but the main model only sees the relevant, budgeted portion each turn.

```text
Current Conversation
  → Working/Raw Log saves original text and metadata
  → Extractor extracts candidate memories
  → Governor decides: write / skip / archive / refresh projection
  → User Model / Episodic / Relationship stored in layers
  → Retriever recalls by intent
  → ConsciousContextBuilder generates conscious workspace
  → PromptBuilder generates memory context with budget and diagnostics
```

### Memory Layers

| Layer | Storage | Description |
|-------|---------|-------------|
| Working / Raw Log | `working.db` | Current session original text, compressed summaries, debug ledger |
| Conscious / Workspace | Generated by `conscious.py`, not persisted | Compresses recall results into current focus, emotional reading, relationship stance, and a few active memories; only clues truly needed right now enter the prompt |
| User Model | `semantic.db` | Structured user facts with categories, confidence, sources, evidence, expiry |
| Relationship State | `relationship.db` | Relationship labels, affinity, intimacy, tension, key relationship moments between bot and user |
| Episodic Memory | `episodic.db` + optional Chroma | Important shared experiences, conflicts/resolutions, promises, life events; does not record ordinary small talk |
| Unified Vector Index | `vector/` + Chroma | Unified semantic recall index for semantic facts, user understanding, relationship narratives, daily summaries, and bot life trajectory; can be rebuilt anytime |
| Self / Autobiographical | Assistant messages with `assistant_initiated` in `daily.db` | What the bot proactively sent recently, why it sent it, how to follow up on user replies |
| User Understanding | `user_understanding.json` | User-editable "bot's understanding of me", split into `manual` and `auto` sections |

Long-term memories are fully preserved, but only the `ConsciousContext` compressed short snippet enters the main model each turn. `MemoryPromptBuilder` further allocates budget by intent, injecting `understanding`, `relationship`, `daily`, `self_memory`, `semantic`, and `episodic` in blocks, and records character counts, token estimates, truncation status, and total budget in `memory_prompt_diagnostics` for easy token debugging.

### User Understanding File

Each bot has a directly editable user understanding file:

```text
~/.ai-companion/data/bots/{bot_id}/memory/user_understanding.json
```

It is used for initializing and correcting the bot's understanding of the user:

- `manual`: Manually filled by the user, always takes priority; auto memories won't overwrite it.
- `auto`: Understanding formed by the system from daily conversations, relationship state, and bot reflections; auto-refreshes.
- Prompt prioritizes `manual`, then relevant `auto`.
- Built-in bots come with initial `manual`, so they have basic social awareness out of the box; `auto` refreshes with daily conversations.

Example:

```json
{
  "version": 3,
  "manual": {
    "summary": "The user wants to be treated gently but not dismissively.",
    "facts": {"nickname": "A-Chi"},
    "communication_style": ["Empathize first, then give advice"],
    "boundaries": ["Don't joke about weight"],
    "relationship_expectations": ["Wants the bot to accompany like someone who knows them well"]
  },
  "auto": {
    "profile_summary": "User has been under higher stress recently, needs to be heard first when feeling down.",
    "facts": {"city": "Shanghai"},
    "emotional_patterns": ["Tends to get anxious under stress but willing to keep pushing forward"],
    "comfort_strategies": ["Stay with them for a while, then give concrete suggestions"],
    "current_context": ["Recently working on a portfolio"],
    "open_threads": ["User wants to continue discussing the portfolio"]
  },
  "relationship_memory": {
    "what_user_seems_to_need_from_bot": ["Steady companionship, not mechanical advice"],
    "things_that_brought_them_closer": ["User started proactively sharing vulnerable moments"]
  }
}
```

### Dynamic Recall

The system first determines the current intent, then selects different memories:

| Intent | Priority Recall |
|--------|----------------|
| Emotional Support | Communication preferences, boundaries, recent stressors, relationship state |
| Reminiscing | Episodic memory first, cross-session if needed |
| Plan Progression | open_threads, goals, recent context |
| Relationship Repair | Relationship state, conflict/resolution episodes, boundaries |
| Task Request | Minimal necessary preferences, avoid irrelevant emotional memories |
| Proactive Messaging | open_threads, relationship state, recent user state, bot life trajectory |

### Unified Vector Memory Index

AI Companion uses a hybrid architecture where "structured databases are the source of truth, and Chroma is the semantic index". SQLite/JSON still stores editable, deletable, verifiable raw memories; Chroma only handles "what background would this sentence semantically associate with".

The unified vector index is generated from these authoritative sources:

- `semantic.db`: User facts, preferences, boundaries.
- `user_understanding.json`: `manual` / `auto` / `relationship_memory` projections from user understanding.
- `relationship.db`: Relationship narratives, current stance, interaction suggestions.
- `daily.db`: Recent summaries and open topics.
- Bot life trajectory: Daily events and major life events.

These are written to the Chroma collection `unified_memory` under `data/bots/{bot_id}/memory/vector/` as source types: `semantic_fact`, `user_understanding`, `relationship_narrative`, `daily_summary`, `life_event`, `major_life_event`, etc.

"Rebuilding vector index" only regenerates the Chroma search index; it does not delete or rewrite raw memories in SQLite/JSON. Useful when you've manually edited memory files, switched embedding models, or suspect the index is out of sync.

```yaml
# Enable local vector embedding
memory:
  embedding: "local"              # "local" | "none"
  embedding_model: "all-MiniLM-L6-v2"
```

Manual rebuild:

```bash
# Rebuild unified vector index for all enabled bots
ai-companion memory rebuild-vector

# Rebuild for a specific bot
ai-companion memory rebuild-vector --bot <bot_id>
```

You can also click "Rebuild Vector Index" on the "Memory" page in the admin UI. If the admin page is served from Vite dev port `5173`, make sure the gateway has been updated and restarted so the admin API CORS allows `http://localhost:5173`.

---

## Proactive Messaging System

### Trigger Mechanisms

- **Idle Trigger**: Bot proactively contacts the user after a period of inactivity
- **Emotion Trigger**: Delayed care when user messages contain specific emotional keywords
- **Gradient Silence**: Adjusts frequency based on time since last contact (7/14/30 day thresholds)
- **Life Topics**: Proactive messaging reasoning and message generation read the bot's current date, dynamic age, life stage, and recent shareable events

### Sending Platforms

| Platform | Config | Message Destination |
|----------|--------|---------------------|
| CLI | `platform.type: "cli"` | Terminal stdout |
| Feishu | `platform.type: "feishu"` | Feishu user/group |
| Webhook | `platform.type: "webhook"` | Custom HTTP endpoint |

### Rate Limiting

- Maximum daily proactive messages
- Minimum send interval
- Cooldown mechanism
- Anger degradation (reduced disturbance after user ignores multiple messages)

### Proactive Continuity

Proactive messages are now written to Working / Daily memory with `metadata.proactive=true`, `metadata.assistant_initiated=true`, and `proactive_kind`. This way, when the user replies, the bot knows the previous message was self-initiated and won't restart the conversation as if it never happened. `proactive_kind` distinguishes sources like `idle_reminder`, `deferred_reply`, `topic_continuation`, `emotion_followup`, `life_event`, etc. These enter the conscious workspace as `self_memory`, letting the bot remember "why I proactively reached out to you". Fallback messages are also more natural, no longer just a bare "Are you there?".

---

## Life Trajectory System

Bots have an independent life trajectory, running separately from the proactive messaging scheduler. Life trajectory state feeds into normal conversations, daily events, major life events, and proactive messaging prompts, preventing the bot from answering with static age after its timeline has advanced.

### Event Types

| Type | Cycle | Description |
|------|-------|-------------|
| Daily Events | Per `life.json` `daily_interval_seconds / time_ratio` | Randomly selects a few candidates from 200+ scenario pool for LLM; keeps most recent 100 |
| Major Life Events | Per `life.json` `major_interval_seconds / time_ratio` | Concrete long-term events that trigger persona file updates |
| Surprise Events | Independent low-probability channel | Default `0.01` probability per bot per day, overall cooldown default 365 days |

### Event Deduplication & Life Profile

- `event_policy.scenario_cooldown_days` and `major_scenario_cooldown_days` control cooldown for similar events.
- `event_policy.llm_daily_candidate_limit` controls how many daily candidates are sent to the LLM each time (default 12); the full 200+ scenario pool is never stuffed into the prompt.
- `daily_life_profile` describes the bot's city, commute, living situation, work, interests, and event preferences; personality tags also influence candidate weights.

### Time Acceleration

`time_ratio` controls how fast the bot's internal time flows:

| time_ratio | Default Daily Check Interval | Effect | Use Case |
|------------|------------------------------|--------|----------|
| 1 | 86400 seconds | Real 1 day = 1 bot day | Normal experience (default) |
| 24 | 3600 seconds | Real 1 hour = 1 bot day | Mild acceleration |
| 1440 | 60 seconds | Real 1 minute = 1 bot day | Observation/testing |
| 3600 | 1 second | Ultra-fast testing, constrained by 1-second poll floor | Quick verification |

LifeScheduler uses adaptive polling with intervals between 1-10 seconds; each `tick_daily` advances at least 1 day. Long offline periods or very high `time_ratio` values will catch up based on elapsed time, with a maximum of 365 days advanced per tick.

---

## Configuration

### Configuration File Locations

```
~/.ai-companion/
├── config/
│   ├── config.yaml  # Main config
│   ├── models.yaml  # AI model config
│   └── bots.yaml    # Bot list
└── data/
    └── bots/        # Bot configs, memory, life_state/proactive_state
```

### models.yaml Example

```yaml
# Default provider
model:
  provider: "minimax"          # minimax | openai | claude | mimo | ollama | custom
  temperature: 0.8
  max_tokens: 1024

# MiniMax
minimax:
  api_key: "${MINIMAX_API_KEY}"
  base_url: "https://api.minimax.chat/v1"
  model: "MiniMax-M2.7"
  max_context_tokens: 20000

# OpenAI
openai:
  api_key: "${OPENAI_API_KEY}"
  base_url: "https://api.openai.com/v1"
  model: "gpt-4o"
  max_context_tokens: 20000

# Claude
claude:
  api_key: "${ANTHROPIC_API_KEY}"
  base_url: "https://api.anthropic.com/v1"
  model: "claude-sonnet-4-20250514"
  max_context_tokens: 20000

# Xiaomi MiMo
mimo:
  api_key: "${MIMO_API_KEY}"
  base_url: "https://token-plan-cn.xiaomimimo.com/v1"
  model: "mimo-v2.5-pro"
  max_context_tokens: 1048576

# Ollama (local)
ollama:
  base_url: "http://localhost:11434"
  model: "qwen2.5:7b"
  max_context_tokens: 20000

memory:
  embedding: "local"              # Enable local vector embedding
  embedding_model: "all-MiniLM-L6-v2"
  max_working_turns: 20
  hard_limit_chars: 5000
  soft_limit_chars: 3000

skills:
  image_generation:
    enabled: true
    auto: true
    base_url: "https://api.openai.com/v1"
    model: "gpt-image-1"
    api_key: "${OPENAI_API_KEY}"
  image_understanding:
    enabled: true
    auto: true
    base_url: "https://api.openai.com/v1"
    model: "gpt-4o"
    api_key: "${OPENAI_API_KEY}"
```

### Environment Variables

```bash
export MINIMAX_API_KEY="your_key"
export MIMO_API_KEY="your_key"
export FEISHU_APP_ID="your_feishu_app_id"
export FEISHU_APP_SECRET="your_feishu_app_secret"
```

---

## Startup

### Local CLI

```bash
ai-companion start              # Default bot
ai-companion start --bot mybot   # Specify bot
```

### Feishu Gateway Service

```bash
ai-companion gateway start    # Background start (default, continues after terminal close)
ai-companion gateway start --sync  # Foreground start (show logs)
ai-companion gateway stop     # Stop
ai-companion gateway logs     # View logs
```

**Admin UI**: Starting local CLI or Gateway auto-launches local Admin API (http://127.0.0.1:8642) and Web UI (http://localhost:1421). If CLI and Gateway start simultaneously, they share one UI process — no duplicate startup.

```bash
ai-companion start
ai-companion gateway start
```

To disable auto UI, set `START_UI=false` or `AI_COMPANION_START_UI=false`.

### One-Click Update

```bash
ai-companion update       # Update code and dependencies, preserve local data
ai-companion update --cn  # Use Tsinghua PyPI mirror
```

### Built-in Commands

In the conversation interface:

| Command | Description |
|---------|-------------|
| `/new` | Start new session |
| `/memory` | View working memory, episodic memory, user facts, relationship state, user understanding file paths, and vector index count |
| `/forget <key>` | Delete an auto user fact, sync removing `auto` projection from user understanding file |
| `quit` | Exit |

Maintenance commands:

```bash
ai-companion memory rebuild-vector [--bot <bot_id>]
```

---

## Bot Initialization

The repository provides three male and three female bot persona examples. See `docs/BOT_DESIGN_GUIDE.md`. You can also create your own bot via `ai-companion setup` and configure it in `data/bots/{bot_id}/persona/`.

---

## Custom Personality

```
data/bots/mybot/persona/
├── profile.json        # Basic profile (name, age, occupation, etc.)
├── backstory.json      # Life experiences
├── values.json         # Values and bottom lines
├── speaking_style.json # Speaking style
├── conversation_style_rules.json # Conversation style rules to reduce AI flavor
├── proactive.json      # Proactive messaging config
└── life.json           # Life trajectory config
```

Copy template:

```bash
cp -r data/bots/_template data/bots/mybot
```

---

## Testing

Project includes an offline system test suite:

```bash
# End-to-end system tests (config, model factory, memory, BotInstance, proactive, life trajectory, gateway, frontend build)
python tests/system_test_suite.py
```

Test reports are written to `.artifacts/system-test-rebuilt-*/`, current suite covers 40+ core behaviors.

---

## Uninstallation

### Local Installation Uninstall

```bash
# 1. Stop gateway service (if running)
ai-companion gateway stop

# 2. Remove Python package
pip uninstall ai-companion -y

# 3. Delete data directory (optional, removes all Bot config and memory)
rm -rf ~/.ai-companion

# 4. If using virtual environment
rm -rf ~/.ai-companion/.venv

# 5. Remove locally cloned project code (if any)
rm -rf ~/AICompanion  # or your clone directory
```

### Windows

```powershell
# 1. Stop gateway service
ai-companion gateway stop

# 2. Uninstall Python package
pip uninstall ai-companion -y

# 3. Delete data directory
Remove-Item -Recurse -Force ~/.ai-companion

# 4. If using virtual environment
Remove-Item -Recurse -Force ~/.ai-companion/.venv

# 5. Remove locally cloned project code (if any)
Remove-Item -Recurse -Force "$env:LOCALAPPDATA\AICompanion"  # or your clone directory
```

### Docker Uninstall

```bash
# Stop and remove container
docker-compose -f ~/.ai-companion/docker-compose.yml down

# Delete data volume
docker volume rm ai-companion-data 2>/dev/null

# Delete installation directory
rm -rf ~/.ai-companion
```

---

## Notes

- **Python version**: Local installation requires Python 3.11+
- **Virtual environment**: If system Python is protected (externally-managed-environment), scripts auto-create virtual environment `~/.ai-companion/.venv`
- **Data directory**: All data stored in `~/.ai-companion/`
- **API Key**: API Key required after installation, see [Configuration](#configuration)
- **Repeated setup**: Config wizard retains old values by default, only merges model, Bot, or platform config modified this run

---

## FAQ

**Q: "API Key not set" error**
A: `export MINIMAX_API_KEY="your_key"`

**Q: Bot doesn't send proactive messages**
A: Check `data/bots/{bot_id}/persona/proactive.json` `enabled`, `mode`, `platform.type` and platform sender config; messages won't count when platform sender isn't configured.

**Q: Bot doesn't seem to know about its own proactive messages?**
A: Proactive messages are written to Working / Daily memory with `assistant_initiated` / `proactive` / `proactive_kind` metadata. The next reply will automatically follow up on the proactive motivation and project it as "what the bot recently proactively did" via `self_memory`. If you still see old behavior, check `~/.ai-companion/logs/gateway.log`, `working.db` and `daily.db` for `metadata_json` to confirm it's not stale data or records from an older version.

**Q: Vector embedding not working**
A: Confirm `models.yaml` has `memory.embedding: "local"` (sentence-transformers should be installed by default), then run `ai-companion memory rebuild-vector --bot <bot_id>`. If clicking rebuild in the admin UI shows `TypeError: Failed to fetch`, the gateway usually hasn't restarted or CORS is blocked; run `ai-companion gateway restart` and refresh the page.

**Q: How to reset memory?**
A: Delete auto memory by clearing `~/.ai-companion/data/bots/{bot_id}/memory/*.db`. `manual` in `user_understanding.json` is user-written understanding; recommend not deleting directly unless you want to fully reset the bot's initialization understanding of the user.

---

## Documentation

| Document | Description |
|----------|-------------|
| [User Guide](./docs/GUIDE.md) | Detailed configuration and feature guide |
| [Bot Design Guide](./docs/BOT_DESIGN_GUIDE.md) | New Bot examples and self-built Bot methodology |
| [Bot JSON Fields](./docs/BOT_JSON_FIELDS.md) | `profile.json` / `life.json` / `proactive.json` / state file field descriptions |
| [Proactive Design](./docs/DESIGN_phase5_proactive.md) | Proactive messaging architecture and algorithm design |
| [Human-Like Memory & Token Control Design](./docs/DESIGN_human_like_memory_token_architecture.md) | Memory hierarchy, conscious workspace, and context budget design |
| [UI Design](./docs/ui/UI_DESIGN.md) | Admin UI design specifications |
| [UI Spec](./docs/ui/UI_SPEC.md) | Admin UI feature list |

---

## License

This project is licensed under [BSL 1.1 (Business Source License)](./LICENSE).

| Item | Details |
|------|---------|
| **Change Date** | 2031-05-17 |
| **Change License** | Mulan Permissive Software License, Version 2 (MulanPSL-2) |

### Allowed

- Personal, non-commercial self-hosted use
- Internal organizational use (including evaluation, testing, and development)
- Modifying the code for non-commercial purposes
- Contributing to the project via pull requests

### Prohibited

- Offering this project or its core functionality as a SaaS service to third parties
- Building a hosted platform with similar functionality for paid use
- Reselling or redistributing this project's functionality as a paid service

The above restrictions automatically expire on the Change Date (2031-05-17), after which the project will be fully open-sourced under the MulanPSL-2 license.
