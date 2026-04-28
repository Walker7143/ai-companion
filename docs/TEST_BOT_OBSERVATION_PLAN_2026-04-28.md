# 测试 Bot 观察方案（2026-04-28）

目标：正式安装环境下，重点验证主动唤醒行为；人生轨迹专项 Bot 已测试完毕并删除。

## 1. Bot 清单

| 类型 | Bot ID | 名称 | 关键设计 |
|---|---|---|---|
| 主动唤醒专项 | `obs_proactive_lab` | 唤醒实验酱 | 主动唤醒高频，人生轨迹低频（减少干扰） |
| 联动综合 | `obs_combo_lab` | 联动实验姬 | 主动唤醒开启 + 人生轨迹中高频，观察联动 |

配置位置：

- `~/.ai-companion/data/bots/obs_proactive_lab/persona/`
- `~/.ai-companion/data/bots/obs_combo_lab/persona/`
- Bot 列表：`~/.ai-companion/config/bots.yaml`

## 2. 关键参数（当前）

### 2.1 `obs_proactive_lab`

- Proactive: `mode=active`
- `check_interval_seconds=30`
- `idle_threshold_hours=0.03`
- `min_interval_hours=0.03`
- `max_daily=30`
- `preferred_contact_times=["00:00-23:59"]`
- Life: `daily_interval=7200s`, `major_interval=43200s`

### 2.2 `obs_combo_lab`

- Proactive: `mode=active`
- `check_interval_seconds=45`
- `idle_threshold_hours=0.1`
- `min_interval_hours=0.15`
- `max_daily=12`
- Life 原始参数：
  - `daily_interval_seconds=1200`
  - `major_interval_seconds=7200`
  - `time_ratio=60`
- 实际调度间隔：
  - `daily_interval=20s`
  - `major_interval=120s`

## 3. 启动与观察

优先单 Bot 观察，避免多个 Bot 噪声叠加。

CLI 当前行为（已按需求调整）：

- 启动 CLI 时，仅初始化 Bot，不会立即启动所有 Bot 的人生轨迹/主动唤醒调度器。
- 你在 CLI 中选中某个 Bot（或 `switch` 切换到某 Bot）后，该 Bot 会立即启动人生轨迹（以及该 Bot 的 proactive，如为 active）。
- 未对话的其他 Bot 不会推进人生轨迹。

### 3.1 启动单个 Bot（CLI）

```bash
~/.ai-companion/.venv/bin/python -m ai_companion start --bot obs_proactive_lab
~/.ai-companion/.venv/bin/python -m ai_companion start --bot obs_combo_lab
```

### 3.2 启动网关统一观察（可选）

```bash
~/.ai-companion/.venv/bin/python -m ai_companion gateway start
~/.ai-companion/.venv/bin/python -m ai_companion gateway status
~/.ai-companion/.venv/bin/python -m ai_companion gateway logs
```

## 4. 日志观察建议

```bash
tail -f ~/.ai-companion/logs/proactive.联动实验姬.log
tail -f ~/.ai-companion/logs/life.联动实验姬.log
tail -f ~/.ai-companion/logs/cli.联动实验姬.log
```

按 Bot 名称分文件规则：

- `~/.ai-companion/logs/cli.<Bot名称>.log`
- `~/.ai-companion/logs/life.<Bot名称>.log`
- `~/.ai-companion/logs/proactive.<Bot名称>.log`

关注点：

- 主动唤醒是否按预期触发频率发送
- 主动唤醒未绑定发送通道时是否不计数
- 用户回复后主动唤醒状态是否正确重置
- 联动 Bot 是否出现“生活事件 -> 更自然的主动话题”

## 5. 已验证状态

- 人生轨迹专项 Bot 已删除：`test_life`、`obs_life_lab`。
- 主动唤醒相关 Bot 保留：`test_proactive`、`obs_proactive_lab`，联动 Bot 保留：`obs_combo_lab`。
- CLI 按选中启动验证通过：
  - 选中前：`life_scheduler/proactive_scheduler` 未启动
  - 选中（或 switch）后立即启动当前 Bot：
    - `obs_combo_lab`: `proactive_running=True`，`life_running=True`
