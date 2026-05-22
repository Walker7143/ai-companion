from rich.console import Console
from rich.markup import escape
from rich.prompt import Prompt
import asyncio
import random

# 初始化 readline，确保方向键工作
def _init_readline():
    try:
        import readline
        # 强制加载默认绑定
        readline.parse_and_bind(r'"\e[D": backward-char')
        readline.parse_and_bind(r'"\e[C": forward-char')
        readline.parse_and_bind(r'"\e[A": previous-history')
        readline.parse_and_bind(r'"\e[B": next-history')
    except Exception:
        pass

_init_readline()

from ..bot.manager import BotManager
from ..gateway.sentence_splitter import SentenceSplitter


class CLIAdapter:
    """命令行交互适配器"""

    def __init__(self, bot_manager: BotManager):
        self.bot_manager = bot_manager
        self.console = Console()
        self.current_bot_id: str = None
        self._output_lock = asyncio.Lock()
        self._pending_proactive: list[tuple[str, str]] = []

    async def _read_input(self) -> str:
        """读取用户输入"""
        try:
            line = await asyncio.to_thread(input, "你 ")
            return line.strip()
        except (EOFError, KeyboardInterrupt):
            raise

    async def _safe_print(self, *args, **kwargs):
        async with self._output_lock:
            self.console.print(*args, **kwargs)

    async def _queue_proactive_message(self, bot_name: str, message: str):
        self._pending_proactive.append((bot_name, message))
        return True

    async def _flush_proactive_messages(self):
        if not self._pending_proactive:
            return
        pending = list(self._pending_proactive)
        self._pending_proactive.clear()
        await self._safe_print("[dim]━━━ 主动消息 ━━━[/dim]")
        for bot_name, message in pending:
            await self._safe_print(f"[bold pink]{escape(bot_name)}[/bold pink]: {escape(message)}")
        await self._safe_print("")

    def _install_cli_proactive_queue(self, bot):
        if not bot:
            return
        platform_type = (bot.proactive_config.platform_type or "cli").lower()
        if platform_type != "cli":
            return
        bot.proactive_engine._platform_sender = (
            lambda msg, bot_name=bot.name: self._queue_proactive_message(bot_name, msg)
        )

    async def _select_bot(self):
        bots = self.bot_manager.list_bots()
        if not bots:
            self.console.print("[red]没有可用的 Bot[/red]")
            return None
        self.console.print("[bold]可用 Bot：[/bold]")
        for i, bot in enumerate(bots, 1):
            self.console.print(f"  {i}. {bot['name']} ({bot['id']})")
        self.console.print("")

        while True:
            try:
                choice = await asyncio.to_thread(
                    Prompt.ask,
                    "[bold]选择 Bot 编号",
                    default="1",
                    choices=[str(i) for i in range(1, len(bots) + 1)],
                )
                return bots[int(choice) - 1]["id"]
            except (ValueError, KeyError):
                self.console.print("[red]请输入有效的编号[/red]")

    async def start(self):
        self.console.print("\n[bold green]═══ AI Companion CLI ═══[/bold green]\n")

        bot_id = await self._select_bot()
        if not bot_id:
            return
        self.current_bot_id = bot_id
        bot = self.bot_manager.get_bot(bot_id)
        if bot:
            from ..logging_utils import configure_bot_log_files
            configure_bot_log_files(bot.name)
            self._install_cli_proactive_queue(bot)
            await bot.ensure_schedulers_started()

        await self._safe_print(f"[bold]当前 Bot:[/bold] {escape(bot.name)} ({escape(bot.id)})")
        await self._safe_print(f"[dim]{escape(bot.description)}[/dim]\n")
        await self._safe_print("[dim]输入 quit 退出，输入 switch 切换 Bot[/dim]\n")

        while True:
            user_input = await self._read_input()
            await self._flush_proactive_messages()
            if not user_input:
                continue

            if user_input.lower() in ["quit", "exit", "退出"]:
                await self._safe_print("[dim]再见！[/dim]")
                break

            if user_input.lower() in ["switch", "切换"]:
                bot_id = await self._select_bot()
                if bot_id:
                    self.current_bot_id = bot_id
                    bot = self.bot_manager.get_bot(bot_id)
                    if bot:
                        from ..logging_utils import configure_bot_log_files
                        configure_bot_log_files(bot.name)
                        self._install_cli_proactive_queue(bot)
                        await bot.ensure_schedulers_started()
                    await self._safe_print(f"\n[bold]切换到:[/bold] {escape(bot.name)}\n")
                continue

            if user_input.lower() in ["reset", "重置"]:
                bot.reset_history()
                await self._safe_print("[dim]对话历史已清空[/dim]\n")
                continue

            # /new — 新会话
            if user_input.strip() == "/new":
                bot.reset_history()
                await self._safe_print("[dim]已开启新会话[/dim]\n")
                continue

            # /memory — 查看记忆状态
            if user_input.strip() == "/memory":
                if bot.memory:
                    status = await bot.memory.get_memory_status()
                    await self._safe_print("[bold]━━━ 记忆状态 ━━━[/bold]")
                    await self._safe_print(f"  会话ID: {status['session_id']}")
                    await self._safe_print(f"  工作记忆轮数: {status['working_turns']}")
                    await self._safe_print(f"  已压缩次数: {status['compression_count']}")
                    await self._safe_print(f"  情景记忆条数: {status['episodic_count']}")
                    await self._safe_print(f"  语义记忆事实数: {status['fact_count']}")
                    if status.get("vector_count") is not None:
                        await self._safe_print(f"  向量记忆索引数: {status['vector_count']}")
                    relationship = status.get("relationship") or {}
                    if relationship:
                        label = relationship.get("relationship_label", "朋友")
                        score = float(relationship.get("relationship_score") or 0)
                        await self._safe_print(f"  关系状态: {label}（综合 {score:.0f}/100）")
                        await self._safe_print(
                            "  关系维度: "
                            f"亲密 {float(relationship.get('intimacy_score') or 0):.0f} / "
                            f"信任 {float(relationship.get('trust_score') or 0):.0f} / "
                            f"好感 {float(relationship.get('affection_score') or 0):.0f} / "
                            f"紧张 {float(relationship.get('tension_score') or 0):.0f}"
                        )
                    if status.get("user_understanding_path"):
                        await self._safe_print(f"  用户理解文件: {status['user_understanding_path']}")
                        await self._safe_print(f"  自动补充事实数: {status.get('user_understanding_auto_facts', 0)}")
                    trust = status.get("memory_trust_view") or {}
                    if trust:
                        relationship_anchor = trust.get("relationship_anchor") or {}
                        if relationship_anchor.get("narrative"):
                            await self._safe_print("[bold]━━━ 记忆信任视图 ━━━[/bold]")
                            await self._safe_print(f"  关系锚点: {escape(str(relationship_anchor.get('narrative') or ''))}")
                        recent = trust.get("recently_remembered") or []
                        if recent:
                            await self._safe_print("  最近正在记住:")
                            for item in recent[:5]:
                                await self._safe_print(f"    - {escape(str(item.get('key') or ''))}: {escape(str(item.get('value') or ''))}")
                        stable = trust.get("stable_understanding") or []
                        if stable:
                            await self._safe_print("  稳定理解:")
                            for item in stable[:5]:
                                confirmed = " ✓" if item.get("confirmed") else ""
                                await self._safe_print(f"    - {escape(str(item.get('key') or ''))}: {escape(str(item.get('value') or ''))}{confirmed}")
                        pending = trust.get("pending_confirmation") or []
                        if pending:
                            await self._safe_print("  可能需要确认:")
                            for item in pending[:5]:
                                confidence = item.get("confidence")
                                confidence_text = f" ({float(confidence):.2f})" if isinstance(confidence, (int, float)) else ""
                                await self._safe_print(f"    - {escape(str(item.get('key') or ''))}: {escape(str(item.get('value') or ''))}{confidence_text}")
                        corrected = trust.get("corrected_memories") or []
                        if corrected:
                            await self._safe_print("  最近已纠正:")
                            for item in corrected[:5]:
                                await self._safe_print(
                                    f"    - {escape(str(item.get('key') or ''))}: "
                                    f"{escape(str(item.get('old_value') or ''))} -> {escape(str(item.get('new_value') or ''))}"
                                )
                        archived = trust.get("archived_or_suppressed") or []
                        if archived:
                            await self._safe_print("  已归档/压制:")
                            for item in archived[:5]:
                                await self._safe_print(
                                    f"    - {escape(str(item.get('key') or ''))}: "
                                    f"{escape(str(item.get('action') or ''))} / {escape(str(item.get('reason') or ''))}"
                                )
                    health = status.get('health', {})
                    if health.get('reason'):
                        await self._safe_print(f"  状态: {health['reason']}")
                else:
                    await self._safe_print("[dim]记忆引擎未启用[/dim]")
                await self._safe_print("")
                continue

            # /forget <key> — 删除语义记忆
            if user_input.strip().startswith("/forget "):
                key = user_input.strip()[8:].strip()
                if not key:
                    await self._safe_print("[red]/forget 需要指定 key，例如: /forget occupation[/red]\n")
                elif bot.memory:
                    await bot.memory.forget_fact(key)
                    await self._safe_print(f"[dim]已删除语义记忆: {escape(key)}[/dim]\n")
                else:
                    await self._safe_print("[dim]记忆引擎未启用[/dim]\n")
                continue

            # /dream — 记忆整理
            if user_input.strip().startswith("/dream"):
                if not bot.memory or not getattr(bot.memory, "dreaming", None):
                    await self._safe_print("[dim]记忆整理未启用[/dim]\n")
                    continue
                action = user_input.strip()[6:].strip().lower()
                action = action or "status"
                dreaming = bot.memory.dreaming
                if action == "on":
                    await dreaming.set_enabled(True)
                    await self._safe_print("[dim]已开启记忆整理[/dim]\n")
                    continue
                if action == "off":
                    await dreaming.set_enabled(False)
                    await self._safe_print("[dim]已关闭记忆整理[/dim]\n")
                    continue
                if action == "run":
                    result = await dreaming.run(trigger_source="cli", trigger_reason="/dream run")
                    report = result.get("report") or {}
                    await self._safe_print("[bold]━━━ 记忆整理结果 ━━━[/bold]")
                    await self._safe_print(report.get("user_summary") or "本次未产出可展示摘要。")
                    await self._safe_print("")
                    continue
                if action == "doctor":
                    doctor = await dreaming.doctor_status()
                    await self._safe_print("[bold]━━━ 记忆整理诊断 ━━━[/bold]")
                    await self._safe_print(f"  状态: {'正常' if doctor.get('ok') else '需要关注'}")
                    for issue in doctor.get("issues") or []:
                        await self._safe_print(f"  问题: {escape(str(issue))}")
                    for item in doctor.get("suggestions") or []:
                        await self._safe_print(f"  建议: {escape(str(item))}")
                    await self._safe_print("")
                    continue
                if action == "report":
                    report = await dreaming.latest_report()
                    await self._safe_print("[bold]━━━ 最近整理报告 ━━━[/bold]")
                    await self._safe_print(escape(str((report or {}).get("user_summary") or "最近还没有整理报告。")))
                    await self._safe_print("")
                    continue
                if action == "delete":
                    deleted = await dreaming.delete_latest_promotions()
                    await self._safe_print("[bold]━━━ 删除最近整理新增项 ━━━[/bold]")
                    await self._safe_print(escape(str(deleted)))
                    await self._safe_print("")
                    continue
                status = await dreaming.status()
                await self._safe_print("[bold]━━━ 记忆整理状态 ━━━[/bold]")
                await self._safe_print(f"  开关: {'开启' if status.get('enabled') else '关闭'}")
                await self._safe_print(f"  自动运行: {'开启' if status.get('auto_run_enabled') else '关闭'}")
                await self._safe_print(f"  最近状态: {status.get('last_status') or '暂无'}")
                await self._safe_print(f"  最近运行时间: {status.get('last_run_at') or '暂无'}")
                if status.get("last_error"):
                    await self._safe_print(f"  最近错误: {escape(str(status.get('last_error')))}")
                latest_report = status.get("latest_report") or {}
                if latest_report.get("user_summary"):
                    await self._safe_print(f"  最近摘要: {escape(str(latest_report.get('user_summary')))}")
                await self._safe_print("")
                continue

            try:
                bot = self.bot_manager.get_bot(self.current_bot_id)
                memory_turn_context = {
                    "platform": "cli",
                    "session_id": getattr(getattr(bot, "memory", None), "_session_id", None),
                    "user_id": getattr(getattr(bot, "memory", None), "user_id", "default_user"),
                    "channel_type": "local",
                }
                response = await bot.handle_message(user_input, memory_turn_context=memory_turn_context)
                sentences = SentenceSplitter.split(response)
                if sentences:
                    # Print bot name prefix only before the first sentence
                    await self._safe_print(f"[bold pink]{escape(bot.name)}[/bold pink]: {escape(sentences[0])}")
                    for i in range(1, len(sentences)):
                        # Random delay between sentences (1-2 seconds)
                        await asyncio.sleep(random.uniform(1.0, 2.0))
                        await self._safe_print(escape(sentences[i]))
                    await self._safe_print("")  # Blank line after response
                else:
                    await self._safe_print(f"[bold pink]{escape(bot.name)}[/bold pink]:\n")
            except Exception as e:
                await self._safe_print(f"[red]Error:[/red] {escape(str(e))}\n")
