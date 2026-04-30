# AI Companion / AI 知己

An open-source AI companion product supporting macOS / Linux / Windows. Each bot has its own personality and memory system, interacting with you like a real person.

## Core Features

| Feature | Description |
|---------|-------------|
| **Multi-Model Support** | MiniMax / OpenAI / Claude / Ollama / Custom API |
| **Distinct Personalities** | Each Bot has unique character, backstory, and speaking style (tsundere / lively / gentle / aloof...) |
| **Intelligent Memory System** | Working memory + User model + Relationship state + Episodic memory + User understanding file, retrieved by intent rather than dumping context |
| **Local Vector Embedding** | Supports sentence-transformers for local semantic retrieval, Chinese-friendly |
| **Life Trajectory** | Each Bot has its own timeline with daily events, life milestones, birthdays, and low-probability surprises |
| **Proactive Messaging** | Bots can initiate conversations, remind you of things, and occasionally act clingy based on LLM reasoning, incorporating current timeline and recent life events |
| **Relationship Evolution** | Bot behavior gradually changes based on interaction depth (stranger → lover) |
| **Personality-Based Refusal** | Determines whether to answer based on personality, not simple keyword filtering |
| **Multimedia Skills** | Image generation, voice synthesis |
| **Multi-Platform Gateway** | Local CLI / Feishu / Webhook, multiple message delivery methods |

---

## Quick Start

### Prerequisites

Before running the installation commands, ensure you have:

- **Python 3.11+**: Required for backend and CLI tools
- **Git**: Installation scripts pull project code
- **Network connection**: Required to download Python dependencies, frontend dependencies, and project code
- **A model provider**: Any one of MiniMax / OpenAI / Claude / Ollama / Custom API. Cloud models require an API Key; Ollama requires a running local Ollama service
- **Node.js + npm (recommended)**: For the admin web UI. Optional if using CLI only

Dependencies are installed automatically by the installation script and `ai-companion setup`.

### Installation

**macOS / Linux (China users):**
```bash
curl -fsSL https://gitee.com/wang_xiao_wei_7143/ai-girl-friend/raw/master/scripts/install-cn.sh | bash
```

**Windows (China users):**
```powershell
irm https://gitee.com/wang_xiao_wei_7143/ai-girl-friend/raw/master/scripts/install-cn.ps1 -UseBasicParsing | iex
```

**International users** please download the corresponding script from [Gitee Release](https://gitee.com/wang_xiao_wei_7143/ai-girl-friend/releases).

### Initial Setup

```bash
source ~/.ai-companion/.venv/bin/activate  # If using virtual environment
ai-companion setup
```

When re-running `setup`, it merges updates with existing configuration: parts not reconfigured or overwritten retain their old values. For example, changing only the model won't overwrite existing Bot, timeline, or proactive configurations.

---

## Project Architecture

```
ai_companion/
├── bot/              # Bot core
│   ├── instance.py   # BotInstance - core runtime
│   └── manager.py    # BotManager - multi-Bot management
├── memory/           # Memory system
│   ├── engine.py     # MemoryEngine - memory write, retrieval, maintenance coordination
│   ├── extractor.py  # MemoryExtractor - extract candidate memories from conversations
│   ├── governor.py   # MemoryGovernor - evaluate if candidates are worth long-term storage
│   ├── retriever.py  # MemoryRetriever - plan retrieval by current intent
│   ├── prompt_builder.py  # MemoryPromptBuilder - build memory context
│   ├── maintenance.py     # MemoryMaintenance - expiration, archival, projection refresh
│   └── stores/
│       ├── working.py    # Working memory / raw message stream
│       ├── episodic.py   # Episodic memory - important shared experiences
│       ├── semantic.py   # User model - structured user facts
│       ├── relationship.py       # Relationship state - affection, intimacy, tension, key moments
│       └── user_understanding.py # User-editable understanding file
├── persona/          # Personality system
│   ├── loader.py     # PersonaLoader - personality loading
│   ├── engine.py     # PersonaEngine - System Prompt construction
│   └── refusal_engine.py  # RefusalEngine - personality-based refusal
├── proactive/        # Proactive messaging system
│   ├── engine.py     # ProactiveEngine - LLM judgment + message generation
│   ├── scheduler.py   # ProactiveScheduler - proactive check scheduling
│   ├── platform.py   # Platform adapter (CLI/Feishu/Webhook)
│   ├── life_engine.py     # LifeEngine - life trajectory event generation
│   ├── life_scheduler.py  # LifeScheduler - independent timeline scheduling
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
└── vite.config.ts   # Vite build configuration
```

---

## Intelligent Memory System

AI Companion's memory system doesn't simply "store more" — it first evaluates what's worth remembering, then selects relevant memories based on the current conversation intent. Core flow:

```text
Current conversation
  → Working/Raw Log saves original text
  → Extractor extracts candidate memories
  → Governor decides write/skip/archive
  → User Model / Episodic / Relationship layered storage
  → Retriever retrieves by intent
  → PromptBuilder generates memory context
```

### Memory Layers

| Layer | Storage | Description |
|-------|---------|-------------|
| Working / Raw Log | `working.db` | Current session original, compressed summary, debug ledger |
| User Model | `semantic.db` | Structured user facts with category, confidence, source, evidence, expiration |
| Relationship State | `relationship.db` | Bot-user relationship labels, affection, intimacy, tension, key relationship moments |
| Episodic Memory | `episodic.db` + optional Chroma | Important shared experiences, conflicts/resolutions, commitments, life events; regular small talk not recorded |
| User Understanding | `user_understanding.json` | User-editable "Bot's understanding of user" with `manual` and `auto` sections |

### User Understanding File

Each Bot has a directly editable user understanding file:

```
~/.ai-companion/data/bots/{bot_id}/memory/user_understanding.json
```

Used to initialize and correct the Bot's understanding of the user:

- `manual`: User-written content, always prioritized, never overwritten by auto memory
- `auto`: Understanding formed from daily conversations, relationship state, and Bot reflection, auto-refreshed
- Prompt uses `manual` first, then relevant `auto`
- Built-in Bots include initial `manual` for basic interaction guidelines; `auto` refreshes over time

Example:

```json
{
  "version": 3,
  "manual": {
    "summary": "User prefers to be treated gently without being dismissed.",
    "facts": {"nickname": "Achi"},
    "communication_style": ["Empathize first, then give advice"],
    "boundaries": ["Don't make jokes about weight"],
    "relationship_expectations": ["Wants Bot to accompany with the familiarity of someone who knows the boundaries"]
  },
  "auto": {
    "profile_summary": "User has been under recent stress and needs to be met with empathy when emotionally low.",
    "facts": {"city": "Shanghai"},
    "emotional_patterns": ["Gets anxious under pressure but willing to push forward"],
    "comfort_strategies": ["Spend time together first, then give specific advice"],
    "current_context": ["Recently preparing portfolio"],
    "open_threads": ["User wants to continue discussing portfolio"]
  },
  "relationship_memory": {
    "what_user_seems_to_need_from_bot": ["Stable companionship, not mechanical advice"],
    "things_that_brought_them_closer": ["User started proactively sharing vulnerable moments"]
  }
}
```

### Dynamic Retrieval

System evaluates current intent first, then selects different memories:

| Intent | Priority Retrieval |
|--------|-------------------|
| Emotional support | Communication preferences, boundaries, recent stressors, relationship state |
| Recalling old events | Episodic memory first, cross-session if needed |
| Advancing plans | open_threads, goals, recent context |
| Relationship repair | Relationship state, conflict/resolution fragments, boundaries |
| Task requests | Minimal necessary preferences, avoid irrelevant emotional memory interference |
| Proactive messaging | open_threads, relationship state, recent user state, Bot life timeline |

### Local Vector Retrieval

```yaml
# Enable local vector embedding
memory:
  embedding: "local"              # "local" | "none"
  embedding_model: "all-MiniLM-L6-v2"
```

---

## Proactive Messaging System

### Trigger Mechanisms

- **Idle trigger**: Bot reaches out when user hasn't interacted for a while
- **Emotional trigger**: Delayed care when user messages contain specific emotional keywords
- **Gradient silence**: Adjust frequency based on time since last contact (7/14/30 day thresholds)
- **Life topics**: Proactive judgment and message generation read Bot's current date, dynamic age, life stage, and recent shareable events

### Delivery Platforms

| Platform | Config | Message destination |
|----------|--------|---------------------|
| CLI | `platform.type: "cli"` | Terminal stdout |
| Feishu | `platform.type: "feishu"` | Feishu user/group |
| Webhook | `platform.type: "webhook"` | Custom HTTP endpoint |

### Rate Limiting

- Maximum daily proactive messages
- Minimum send interval
- Cooldown mechanism
- Anger degradation (reduce interruptions after multiple user non-replies)

---

## Life Trajectory System

Bots have an independent life timeline running separately from the proactive scheduler. Life trajectory state feeds into regular conversations, daily events, life milestones, and proactive messaging prompts — preventing Bot from answering based on a static age after the timeline progresses.

### Event Types

| Type | Period | Description |
|------|--------|-------------|
| Daily events | Based on `life.json` `daily_interval_seconds / time_ratio` | Random selection from 200+ scenario pool, limited candidates given to LLM; last 100 events retained max |
| Life milestones | Based on `life.json` `major_interval_seconds / time_ratio` | Specific long-term events triggering personality file updates |
| Random events | Independent low-probability channel | Default 0.01 probability per Bot day, overall cooldown default 365 days |

### Event Deduplication and Life Profile

- `event_policy.scenario_cooldown_days` and `major_scenario_cooldown_days` control same-type event cooldowns
- `event_policy.llm_daily_candidate_limit` controls daily candidates given to LLM, default 12, avoiding flooding prompt with full 200+ pool
- `daily_life_profile` describes Bot's city, commute, residence, work, interests, and event preferences; personality tags also affect candidate weights

### Time Acceleration

`time_ratio` controls Bot internal time flow speed:

| time_ratio | Default daily check interval | Common effect | Use case |
|------------|------------------------------|---------------|----------|
| 1 | 86400 seconds | 1 real day = 1 Bot day | Normal experience (default) |
| 24 | 3600 seconds | 1 real hour = 1 Bot day | Light acceleration |
| 1440 | 60 seconds | 1 real minute = 1 Bot day | Observation/testing |
| 3600 | 1 second | Extreme testing, constrained by 1-second polling minimum | Quick verification |

LifeScheduler adapts polling interval between 1-10 seconds; single `tick_daily` advances at least 1 day, long offline or extremely high `time_ratio` backfills by elapsed time, max 365 days per single tick.

---

## Configuration

### Config File Location

```
~/.ai-companion/
├── config/
│   ├── config.yaml  # Main config
│   ├── models.yaml  # AI model config
│   └── bots.yaml    # Bot list
└── data/
    └── bots/        # Bot config, memory, life_state/proactive_state
```

### models.yaml Example

```yaml
# Default provider
model:
  provider: "minimax"          # minimax | openai | claude | ollama | custom
  temperature: 0.8
  max_tokens: 1024

# MiniMax
minimax:
  api_key: "${MINIMAX_API_KEY}"
  base_url: "https://api.minimax.chat/v1"
  model: "MiniMax-M2.7"

# OpenAI
openai:
  api_key: "${OPENAI_API_KEY}"
  base_url: "https://api.openai.com/v1"
  model: "gpt-4o"

# Claude
claude:
  api_key: "${ANTHROPIC_API_KEY}"
  base_url: "https://api.anthropic.com/v1"
  model: "claude-sonnet-4-20250514"

# Ollama (local)
ollama:
  base_url: "http://localhost:11434"
  model: "qwen2.5:7b"

memory:
  embedding: "local"              # Enable local vector embedding
  embedding_model: "all-MiniLM-L6-v2"
  max_working_turns: 20
  hard_limit_chars: 5000
  soft_limit_chars: 3000
```

### Environment Variables

```bash
export MINIMAX_API_KEY="your_key"
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

### Built-in Commands

In the conversation interface:

| Command | Description |
|---------|-------------|
| `/new` | Start new session |
| `/memory` | View working memory, episodic memory, user facts, relationship state, and user understanding file paths |
| `/forget <key>` | Delete an auto user fact, sync removing `auto` projection from user understanding file |
| `quit` | Exit |

---

## Bot Initialization

Repository provides three male and three female Bot personas as examples. See `docs/BOT_DESIGN_GUIDE.md`. You can also create your own Bot via `ai-companion setup` and configure in `data/bots/{bot_id}/persona/`.

---

## Custom Personality

```
data/bots/mybot/persona/
├── profile.json        # Basic profile (name, age, occupation, etc.)
├── backstory.json      # Life experiences
├── values.json        # Values and bottom lines
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

Project includes offline system test suite:

```bash
# End-to-end system tests (config, model factory, memory, BotInstance, proactive, life trajectory, gateway, frontend build)
python tests/system_test_suite.py
```

Test reports written to `.artifacts/system-test-rebuilt-*/`, current suite covers 40+ core behaviors.

---

## Installation

For detailed installation instructions, see [Quick Start](#quick-start) above.

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

**Q: Vector embedding not working**
A: Confirm `models.yaml` `memory.embedding: "local"` (sentence-transformers should be installed by default)

**Q: How to reset memory?**
A: Delete auto memory by clearing `~/.ai-companion/data/bots/{bot_id}/memory/*.db`. `manual` in `user_understanding.json` is user-written understanding, recommend not deleting directly unless you want to fully reset Bot's initialization understanding of user.

---

## Documentation

| Document | Description |
|----------|-------------|
| [User Guide](./docs/GUIDE.md) | Detailed configuration and feature guide |
| [Bot Design Guide](./docs/BOT_DESIGN_GUIDE.md) | New Bot examples and self-built Bot methodology |
| [Bot JSON Fields](./docs/BOT_JSON_FIELDS.md) | `profile.json` / `life.json` / `proactive.json` / state file field descriptions |
| [Proactive Design](./docs/DESIGN_phase5_proactive.md) | Proactive messaging architecture and algorithm design |
| [UI Design](./docs/ui/UI_DESIGN.md) | Admin UI design specifications |
| [UI Spec](./docs/ui/UI_SPEC.md) | Admin UI feature list |

---

## License

MIT
