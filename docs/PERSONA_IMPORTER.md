# Persona Importer

`persona_importer` 用于把单本书中的多个角色抽取成可审核的 Bot persona 草稿。它不是一次把整本书塞进上下文，而是按分块抽取证据，再按角色合并成紧凑档案，最后生成本项目使用的 persona JSON。

## 目标

- 单本书，多角色。
- 支持长文本，不依赖一次性大上下文。
- 生成 `profile.json`、`backstory.json`、`values.json`、`speaking_style.json`、`conversation_style_rules.json`。
- 默认只写入导入草稿，不覆盖正式 Bot。
- 输出 `run.log`、`review.md`、`dossier.json`、`extractions.jsonl`，方便人工审核、追溯证据和恢复长任务。

## 流水线

```text
book txt/md/html/epub/pdf
        |
        v
章节识别 + 字符分块
        |
        v
按角色名/别名命中分块，可附带相邻分块
        |
        v
Chunk Extractor
只抽取事实、事件、性格推断、关系、说话风格、价值观和不确定点
        |
        v
Character Dossier Merger
按角色合并成紧凑档案，保留 evidence_index
        |
        v
Persona Generator
生成项目 persona JSON 草稿
        |
        v
人工审核 review.md
        |
        v
persona apply 写入 ~/.ai-companion/data/bots/{bot_id}/persona
```

## 命令

先看分块计划，不调用模型：

```bash
ai-companion persona import-book \
  --book ./books/book.txt \
  --character "lin_daiyu:林黛玉=黛玉,林妹妹" \
  --character "xue_baochai:薛宝钗=宝钗" \
  --plan-only
```

正式生成草稿：

```bash
ai-companion persona import-book \
  --book ./books/book.txt \
  --character "lin_daiyu:林黛玉=黛玉,林妹妹" \
  --character "xue_baochai:薛宝钗=宝钗" \
  --chunk-chars 6000 \
  --overlap-chars 600 \
  --max-concurrency 1 \
  --requests-per-minute 20 \
  --retry-attempts 3
```

`--book` 是本地文件路径，支持：

```text
./books/book.txt
/Users/me/books/book.txt
~/books/book.txt
$BOOK_DIR/book.txt
file:///Users/me/books/book.txt
```

路径里有空格时需要加引号：

```bash
ai-companion persona import-book \
  --book "/Users/me/My Books/book.txt" \
  --character "lin_daiyu:林黛玉=黛玉"
```

查看草稿摘要：

```bash
ai-companion persona review ~/.ai-companion/imports/book-20260430-150000
```

审核通过后应用：

```bash
ai-companion persona apply ~/.ai-companion/imports/book-20260430-150000
```

覆盖已有 Bot 时会先备份：

```bash
ai-companion persona apply ~/.ai-companion/imports/book-20260430-150000 \
  --bot-id lin_daiyu \
  --overwrite
```

## 角色参数格式

`--character` 可重复使用。

```text
角色名
角色名=别名1,别名2
bot_id:角色名=别名1,别名2
```

如果没有显式 `bot_id`，英文/数字名称会转成简短 ID；中文名称会生成稳定的 `role_<hash>` ID。建议实际使用时显式指定 `bot_id`。

## 输出目录

默认输出到：

```text
~/.ai-companion/imports/<book-name>-<timestamp>/
```

目录结构：

```text
manifest.json
chunk_plan.json
extractions.jsonl
run.log
review.md
characters/
  <bot_id>/
    dossier.json
    persona_raw.json
    persona/
      profile.json
      backstory.json
      values.json
      speaking_style.json
      conversation_style_rules.json
```

## 审核重点

- 不要把模型推断直接当作事实，低把握内容应改写为倾向或删除。
- 删除或改写过于贴近原文的台词、口头禅和长表达。
- 检查 `relationship_to_user`，书中角色与用户通常没有原始关系，需要改写成合理的 Bot 初始关系。
- 多角色之间的关系可以保留在背景里，但不要让它压过与用户的关系。
- 检查年龄、职业、当前状态是否适合项目内的人生轨迹系统。

## 长文本策略

`chunk_chars` 控制单次抽取上下文，默认 6000 字符。`overlap_chars` 保留相邻分块重叠，降低事件断裂风险。默认只把命中目标角色姓名或别名的分块送给模型，并附带相邻分块帮助处理代词和上下文延续。

如果别名不完整，可能漏掉大量内容。可以先用 `--plan-only` 看命中数量，必要时增加别名，或使用 `--skip-alias-filter` 让整本书所有分块进入抽取流程。

## 长任务、限流和重试

默认行为适合慢速稳定跑长书：

- `--max-concurrency 1`：并发 LLM 请求数，默认 1。
- `--requests-per-minute 0`：额外 RPM 限流，0 表示不额外限制；例如 `20` 表示每分钟最多启动 20 次 LLM 请求。
- `--retry-attempts 3`：每次 LLM JSON 调用最多尝试 3 次。
- `--retry-base-delay 2`：重试等待使用指数退避，默认约 2 秒、4 秒、8 秒。
- 默认启用断点续跑；同一草稿目录中 `extractions.jsonl` 已有成功结果的 chunk 会跳过，不重复请求 LLM。
- `--no-resume`：禁用断点续跑，重新抽取所有选中 chunk。

建议长书固定 `--out`，中断后用同一命令和同一输出目录重跑：

```bash
ai-companion persona import-book \
  --book ./books/book.txt \
  --character "lin_daiyu:林黛玉=黛玉,林妹妹" \
  --out ~/.ai-companion/imports/red-mansion \
  --requests-per-minute 20
```

如果进程中断，再执行同一命令即可复用已经成功的 chunk 抽取结果。

## 日志

每次导入都会在草稿目录写入：

```text
run.log
```

`run.log` 是 JSONL，一行一个事件，包含：

- `import_start` / `import_complete`
- `plan_complete`
- `resume_loaded`
- `chunk_extract_start` / `chunk_extract_success` / `chunk_extract_failed`
- `chunk_skip_completed`
- `llm_call_start` / `llm_call_success` / `llm_call_error`
- `llm_retry_sleep`
- `dossier_merge_start` / `dossier_merge_success`
- `persona_generate_start` / `persona_generate_success`

证据结果仍以 `extractions.jsonl`、`dossier.json` 和 `persona_raw.json` 为准。`run.log` 记录运行过程、耗时、失败和重试，便于排查长任务。

## 支持格式

- 内置支持：`txt`、`md`、`html`、`epub`
- PDF：需要可选依赖 `pypdf`，且只适合可抽取文本的 PDF

## 版权边界

导入器的目标是抽象角色经历、性格和表达规律，不是复刻原文。提示词会限制长引文，并要求生成 persona 时改写短句。对外发布 Bot 前，应再次人工检查，避免复制原文台词和高度相似表达。
