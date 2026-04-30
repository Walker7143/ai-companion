from __future__ import annotations

import argparse
import asyncio
import os
from datetime import datetime
from pathlib import Path

from rich.console import Console

from ai_companion.config.loader import Config
from ai_companion.model.factory import ModelFactory

from .apply import apply_draft
from .paths import resolve_book_path
from .pipeline import PersonaImportPipeline
from .review import print_draft_summary
from .schema import ImportOptions, parse_character_spec

console = Console()


def add_persona_parser(subparsers) -> None:
    persona_parser = subparsers.add_parser("persona", help="Persona 导入与审核")
    persona_subparsers = persona_parser.add_subparsers(dest="persona_command")

    import_book = persona_subparsers.add_parser("import-book", help="从单本书导入多个角色 persona 草稿")
    import_book.add_argument("--book", required=True, help="书籍文件，支持 txt/md/html/epub，PDF 需可选 pypdf")
    import_book.add_argument(
        "--character",
        action="append",
        required=True,
        help="目标角色。格式：角色名、角色名=别名1,别名2、bot_id:角色名=别名1,别名2。可重复。",
    )
    import_book.add_argument("--out", help="草稿输出目录，默认 ~/.ai-companion/imports/<book>-<timestamp>")
    import_book.add_argument("--provider", help="覆盖 models.yaml 中的默认模型 provider")
    import_book.add_argument("--chunk-chars", type=int, default=6000, help="每个书籍分块字符数")
    import_book.add_argument("--overlap-chars", type=int, default=600, help="分块重叠字符数")
    import_book.add_argument("--merge-batch-chars", type=int, default=24000, help="角色档案合并批次字符上限")
    import_book.add_argument("--max-concurrency", type=int, default=1, help="并发 LLM 请求数")
    import_book.add_argument("--requests-per-minute", type=float, default=0, help="独立限流：每分钟最多发起多少次 LLM 请求，0 表示不额外限制")
    import_book.add_argument("--retry-attempts", type=int, default=3, help="每次 LLM JSON 调用的最大尝试次数")
    import_book.add_argument("--retry-base-delay", type=float, default=2.0, help="失败重试基础等待秒数，按指数退避")
    import_book.add_argument("--no-resume", action="store_true", help="禁用断点续跑，重新抽取所有选中分块")
    import_book.add_argument("--max-chunks", type=int, help="最多处理多少个命中分块，便于试跑")
    import_book.add_argument("--skip-alias-filter", action="store_true", help="不按角色名过滤，整本书所有分块都送入抽取")
    import_book.add_argument("--no-neighbor-chunks", action="store_true", help="不附带命中分块的相邻分块")
    import_book.add_argument("--plan-only", action="store_true", help="只生成分块/命中计划，不调用模型")

    review = persona_subparsers.add_parser("review", help="查看 persona 导入草稿摘要")
    review.add_argument("draft_dir", help="import-book 生成的草稿目录")

    apply = persona_subparsers.add_parser("apply", help="审核后把草稿应用为正式 Bot")
    apply.add_argument("draft_dir", help="import-book 生成的草稿目录")
    apply.add_argument("--bot-id", action="append", help="只应用指定 bot_id，可重复")
    apply.add_argument("--data-dir", help="Bot 数据根目录，默认 ~/.ai-companion/data/bots")
    apply.add_argument("--config-dir", help="配置目录，默认 ~/.ai-companion/config")
    apply.add_argument("--overwrite", action="store_true", help="覆盖已有 persona 文件，覆盖前会备份")
    apply.add_argument("--no-register", action="store_true", help="不更新 bots.yaml")
    apply.add_argument("-y", "--yes", action="store_true", help="跳过 APPLY 确认")


def handle_persona_command(command: str | None, args: argparse.Namespace) -> None:
    if command == "import-book":
        asyncio.run(_handle_import_book(args))
    elif command == "review":
        console.print(print_draft_summary(Path(args.draft_dir).expanduser().resolve()))
    elif command == "apply":
        result = apply_draft(
            Path(args.draft_dir),
            data_dir=Path(args.data_dir) if args.data_dir else None,
            config_dir=Path(args.config_dir) if args.config_dir else None,
            bot_ids=args.bot_id,
            overwrite=args.overwrite,
            register_bots=not args.no_register,
            yes=args.yes,
        )
        console.print(f"[green]已应用 Bot:[/green] {', '.join(result.applied_bot_ids)}")
        console.print(f"数据目录: {result.data_dir}")
        if result.updated_bots_yaml:
            console.print(f"已更新配置: {result.config_dir / 'bots.yaml'}")
        for backup in result.backups:
            console.print(f"备份: {backup}")
    else:
        console.print("请指定 persona 子命令：import-book / review / apply")


async def _handle_import_book(args: argparse.Namespace) -> None:
    book_path = resolve_book_path(args.book)
    output_dir = Path(args.out).expanduser().resolve() if args.out else _default_output_dir(book_path)
    characters = [parse_character_spec(spec) for spec in args.character]

    options = ImportOptions(
        book_path=book_path,
        characters=characters,
        output_dir=output_dir,
        chunk_chars=args.chunk_chars,
        overlap_chars=args.overlap_chars,
        merge_batch_chars=args.merge_batch_chars,
        max_concurrency=args.max_concurrency,
        requests_per_minute=args.requests_per_minute,
        retry_attempts=args.retry_attempts,
        retry_base_delay_seconds=args.retry_base_delay,
        resume=not args.no_resume,
        max_chunks=args.max_chunks,
        include_neighbor_chunks=not args.no_neighbor_chunks,
        skip_alias_filter=args.skip_alias_filter,
        plan_only=args.plan_only,
    )

    model = None
    if not args.plan_only:
        model = _create_model(args.provider)
    try:
        pipeline = PersonaImportPipeline(model=model, options=options)
        manifest = await pipeline.run()
    finally:
        if model is not None:
            await model.close()

    console.print(f"[green]导入草稿已生成:[/green] {output_dir}")
    console.print(f"书籍分块: {manifest.get('chunks', {}).get('selected', 0)} / {manifest.get('chunks', {}).get('total', 0)}")
    if args.plan_only:
        console.print(f"分块计划: {output_dir / 'chunk_plan.json'}")
    else:
        console.print(f"审核报告: {output_dir / 'review.md'}")
        console.print(f"审核后应用: ai-companion persona apply {output_dir}")


def _default_output_dir(book_path: Path) -> Path:
    timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    safe_stem = "".join(ch if ch.isalnum() or ch in "-_" else "_" for ch in book_path.stem).strip("_")
    if not safe_stem:
        safe_stem = "book"
    return Path.home() / ".ai-companion" / "imports" / f"{safe_stem}-{timestamp}"


def _create_model(provider: str | None):
    config = Config()
    model_cfg = config.get_model_config(provider)
    selected_provider = model_cfg.get("provider", provider or config.default_provider)
    env_key_map = {
        "minimax": "MINIMAX_API_KEY",
        "openai": "OPENAI_API_KEY",
        "claude": "ANTHROPIC_API_KEY",
    }
    env_key = env_key_map.get(selected_provider)
    api_key = os.environ.get(env_key, "") if env_key else ""
    if not api_key:
        api_key = model_cfg.get("api_key", "")

    if env_key and (not api_key or str(api_key).startswith("${")):
        raise RuntimeError(f"{selected_provider} API Key 未配置，请设置 {env_key} 或运行 ai-companion setup")

    return ModelFactory.create_from_runtime_config(
        model_config=model_cfg,
        provider=selected_provider,
        api_key=api_key if env_key else None,
    )
