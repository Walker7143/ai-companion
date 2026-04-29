# Bot JSON 通用字段说明

> 说明：JSON 标准不支持注释。不要在运行时读取的 `.json` 文件里写 `//`、`/* */` 或尾随逗号，否则 `json.load()` 会解析失败。本文档作为字段字典使用，运行文件仍保持纯 JSON。

本文档面向所有 Bot，不绑定任何单个 Bot 或业务领域。字段说明按系统读取方式编写；没有列出的自定义字段通常会被保留在 JSON 中，但不一定会被核心逻辑读取。

## 目录结构

典型 Bot 目录：

```text
data/bots/{bot_id}/
├── persona/
│   ├── profile.json
│   ├── backstory.json
│   ├── values.json
│   ├── speaking_style.json
│   ├── proactive.json
│   └── life.json
├── proactive_state.json
└── life_state.json
```

用户安装后的实际运行目录通常在：

```text
~/.ai-companion/data/bots/{bot_id}/
```

`persona/*.json` 是人工配置和人格素材。`*_state.json` 是运行时状态，通常不建议手工编辑，除非是在调试或重置状态。

## profile.json

基础档案。`PersonaEngine` 主要读取 `name`、`age`、`occupation`、`personality_tags`、`relationship_to_user`；人生轨迹系统还会读取 `birth_date`。这些字段可以描述任何类型的 Bot：角色、助手、朋友、虚构人物或业务场景角色。


| 字段                     | 类型            | 必填  | 说明                                                                    |
| ---------------------- | ------------- | --- | --------------------------------------------------------------------- |
| `id`                   | string        | 是   | Bot 唯一 ID，应与目录名和 `bots.yaml` 中的 `id` 一致。                              |
| `name`                 | string        | 是   | Bot 展示名，也会进入 system prompt。                                           |
| `age`                  | number        | 是   | 初始年龄。启用人生轨迹后，对话中的当前年龄优先按 `birth_date` + `life_state.current_date` 计算。 |
| `birth_date`           | string/null   | 推荐  | 出生日期，格式 `YYYY-MM-DD`。用于生日事件、动态年龄和时间线。                                 |
| `occupation`           | string        | 是   | 职业或身份，会影响人格和人生事件生成。                                                   |
| `gender`               | string        | 否   | 性别或身份描述，例如 `female`、`male`、`non_binary`、`unspecified`。主要作为人格素材。       |
| `personality_tags`     | array[string] | 是   | 性格标签，例如 `傲娇`、`嘴硬心软`。会进入 system prompt，也用于粗略识别主动消息风格。                  |
| `relationship_to_user` | string        | 是   | 与用户的关系，例如 `朋友`、`暧昧中`、`恋人`。会进入 system prompt。                          |
| `appearance`           | string        | 否   | 外貌描述，供人格、图片或多模态功能参考。                                                  |
| `interests`            | array[string] | 否   | 兴趣爱好，供人格和事件生成参考。                                                      |
| `attitude_score`       | number        | 否   | 关系好感分。部分记忆/evolution 逻辑会写回。                                           |
| `avatar_prompt`        | string        | 否   | 头像或图像生成提示词。                                                           |
| `summary`              | string        | 否   | 简短人物摘要。旧模板或自定义 Bot 可使用。                                               |
| `settings`             | object        | 否   | 回复风格偏好，见下表。                                                           |


`settings` 子字段：


| 字段                | 类型     | 说明                            |
| ----------------- | ------ | ----------------------------- |
| `tone_default`    | string | 默认语气，例如 `略带冷淡但不失礼貌`。          |
| `emoji_usage`     | string | Emoji 使用频率，例如 `从不`、`偶尔`、`经常`。 |
| `response_length` | string | 回复长度偏好，例如 `简短`、`中等`、`较长`。     |


## backstory.json

背景经历。`PersonaEngine` 会重点读取 `key_moments`；PersonaUpdater 也会优先把人生大事追加到这里。字段可按 Bot 类型灵活取舍，不需要所有字段都出现。


| 字段                     | 类型            | 必填  | 说明                                           |
| ---------------------- | ------------- | --- | -------------------------------------------- |
| `summary`              | string        | 否   | 背景总述。适合简化模板或不需要分阶段背景的 Bot。                   |
| `childhood`            | string        | 否   | 童年经历。                                        |
| `teenage`              | string        | 否   | 青少年时期经历。                                     |
| `youth`                | string        | 否   | 青年时期经历。兼容旧模板字段。                              |
| `university`           | string        | 否   | 大学或重要成长期经历。                                  |
| `career`               | string        | 否   | 职业经历。                                        |
| `now`                  | string        | 否   | 当前状态、生活阶段或角色处境。                              |
| `meeting_user`         | string        | 否   | 与用户相识的故事。                                    |
| `relationship_history` | string        | 否   | 与用户或主要交互对象的关系发展历史。                           |
| `key_moments`          | array[string] | 推荐  | 与用户或人生相关的关键时刻。会进入 system prompt，人生大事也会追加到这里。 |


## speaking_style.json

说话风格。`PersonaEngine` 主要读取 `tone`、`口头禅`、`emotion_indicators`。


| 字段                    | 类型            | 必填  | 说明                                           |
| --------------------- | ------------- | --- | -------------------------------------------- |
| `tone`                | string        | 是   | 整体语气，例如 `外冷内热，话不多但每句有点分量`。                   |
| `口头禅`                 | array[string] | 否   | 常用口头禅或短句。                                    |
| `greeting_style`      | string        | 否   | 打招呼风格。                                       |
| `farewell_style`      | string        | 否   | 告别风格。                                        |
| `emotion_indicators`  | object        | 否   | 不同情绪下的语言表现。键可自定义，例如 `happy`、`sad`、`angry`。   |
| `special_expressions` | array[string] | 否   | 特殊表达方式。                                      |
| `response_patterns`   | object        | 否   | 面对特定场景的回复模式，例如 `praise`、`complaint`、`flirt`。 |
| `style`               | string        | 否   | 旧模板字段，表示风格类型。                                |
| `traits`              | array[string] | 否   | 旧模板字段，表示说话特征。                                |
| `phrases`             | object        | 否   | 旧模板字段，按场景列举短句。                               |
| `forbidden_words`     | array[string] | 否   | 不希望 Bot 使用的词。当前核心 prompt 不强制执行，可作为素材。        |


`emotion_indicators` 常见子字段：


| 字段        | 类型     | 说明         |
| --------- | ------ | ---------- |
| `happy`   | string | 开心时的表现。    |
| `sad`     | string | 难过时的表现。    |
| `angry`   | string | 生气时的表现。    |
| `jealous` | string | 吃醋时的表现。    |
| `lonely`  | string | 孤独或想念时的表现。 |


## values.json

价值观和底线。`PersonaEngine` 会读取 `non_negotiable`，拒绝引擎会参考软边界、关键词和关系阈值。


| 字段                            | 类型            | 必填  | 说明                             |
| ----------------------------- | ------------- | --- | ------------------------------ |
| `non_negotiable`              | array[string] | 推荐  | 绝对原则和不可妥协事项。会进入 system prompt。 |
| `soft_boundaries`             | array[object] | 推荐  | 软边界规则，见下表。                     |
| `triggers_jealousy`           | array[string] | 否   | 会触发吃醋的行为或话题。                   |
| `deal_breakers`               | array[string] | 否   | 可能导致关系破裂的行为。                   |
| `personality_evolution_notes` | array[string] | 否   | 人格演化约束或提示。                     |


`soft_boundaries[]` 子字段：


| 字段                   | 类型            | 说明                       |
| -------------------- | ------------- | ------------------------ |
| `topic`              | string        | 边界话题名称。                  |
| `keywords`           | array[string] | 触发关键词。                   |
| `attitude`           | string        | Bot 对该话题的态度。             |
| `reason`             | string        | 态度背后的原因。                 |
| `persona_response`   | string        | 触发时可参考的人格化回应。            |
| `relation_threshold` | number        | 关系阈值，通常 0-1。关系越亲近，越可能软化。 |


## proactive.json

主动唤醒配置。支持当前嵌套结构，也兼容一部分旧版扁平字段。不同平台可以只配置自己需要的投递字段。


| 字段                         | 类型            | 默认值               | 说明                                                               |
| -------------------------- | ------------- | ----------------- | ---------------------------------------------------------------- |
| `enabled`                  | boolean       | `true`            | 是否启用主动唤醒系统。                                                      |
| `mode`                     | string        | `active`          | `active` 表示会主动发消息；`silent` 表示保留状态但不主动发。旧值 `idle` 会被兼容为 `silent`。 |
| `scheduler`                | object        | 见下表               | 后台调度参数。                                                          |
| `triggers`                 | object        | 见下表               | 触发器参数。                                                           |
| `platform`                 | object        | 见下表               | 主动消息投递平台。                                                        |
| `preferred_contact_times`  | array[string] | `["09:00-23:00"]` | 允许主动联系的时间段，格式 `HH:MM-HH:MM`。                                     |
| `timezone`                 | string        | `Asia/Shanghai`   | 主动唤醒使用的时区。                                                       |
| `random_trigger_prob`      | number        | `0.05`            | 随机提前触发概率。                                                        |
| `random_trigger_min_ratio` | number        | `0.5`             | 至少达到空闲阈值的多少比例后，才允许随机提前触发。                                        |
| `home_channel`             | string/object | 无                 | 可选。飞书等平台的主动发送目标，例如 `chat_id`。                                    |


`scheduler` 子字段：


| 字段                       | 类型     | 默认值   | 说明                    |
| ------------------------ | ------ | ----- | --------------------- |
| `check_interval_seconds` | number | `600` | 主动唤醒检查间隔，单位秒。         |
| `idle_threshold_hours`   | number | `24`  | 用户空闲多久后考虑主动联系，单位小时。   |
| `max_daily`              | number | `5`   | 每天最多主动消息数。            |
| `min_interval_hours`     | number | `4`   | 两次主动消息之间最小间隔，单位小时。    |
| `max_idle_days`          | number | `7`   | 用户长期不回应超过该天数后降低或停止主动。 |


`triggers.idle_reminder` 子字段：


| 字段           | 类型      | 默认值    | 说明             |
| ------------ | ------- | ------ | -------------- |
| `enabled`    | boolean | `true` | 是否启用空闲提醒。      |
| `idle_hours` | number  | `24`   | 空闲提醒触发阈值，单位小时。 |


`triggers.emotion_trigger` 子字段：


| 字段                       | 类型            | 默认值    | 说明                 |
| ------------------------ | ------------- | ------ | ------------------ |
| `enabled`                | boolean       | `true` | 是否启用情绪关键词触发。       |
| `keywords`               | array[string] | 内置情绪词  | 用户消息包含这些词时，可能延迟关心。 |
| `response_delay_minutes` | number        | `5`    | 情绪触发后的延迟响应时间，单位分钟。 |


`platform` 子字段：


| 字段             | 类型            | 默认值    | 说明                                  |
| -------------- | ------------- | ------ | ----------------------------------- |
| `type`         | string        | `cli`  | 投递平台，常见值：`cli`、`feishu`、`webhook`。  |
| `webhook_url`  | string/null   | `null` | `type=webhook` 时使用的目标地址。            |
| `home_channel` | string/object | 无      | 平台目标频道。部分代码也会从顶层 `home_channel` 读取。 |
| `chat_id`      | string        | 无      | 飞书群聊或用户会话 ID。                       |
| `group_id`     | string        | 无      | 飞书群 ID，作为 `chat_id` 的兼容来源。          |


旧版扁平字段兼容映射：


| 旧字段                              | 当前字段                                              |
| -------------------------------- | ------------------------------------------------- |
| `check_interval`                 | `scheduler.check_interval_seconds`                |
| `idle_threshold_hours`           | `scheduler.idle_threshold_hours`                  |
| `max_daily`                      | `scheduler.max_daily`                             |
| `min_interval_hours`             | `scheduler.min_interval_hours`                    |
| `max_idle_days`                  | `scheduler.max_idle_days`                         |
| `idle_reminder_enabled`          | `triggers.idle_reminder.enabled`                  |
| `idle_reminder_hours`            | `triggers.idle_reminder.idle_hours`               |
| `emotion_trigger_enabled`        | `triggers.emotion_trigger.enabled`                |
| `emotion_keywords`               | `triggers.emotion_trigger.keywords`               |
| `emotion_response_delay_minutes` | `triggers.emotion_trigger.response_delay_minutes` |
| `platform_type`                  | `platform.type`                                   |
| `webhook_url`                    | `platform.webhook_url`                            |


## life.json

人生轨迹配置。控制 Bot 自己的日期、日常事件、人生大事、生日、里程碑和事件去重策略。


| 字段                              | 类型            | 默认值     | 说明                                          |
| ------------------------------- | ------------- | ------- | ------------------------------------------- |
| `daily_interval_seconds`        | number        | `86400` | 日常事件基础检查间隔。默认现实 1 天，实际间隔会除以 `time_ratio`。       |
| `major_interval_seconds`        | number        | `604800` | 人生大事基础检查间隔。默认现实 7 天，实际间隔会除以 `time_ratio`。       |
| `time_ratio`                    | number        | `1`     | Bot 时间流速倍率。默认 1 表示现实时间 1:1；值越大，Bot 日期推进越快。    |
| `time_ratio_warning_threshold`  | number        | `500`   | 超过该值时输出警告，提示可能影响事件质量。                       |
| `daily_event_min_gap_days`      | number        | `2`     | 至少每 N 个 Bot 日尝试产出 1 个日常事件。无可用场景时会跳过，避免重复。   |
| `major_event_fixed_probability` | number        | `0.05`  | 每个 Bot 日触发固定概率人生大事的概率，范围 0-1。               |
| `max_events`                    | number        | `100`   | 最多保留的日常事件数。系统硬上限为 100，配置更大也只保留最近 100 条。     |
| `max_context_bits`              | number        | `2000`  | 日常事件上下文最大字符预算。                              |
| `season`                        | object        | 见下表     | 季节配置。                                       |
| `milestones`                    | array[object] | `[]`    | 年龄里程碑。                                      |
| `holidays`                      | array[object] | 内置节日    | 节假日配置。                                      |
| `birth_date`                    | string/null   | `null`  | Bot 出生日期，格式 `YYYY-MM-DD`。                   |
| `event_policy`                  | object        | 见下表     | 事件场景冷却、权重和自定义模板策略。                          |
| `daily_life_profile`            | object        | `{}`    | 日常生活画像。用于影响日常小事候选场景的权重，不会把完整大场景池塞进 prompt。    |


`season` 子字段：


| 字段               | 类型     | 默认值     | 说明                          |
| ---------------- | ------ | ------- | --------------------------- |
| `hemisphere`     | string | `north` | 季节所在半球，支持 `north`、`south`。  |
| `birthday_month` | number | `1`     | 未配置 `birth_date` 时用于反推生日月份。 |


`milestones[]` 子字段：


| 字段             | 类型     | 说明           |
| -------------- | ------ | ------------ |
| `age`          | number | 到达该年龄时触发。    |
| `event`        | string | 里程碑事件描述。     |
| `topic_prompt` | string | 主动分享时的话题切入语。 |


`holidays[]` 子字段：


| 字段      | 类型     | 说明                            |
| ------- | ------ | ----------------------------- |
| `name`  | string | 节假日名称。                        |
| `month` | number | 月份，1-12。                      |
| `day`   | number | 日期，1-31。                      |
| `type`  | string | 节日类型，例如 `法定假日`、`传统节日`、`西方节日`。 |


`event_policy` 子字段：


| 字段                               | 类型            | 默认值    | 说明                                      |
| -------------------------------- | ------------- | ------ | --------------------------------------- |
| `scenario_cooldown_days`         | number        | `14`   | 同一日常场景冷却天数。用于减少重复事件。                    |
| `major_scenario_cooldown_days`   | number        | `180`  | 同一人生大事场景冷却天数。                           |
| `unexpected_event_probability`   | number        | `0.01` | 每个 Bot 日检查时，独立触发意外类人生大事的低概率。取值范围 0-1。   |
| `unexpected_event_cooldown_days` | number        | `365`  | 意外类人生大事整体冷却天数，避免短期内连续出现事故、灾害等高冲击事件。     |
| `llm_recent_event_limit`         | number        | `20`   | 传给 LLM 的最近事件数量。                         |
| `llm_forbidden_scenario_limit`   | number        | `12`   | 传给 LLM 的近期禁用场景数量。                       |
| `llm_daily_candidate_limit`      | number        | `12`   | 每次传给 LLM 的日常候选场景数量。系统会先过滤近期/冷却场景，再从 200+ 内置场景中随机抽样。最大 20。 |
| `disabled_scenarios`             | array[string] | `[]`   | 禁用的全局场景 key。                            |
| `scenario_weights`               | object        | `{}`   | 场景权重，key 是场景名，value 是数字。0 表示禁用，越大越容易出现。 |
| `custom_scenarios`               | array[object] | `[]`   | Bot 专属场景模板。                             |


`daily_life_profile` 常用子字段：


| 字段                         | 类型            | 说明                                            |
| -------------------------- | ------------- | --------------------------------------------- |
| `city_type`                | string        | 城市/生活环境，例如 `一线城市`、`小城市`、`海外城市`。          |
| `commute_mode`             | string        | 通勤方式，例如 `地铁`、`公交`、`步行`、`远程办公`。           |
| `living_status`            | string        | 居住状态，例如 `独居`、`合租`、`和家人住`。                 |
| `work_style`               | string        | 工作/学习方式，例如 `办公室`、`混合办公`、`自由职业`、`学生`。     |
| `hobbies`                  | array[string] | 常见兴趣，例如 `做饭`、`看展`、`跑步`、`阅读`。              |
| `family_contact_style`     | string        | 与家人的联系模式。                                    |
| `social_style`             | string        | 社交风格。                                        |
| `personality_event_bias`   | object        | 按事件类别调权重，例如 `{"solitude": 1.8, "social": 0.7}`。 |


`custom_scenarios[]` 子字段：


| 字段             | 类型            | 说明                                                             |
| -------------- | ------------- | -------------------------------------------------------------- |
| `key`          | string        | 场景唯一 key，建议英文 snake_case。                                      |
| `category`     | string        | 场景类别，例如 `work`、`home`、`social`。                                |
| `templates`    | array[string] | 描述模板。可使用 `{date}`、`{season}`、`{bot_name}`、`{occupation}` 等占位符。 |
| `mood_after`   | string        | 事件后的情绪。                                                        |
| `tags`         | array[string] | 情绪或场景标签。                                                       |
| `topic_prompt` | string        | 主动分享时的话题切入语。                                                   |
| `importance`   | number        | 重要性，0-10。                                                      |
| `shareable`    | boolean       | 是否可分享给用户。                                                      |


系统内置日常场景 key 超过 200 个。下面只列出稳定基础 key 示例；扩展 key 也可以用于 `disabled_scenarios`、`scenario_weights` 或调试。候选选择不会取前 20 个，而是先排除近期/冷却场景，再按性格和生活画像权重随机抽样少量 key 给 LLM：


| key               | 类别          | 说明               |
| ----------------- | ----------- | ---------------- |
| `commute_delay`   | commute     | 通勤延误、绕路。         |
| `lunch_discovery` | food        | 午饭、探店、小吃。        |
| `office_gossip`   | work_social | 茶水间、同事闲聊、办公室小插曲。 |
| `delivery_mixup`  | errand      | 外卖、自提柜、配送乌龙。     |
| `dessert_queue`   | food        | 甜品、排队。           |
| `night_walk`      | health      | 晚间散步、拉伸。         |
| `work_review`     | work        | 工作评审、返工、批注。      |
| `home_repair`     | home        | 家务维修。            |
| `friend_message`  | social      | 朋友消息、旧照片、约饭。     |
| `family_call`     | family      | 家人电话、关心。         |
| `rainy_day`       | weather     | 下雨、天气影响。         |
| `weekend_cleanup` | home        | 周末收纳、洗晒。         |
| `skill_learning`  | growth      | 学习新工具或技能。        |
| `sleep_trouble`   | health      | 睡眠波动、疲惫。         |
| `small_purchase`  | errand      | 小物件、文具、日常购物。     |


系统内置人生大事场景 key（用于冷却和去重；具体描述会结合 Bot 的职业/身份、日期和状态渲染，不限定某一种 Bot）：


| key                            | 说明                         |
| ------------------------------ | -------------------------- |
| `career_offer_signed`          | 正式确认、合同、录用、转岗或职责变化。        |
| `portfolio_project_launched`   | 长期作品、公开项目、主页或主导成果正式发布。     |
| `promotion_or_role_change`     | 被赋予更高职责、带人、主导项目或角色升级。      |
| `major_project_failure`        | 重要任务失败、被否决或退回，并触发复盘和重做。    |
| `moving_home_decision`         | 搬家、签约、换城市或生活结构变化。          |
| `health_turning_point`         | 健康检查、复查、作息问题引发明确调整。        |
| `family_responsibility`        | 家庭医疗、照顾责任或家庭事务重新安排。        |
| `public_recognition`           | 公开认可、分享、奖项、成果被采用或被看见。      |
| `financial_independence`       | 预算、备用金、住房、家庭支出等独立规划。       |
| `relationship_boundary_shift`  | 重要关系中通过谈话、道歉或约定形成新边界。      |
| `unexpected_self_accident`     | 自己遭遇轻伤、急诊、复查等非致命意外。        |
| `unexpected_family_accident`   | 家人急诊、住院观察、陪护或临时返程。         |
| `unexpected_natural_disaster`  | 暴雨、台风、地震预警、断电、临时安置等天灾影响。   |
| `unexpected_public_incident`   | 火警、封站、疏散、警戒线等公共突发事件。       |
| `unexpected_document_loss`     | 证件、银行卡、门禁等遗失后的挂失和补办。       |
| `unexpected_home_emergency`    | 漏水、断电、老旧线路、物业抢修等居住突发。      |
| `unexpected_travel_disruption` | 航班或高铁取消、延误，导致重要安排被打乱。      |
| `unexpected_scam_near_miss`    | 差点遭遇诈骗、报警、冻结账户、重置安全设置。     |
| `birthday`                     | 生日事件。                      |
| `milestone_{age}`              | 年龄里程碑事件，例如 `milestone_25`。 |


## life_state.json

人生轨迹运行状态。由系统写入，通常不建议手改。


| 字段                                  | 类型                    | 说明                                   |
| ----------------------------------- | --------------------- | ------------------------------------ |
| `life_events`                       | array[LifeEvent]      | 日常小事列表，可被裁剪。                         |
| `major_life_events`                 | array[MajorLifeEvent] | 人生大事列表，通常长期保留。                       |
| `life_journal`                      | array[object]         | 每日推进和事件流水，用于审计、排查和回放。                |
| `scenario_history`                  | object                | 日常场景历史，记录每个 `scenario_key` 的最后日期和次数。 |
| `major_scenario_history`            | object                | 人生大事场景历史。                            |
| `bot_mood`                          | string                | 当前情绪。                                |
| `bot_current_activity`              | string                | 当前活动或状态摘要。                           |
| `bot_age_days`                      | number                | Bot 内部经过的天数。                         |
| `last_daily_tick`                   | string/null           | 上次日常 tick 的现实时间 ISO 字符串。             |
| `last_major_tick`                   | string/null           | 上次人生大事 tick 的现实时间 ISO 字符串。           |
| `last_daily_event_date`             | string/null           | 最近一次日常事件对应的 Bot 日期。                  |
| `last_major_event_date`             | string/null           | 最近一次人生大事对应的 Bot 日期。                  |
| `last_major_probability_check_date` | string/null           | 最近一次检查固定概率人生大事的 Bot 日期。              |
| `last_unexpected_event_date`        | string/null           | 最近一次意外类人生大事对应的 Bot 日期，用于整体冷却。        |
| `current_season`                    | string                | 当前季节。                                |
| `current_month`                     | number                | 当前月份。                                |
| `birthday_month`                    | number                | 生日月份。                                |
| `birth_date`                        | string/null           | 出生日期。                                |
| `current_date`                      | string/null           | 当前 Bot 日期。                           |
| `day_of_week`                       | string                | 当前周几。                                |
| `year`                              | number                | 当前年份。                                |
| `is_weekend`                        | boolean               | 是否周末。                                |
| `last_checked_age`                  | number                | 上次检查里程碑时的年龄。                         |
| `triggered_milestones`              | array[number]         | 已触发的里程碑年龄。                           |
| `_initial_age`                      | number/null           | 初始年龄内部记录。                            |
| `_triggered_birthdays`              | array[string]         | 已触发的生日 key，格式通常是 `{year}-birthday`。  |


对话 prompt 会读取 `life_state.json` 的当前日期、出生日期、动态年龄和近期事件；如果这些字段与 `profile.json.age` 冲突，以 `life_state.json` 为准。

`LifeEvent` 字段：


| 字段                  | 类型            | 说明                                                                                          |
| ------------------- | ------------- | ------------------------------------------------------------------------------------------- |
| `id`                | string        | 事件唯一 ID。                                                                                    |
| `timestamp`         | string        | 事件写入现实时间 ISO 字符串。                                                                           |
| `description`       | string        | 事件描述。                                                                                       |
| `mood_before`       | string        | 事件前情绪。                                                                                      |
| `mood_after`        | string        | 事件后情绪。                                                                                      |
| `importance`        | number        | 重要性，0-10。                                                                                   |
| `shareable`         | boolean       | 是否适合主动分享给用户。                                                                                |
| `topic_prompt`      | string        | 分享时的话题切入语。                                                                                  |
| `mood_tags`         | array[string] | 情绪或场景标签。                                                                                    |
| `related_to_user`   | boolean       | 是否与用户直接相关。                                                                                  |
| `context_bits`      | number        | 描述字符数。                                                                                      |
| `scenario_key`      | string        | 场景 key。新事件会写入，旧事件可能为空。                                                                      |
| `scenario_category` | string        | 场景类别。                                                                                       |
| `source`            | string        | 来源，例如 `llm`、`fallback`、`fixed_probability`、`unexpected_probability`、`birthday`、`milestone`。 |


`life_journal[]` 字段：


| 字段            | 类型          | 说明                                        |
| ------------- | ----------- | ----------------------------------------- |
| `id`          | string      | 流水记录 ID。                                  |
| `timestamp`   | string      | 写入现实时间。                                   |
| `record_type` | string      | `day_passed`、`daily_event`、`major_event`。 |
| `date`        | string/null | 对应 Bot 日期。                                |
| `description` | string      | 流水描述。                                     |
| `event_id`    | string      | 关联事件 ID，仅事件流水有。                           |
| `metadata`    | object      | 附加信息，如情绪、场景 key、季节。                       |


## proactive_state.json

主动唤醒运行状态。由系统写入，通常不建议手改。


| 字段                          | 类型          | 说明                       |
| --------------------------- | ----------- | ------------------------ |
| `last_message_time`         | string/null | 用户最后发消息时间。               |
| `last_proactive_time`       | string/null | Bot 最后主动发消息时间。           |
| `annoyance_level`           | number      | 生气/烦躁程度，0-10。            |
| `today_proactive_count`     | number      | 今日已主动发送次数。               |
| `last_reset_date`           | string      | 每日计数重置日期。                |
| `total_proactive_sent`      | number      | 累计主动发送次数。                |
| `last_emotion_trigger_time` | string/null | 最近一次情绪触发时间。              |
| `cooldowns`                 | object      | 触发器冷却状态。                 |
| `last_opening_style`        | string      | 上次使用的开场风格，用于避免重复。        |
| `miss_level`                | number      | 想念程度，0-10。               |
| `insecurity_level`          | number      | 不安全感，0-10。               |
| `excitement_level`          | number      | 兴奋度，0-10。                |
| `last_user_reply_time`      | string/null | 用户最后回复主动消息的时间。           |
| `unreplied_count`           | number      | 主动消息未回复次数。               |
| `user_active_hours`         | object      | 用户活跃小时统计，例如 `{"20": 5}`。 |
| `previous_absence_days`     | number      | 上次冷落天数。                  |
| `just_reactivated`          | boolean     | 是否刚从长期冷落后重新激活。           |


## skill.json

技能元数据，示例位置：`data/bots/_skills/{skill_name}/skill.json`。


| 字段             | 类型            | 必填  | 说明           |
| -------------- | ------------- | --- | ------------ |
| `name`         | string        | 是   | 技能名称。        |
| `version`      | string        | 是   | 技能版本。        |
| `description`  | string        | 否   | 技能描述。        |
| `author`       | string        | 否   | 作者。          |
| `entry`        | string        | 是   | 技能入口文件。      |
| `enabled`      | boolean       | 否   | 是否启用。        |
| `requirements` | array[string] | 否   | Python 依赖列表。 |


## 通用配置示例

给某个 Bot 调整事件权重，并增加一个不绑定职业的专属成长场景：

```json
{
  "event_policy": {
    "scenario_cooldown_days": 14,
    "major_scenario_cooldown_days": 180,
    "unexpected_event_probability": 0.01,
    "unexpected_event_cooldown_days": 365,
    "disabled_scenarios": ["delivery_mixup"],
    "scenario_weights": {
      "work_review": 0.5,
      "skill_practice_breakthrough": 2.0
    },
    "custom_scenarios": [
      {
        "key": "skill_practice_breakthrough",
        "category": "growth",
        "templates": [
          "{date} 晚上练习一个卡了很久的技能，反复试到第三次终于跑通了第一个完整成果。"
        ],
        "mood_after": "有成就感",
        "tags": ["练习", "突破", "成长"],
        "topic_prompt": "今天终于把之前卡住的事情推进了一步。",
        "importance": 4.0,
        "shareable": true
      }
    ]
  }
}
```
