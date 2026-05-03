from __future__ import annotations

import asyncio
import logging
import os
from pathlib import Path

import discord
from discord import app_commands

from .adapters import create_adapter
from .config import load_agent_configs
from .discord import (
    DiscordBotState,
    build_agent_settings_message,
    build_help_message,
    build_onboarding_message,
    build_status_message,
    execute_discord_command,
    format_agent_timeline_message,
    format_approval_needed_message,
    format_run_complete_message,
    format_handoff_message,
    parse_discord_command,
    publish_collaboration_live,
    build_workspace_from_env,
    _slugify,
)
from .workflow import run_design_review, finalize_collaboration, DesignReviewStage
from .prototype import generate_playable_prototype
from .github_pr import create_game_pr, PRResult

LOGGER = logging.getLogger(__name__)

ROLE_LABELS = {
    "creative_designer": "Designer",
    "technical_reviewer": "Reviewer",
    "product_ceo": "CEO",
    "spec_writer": "Writer",
}

ROLE_KEYWORDS = {
    "designer": "creative_designer",
    "디자이너": "creative_designer",
    "reviewer": "technical_reviewer",
    "리뷰어": "technical_reviewer",
    "ceo": "product_ceo",
    "writer": "spec_writer",
    "라이터": "spec_writer",
}


class LiveDiscordPublisher:
    def __init__(self, guild: discord.Guild, category_name: str) -> None:
        self.guild = guild
        self.category_name = category_name
        self._category: discord.CategoryChannel | None = None
        self._channel_cache: dict[str, discord.TextChannel] = {}
        self._thread_cache: dict[tuple[str, str], discord.Thread] = {}

    async def send_message(self, channel_name: str, thread_name: str, content: str, view: discord.ui.View | None = None) -> None:
        channel = await self._get_or_create_text_channel(channel_name)
        thread = await self._get_or_create_thread(channel, thread_name)
        chunks = _chunk_message(content)
        for index, chunk in enumerate(chunks):
            await thread.send(chunk, view=view if index == len(chunks) - 1 else None)

    async def _get_or_create_text_channel(self, channel_name: str) -> discord.TextChannel:
        cached = self._channel_cache.get(channel_name)
        if cached is not None:
            return cached
        for channel in self.guild.text_channels:
            if channel.name == channel_name:
                self._channel_cache[channel_name] = channel
                return channel
        category = await self._get_or_create_category()
        created = await self.guild.create_text_channel(channel_name, category=category)
        self._channel_cache[channel_name] = created
        return created

    async def _get_or_create_category(self) -> discord.CategoryChannel:
        if self._category is not None:
            return self._category
        for category in self.guild.categories:
            if category.name == self.category_name:
                self._category = category
                return category
        self._category = await self.guild.create_category(self.category_name)
        return self._category

    async def _get_or_create_thread(self, channel: discord.TextChannel, thread_name: str) -> discord.Thread:
        cache_key = (channel.name, thread_name)
        cached = self._thread_cache.get(cache_key)
        if cached is not None:
            return cached
        for thread in channel.threads:
            if thread.name == thread_name:
                self._thread_cache[cache_key] = thread
                return thread
        seed = await channel.send(f"Opening thread `{thread_name}` for Orchestra.")
        thread = await seed.create_thread(name=thread_name, auto_archive_duration=1440)
        self._thread_cache[cache_key] = thread
        return thread

class InterventionModal(discord.ui.Modal, title="게임 기획 피드백"):
    feedback = discord.ui.TextInput(
        label="어떤 부분을 수정할까요?",
        style=discord.TextStyle.paragraph,
        placeholder="예: 시간 제한을 30초로 줄이고 장애물을 추가해줘",
        required=True
    )

    def __init__(self, bot: "OrchestraDiscordBot", run_key: str):
        super().__init__()
        self.bot = bot
        self.run_key = run_key

    async def on_submit(self, interaction: discord.Interaction):
        await interaction.response.send_message("✅ 피드백을 반영하여 명세서와 프로토타입을 생성합니다...", ephemeral=True)
        await self.bot._run_finalize(interaction, self.run_key, self.feedback.value)

class InterventionView(discord.ui.View):
    def __init__(self, bot: "OrchestraDiscordBot", run_key: str):
        super().__init__(timeout=3600)
        self.bot = bot
        self.run_key = run_key

    @discord.ui.button(label="이대로 진행 (Approve)", style=discord.ButtonStyle.green, emoji="✅")
    async def approve(self, interaction: discord.Interaction, button: discord.ui.Button):
        for child in self.children:
            child.disabled = True
        await interaction.response.edit_message(content="✅ **이대로 진행합니다!** 최종 명세와 프로토타입을 생성 중...", view=self)
        await self.bot._run_finalize(interaction, self.run_key, "")

    @discord.ui.button(label="피드백 주고 수정 (Revise)", style=discord.ButtonStyle.primary, emoji="✏️")
    async def revise(self, interaction: discord.Interaction, button: discord.ui.Button):
        modal = InterventionModal(self.bot, self.run_key)
        await interaction.response.send_modal(modal)

    async def on_timeout(self):
        for child in self.children:
            child.disabled = True


class OrchestraDiscordBot(discord.Client):
    def __init__(self) -> None:
        intents = discord.Intents.default()
        intents.message_content = True
        intents.guilds = True
        intents.messages = True
        super().__init__(intents=intents)
        self.tree = app_commands.CommandTree(self)
        self.guild_states: dict[int, DiscordBotState] = {}
        from typing import Any
        self.pending_stages: dict[str, tuple[DesignReviewStage, Any, dict[str, str]]] = {}
        self.thread_context_cache: dict[str, str] = {}
        self.artifact_root = Path(os.environ.get("DISCORD_ARTIFACT_ROOT", "artifacts/discord"))
        self.artifact_root.mkdir(parents=True, exist_ok=True)
        self._register_slash_commands()

    def state_for(self, guild_id: int) -> DiscordBotState:
        if guild_id not in self.guild_states:
            self.guild_states[guild_id] = DiscordBotState()
        return self.guild_states[guild_id]

    def get_effective_env(self, guild_id: int) -> dict[str, str]:
        env = dict(os.environ)
        state = self.state_for(guild_id)
        if state.server_config.get("ollama_base_url"):
            env["OLLAMA_BASE_URL"] = state.server_config["ollama_base_url"]
        if state.server_config.get("preset"):
            env["AGENT_PRESET"] = state.server_config["preset"]
        for key, value in state.api_keys.items():
            env[key] = value
        # 학습된 규칙을 LEARNED_RULES 환경 변수로 주입
        from .knowledge import load_all_rules
        project_name = ""
        if state.last_run:
            project_name = state.last_run.get("idea", "")
        knowledge = load_all_rules(self.artifact_root, project_name)
        learned_text = knowledge.format_for_prompt()
        if learned_text:
            env["LEARNED_RULES"] = learned_text
        return env

    async def setup_hook(self) -> None:
        await self.tree.sync()
        LOGGER.info("Bot setup complete, global slash commands synced.")

    async def on_ready(self) -> None:
        LOGGER.info("Logged in as %s", self.user)

    async def on_guild_join(self, guild: discord.Guild) -> None:
        try:
            docs_channel = discord.utils.get(guild.text_channels, name="tutti-docs")
            if not docs_channel:
                docs_channel = await guild.create_text_channel("tutti-docs")
            
            embed1 = discord.Embed(
                title="🎮 Tutti: 멀티 에이전트 게임 기획 봇",
                description="AI 에이전트 4명이 협력하여 게임을 기획하고, 사용자가 실시간으로 개입하며, 프로토타입 생성 + GitHub PR까지 자동화하는 디스코드 봇입니다.",
                color=0x5865F2
            )
            embed1.add_field(
                name="🤖 에이전트 구조",
                value="**1. 🎨 Designer**: 게임 컨셉 기획\n"
                      "**2. 🛠️ Reviewer**: 기술 검토 & 엣지 케이스\n"
                      "**3. 💼 CEO**: 시장성 평가 + 위험도(Risk) 판단\n"
                      "**4. 👨‍💻 Human (사용자)**: 승인/피드백 결재\n"
                      "**5. ✍️ Writer**: 최종 명세서 작성\n"
                      "**6. 🚀 Prototype**: HTML/JS 미니게임 자동 생성",
                inline=False
            )
            embed1.add_field(
                name="✨ 핵심 기능",
                value="**⚡ 위험도 기반 자율 승인**\n"
                      "CEO가 Risk를 LOW/MEDIUM/HIGH로 판단합니다.\n"
                      "LOW는 즉시 자동 승인, MEDIUM은 15초 후 자동 진행, HIGH만 사람이 결재합니다.\n\n"
                      "**🧠 에이전트 학습 (`/tutti learn`)**\n"
                      "규칙을 학습시키면 이후 모든 기획에 자동 반영됩니다.\n"
                      "(예: `/tutti learn \"게임 오버 시 반드시 재시작 버튼 포함\"`)\n\n"
                      "**🔗 GitHub PR 자동 생성**\n"
                      "기획 완료 시 산출물을 GitHub 레포에 자동 커밋 + PR 생성합니다.\n"
                      "`/tutti github` 로 설정 가이드를 확인하세요.\n\n"
                      "**💬 쓰레드 에이전트 멘션**\n"
                      "쓰레드에서 `@디자이너`, `@리뷰어`, `@ceo`, `@라이터`로 브레인스토밍 가능",
                inline=False
            )

            embed2 = discord.Embed(color=0x2ECC71)
            embed2.add_field(
                name="⌨️ 명령어 가이드",
                value="`/tutti start` - 게임 기획 시작 (name + idea 입력)\n"
                      "`/tutti revise` - 마지막 기획 수정\n"
                      "`/tutti learn` - 에이전트에게 규칙 학습\n"
                      "`/tutti rules` - 학습된 규칙 목록 확인\n"
                      "`/tutti forget` - 규칙 삭제\n"
                      "`/tutti github` - GitHub PR 연동 설정 가이드\n"
                      "`/tutti settings` - 모델/서버/GitHub 설정\n"
                      "`/tutti apikey` - API 키 등록 (DM)\n"
                      "`/tutti status` - 현재 상태 확인",
                inline=False
            )
            embed2.add_field(
                name="⚠️ 기술적 한계 및 보완",
                value="로컬 `qwen2.5-coder` 모델은 복잡한 게임 생성 시 불안정할 수 있습니다.\n"
                      "**안전망 아키텍처**(CSS 강제 주입, 로직 분리 프롬프트)로 보완합니다.\n"
                      "`/tutti settings`에서 GPT-4o/Sonnet으로 교체 시 즉시 고품질 출력.",
                inline=False
            )

            await docs_channel.send(embeds=[embed1, embed2])
        except Exception as exc:
            LOGGER.error("Failed to create docs channel or send guide: %s", exc)

        channel = _find_writable_channel(guild)
        if channel is None:
            return
        await channel.send(
            build_onboarding_message(
                mode=os.environ.get("AGENT_MODE", "mock"),
                model=os.environ.get("DESIGNER_MODEL", "mock"),
            ),
            view=OnboardingView(self),
        )

    async def on_message(self, message: discord.Message) -> None:
        if message.author == self.user or not message.guild:
            return
        content = message.content.strip()
        if not isinstance(message.channel, discord.Thread) and (
            content.startswith("/orchestra ") or content.startswith("!orchestra ")
        ):
            await self._handle_prefix_command(message, content)
            return
        if isinstance(message.channel, discord.Thread):
            await self._handle_thread_message(message)

    async def _handle_prefix_command(self, message: discord.Message, content: str) -> None:
        normalized = content
        if normalized.startswith("!orchestra "):
            normalized = "/orchestra " + normalized[len("!orchestra "):]
        
        command = parse_discord_command(normalized)
        if command.group in {"help", "status"}:
            result = await asyncio.to_thread(
                execute_discord_command, command,
                self.state_for(message.guild.id),
                self.get_effective_env(message.guild.id),
                self.artifact_root,
            )
            await message.channel.send(result.message)
            return
            
        await message.channel.send("⚠️ 텍스트 명령어(!orchestra start) 대신 슬래시 명령어 **`/tutti start`** 를 사용해 주세요. 더 깔끔한 UI와 기능을 제공합니다.")

    async def _handle_thread_message(self, message: discord.Message) -> None:
        thread = message.channel
        if not (thread.name.startswith("run-") or thread.name.startswith("task-")):
            return
        if not message.guild:
            return
        if not self._should_respond_to_thread_message(message):
            return
        env = self.get_effective_env(message.guild.id)
        context = await self._build_thread_context(thread)
        agent_id = self._detect_agent(message.content, thread, context=context)
        configs = load_agent_configs(env)
        agents = configs.by_id
        agent_config = agents[agent_id]
        adapter = create_adapter(agent_config, env)
        async with thread.typing():
            try:
                response = await asyncio.to_thread(
                    adapter.generate, "chat", message.content, context=context,
                )
            except Exception as exc:
                await thread.send(f"Agent response failed: {exc}")
                return
        label = ROLE_LABELS.get(agent_id, agent_id)
        for chunk in _chunk_message(f"**{label}** `{agent_config.provider}/{agent_config.model}`\n\n{response}"):
            await thread.send(chunk)

    def _should_respond_to_thread_message(self, message: discord.Message) -> bool:
        if _mentions_user(message, self.user):
            return True
        content = message.content.strip().lower()
        explicit_prefixes = (
            "designer:", "designer ", "@designer ", "@designer:",
            "디자이너:", "디자이너 ", "@디자이너 ", "@디자이너:",
            "reviewer:", "reviewer ", "@reviewer ", "@reviewer:",
            "리뷰어:", "리뷰어 ", "@리뷰어 ", "@리뷰어:",
            "ceo:", "ceo ", "@ceo ", "@ceo:",
            "writer:", "writer ", "@writer ", "@writer:",
            "라이터:", "라이터 ", "@라이터 ", "@라이터:",
            "tutti:", "tutti ", "@tutti ", "@tutti:",
            "뚜띠:", "뚜띠 ", "@뚜띠 ", "@뚜띠:",
        )
        return content.startswith(explicit_prefixes) or any(p.strip() in content for p in explicit_prefixes if p.startswith("@"))

    def _detect_agent(
        self,
        content: str,
        thread: discord.Thread | None = None,
        context: str | None = None,
    ) -> str:
        lower = content.lower()
        for keyword, agent_id in ROLE_KEYWORDS.items():
            if keyword in lower:
                return agent_id
        if thread is not None:
            history = context if context is not None else self.thread_context_cache.get(self._thread_cache_key(thread), "")
            return self._fallback_agent_for_thread_context(history)
        return "creative_designer"

    def _thread_cache_key(self, thread: discord.Thread) -> str:
        thread_id = getattr(thread, "id", None)
        if thread_id is not None:
            return str(thread_id)
        return getattr(thread, "name", "unknown-thread")

    def _fallback_agent_for_thread_context(self, context: str) -> str:
        role_map = {
            "Designer": "creative_designer",
            "Reviewer": "technical_reviewer",
            "CEO": "product_ceo",
            "Writer": "spec_writer",
        }
        for line in reversed(context.splitlines()):
            if not line.startswith("[Agent: "):
                continue
            closing = line.find("]")
            if closing == -1:
                continue
            label = line[len("[Agent: ") : closing]
            agent_id = role_map.get(label)
            if agent_id:
                return agent_id
        return "creative_designer"

    async def _build_thread_context(self, thread: discord.Thread, limit: int = 10) -> str:
        msgs = []
        async for msg in thread.history(limit=limit, oldest_first=False):
            if msg.author == self.user:
                role = self._agent_label_from_bot_message(msg.content)
                if role:
                    msgs.append(f"[Agent: {role}]: {msg.content[:500]}")
                else:
                    msgs.append(f"[Agent]: {msg.content[:500]}")
            else:
                msgs.append(f"[User]: {msg.content[:500]}")
        msgs.reverse()
        context = "\n\n".join(msgs)
        self.thread_context_cache[self._thread_cache_key(thread)] = context
        return context

    def _agent_label_from_bot_message(self, content: str) -> str | None:
        for label in ROLE_LABELS.values():
            prefix = f"**{label}**"
            if content.startswith(prefix):
                return label
        return None

    async def _run_start(self, interaction: discord.Interaction, idea: str, run_name: str | None = None) -> None:
        await interaction.response.defer(thinking=True)
        try:
            guild_id = interaction.guild.id
            env = self.get_effective_env(guild_id)
            env["DISCORD_PROJECT"] = env.get("DISCORD_PROJECT", "orchestra-demo")
            env["DISCORD_RUN"] = _slugify(run_name) if run_name else (_slugify(idea) or "latest")
            workspace = build_workspace_from_env(env)
            
            # Phase 1: Design Review
            stage = await asyncio.to_thread(
                run_design_review, idea, env=env, artifact_dir=self.artifact_root
            )
            
            # Publish Phase 1 locally
            publisher = LiveDiscordPublisher(interaction.guild, workspace.category_name)
            await publisher.send_message(
                channel_name=workspace.runs_channel_name,
                thread_name=workspace.run_thread_name,
                content=f"# Orchestra Run Opened\n\n- Project: `{workspace.project_name}`\n- Idea: {idea}"
            )
            
            for message in stage.messages:
                if message.sender == "human_operator":
                    continue
                await publisher.send_message(
                    channel_name=workspace.runs_channel_name,
                    thread_name=workspace.run_thread_name,
                    content=format_agent_timeline_message(message),
                )
            self.pending_stages[workspace.run_thread_name] = (stage, workspace, env)
            
        except Exception as exc:
            await interaction.followup.send(f"Run failed: {exc}")
            return

        risk = stage.risk_level
        LOGGER.info("CEO risk assessment: %s for run %s", risk, workspace.run_thread_name)

        if risk == "LOW":
            # 자동 승인 — HITL 없이 바로 finalize
            await publisher.send_message(
                channel_name=workspace.runs_channel_name,
                thread_name=workspace.run_thread_name,
                content=(
                    "## ⚡ 자동 승인 (Risk: LOW)\n\n"
                    "CEO가 위험도를 **LOW**로 평가했습니다. 자동으로 최종 명세 및 프로토타입 생성을 진행합니다."
                ),
            )
            await interaction.followup.send(
                f"Run created: `{workspace.run_thread_name}` (Risk: LOW, 자동 승인)",
                ephemeral=True,
            )
            await self._run_finalize(interaction, workspace.run_thread_name, "")

        elif risk == "MEDIUM":
            # 15초 대기 후 자동 진행 (사용자가 그 사이 Revise 버튼을 누르면 중단)
            view = InterventionView(self, workspace.run_thread_name)
            await publisher.send_message(
                channel_name=workspace.runs_channel_name,
                thread_name=workspace.run_thread_name,
                content=(
                    "## ⚠️ 주의 필요 (Risk: MEDIUM)\n\n"
                    "CEO가 위험도를 **MEDIUM**으로 평가했습니다.\n"
                    "**15초 후 자동으로 진행**됩니다. 수정이 필요하면 아래 버튼을 눌러주세요."
                ),
                view=view,
            )
            await interaction.followup.send(
                f"Run created: `{workspace.run_thread_name}` (Risk: MEDIUM, 15초 후 자동 진행)",
                ephemeral=True,
            )
            # 15초 대기 후 pending_stages에 아직 남아있으면 (사용자가 버튼을 안 눌렀으면) 자동 승인
            await asyncio.sleep(15)
            if workspace.run_thread_name in self.pending_stages:
                await self._run_finalize(interaction, workspace.run_thread_name, "")

        else:
            # HIGH — 기존과 동일한 HITL 버튼 표시
            view = InterventionView(self, workspace.run_thread_name)
            await publisher.send_message(
                channel_name=workspace.runs_channel_name,
                thread_name=workspace.run_thread_name,
                content=(
                    "## 🛑 승인 필요 (Risk: HIGH)\n\n"
                    + format_approval_needed_message(stage)
                ),
                view=view,
            )
            await interaction.followup.send(
                f"Run created: `{workspace.run_thread_name}` (Risk: HIGH, 승인 대기 중)",
                ephemeral=True,
            )

    async def _run_finalize(self, interaction: discord.Interaction, run_key: str, intervention: str) -> None:
        if run_key not in self.pending_stages:
            try:
                await interaction.followup.send("진행 중인 기획이 없습니다. /tutti start 로 새로 시작하세요.", ephemeral=True)
            except discord.errors.InteractionResponded:
                pass
            return
            
        stage, workspace, env = self.pending_stages.pop(run_key)
        # revise에서 저장한 기존 instruction이 있으면 intervention에 합침
        saved_instruction = self.pending_stages.pop(f"{run_key}:instruction", "")
        if saved_instruction and intervention:
            intervention = f"{saved_instruction}\n\n추가 피드백: {intervention}"
        elif saved_instruction:
            intervention = saved_instruction
        publisher = LiveDiscordPublisher(interaction.guild, workspace.category_name)
        
        try:
            # Phase 2: Finalize
            result = await asyncio.to_thread(
                finalize_collaboration, stage, intervention=intervention
            )
            
            # Phase 3: Prototype Generator
            idea = stage.idea
            playable_dir = await asyncio.to_thread(
                generate_playable_prototype,
                idea=idea,
                final_spec=result.final_spec_path.read_text(encoding="utf-8"),
                artifact_dir=result.final_spec_path.parent,
                run_name=workspace.run_thread_name.replace("run-", ""),
                env=env,
            )
            result.playable_dir = playable_dir
            
            # Publish Phase 2/3 locally
            # Send the new messages (Intervention, Designer Revision, Spec Writer)
            for message in result.messages:
                if message.round > 1:
                    await publisher.send_message(
                        channel_name=workspace.runs_channel_name,
                        thread_name=workspace.run_thread_name,
                        content=format_agent_timeline_message(message),
                    )
            
            # Final Run Complete Message
            await publisher.send_message(
                channel_name=workspace.runs_channel_name,
                thread_name=workspace.run_thread_name,
                content=format_run_complete_message(
                    result.final_spec_path,
                    playable_dir / "index.html",
                ),
            )

            # Handoff Message (개발팀 전달용 - #proj-handoffs)
            await publisher.send_message(
                channel_name=workspace.handoff_channel_name,
                thread_name=workspace.run_thread_name,
                content=format_handoff_message(result),
            )

            # GitHub PR 자동 생성 (토큰이 있을 때만)
            state = self.state_for(interaction.guild.id)
            github_token = state.api_keys.get("GITHUB_TOKEN")
            github_repo = env.get("GITHUB_GAME_REPO", state.server_config.get("GITHUB_GAME_REPO", ""))
            run_label = workspace.run_thread_name.replace("run-", "")

            if github_token and github_repo:
                try:
                    risk = getattr(stage, "risk_level", "MEDIUM")
                    pr_result = await asyncio.to_thread(
                        create_game_pr,
                        token=github_token,
                        repo=github_repo,
                        run_name=run_label,
                        spec_path=result.final_spec_path,
                        schema_path=result.schema_path,
                        prototype_dir=playable_dir,
                        idea=idea,
                        risk_level=risk,
                    )
                    await publisher.send_message(
                        channel_name=workspace.handoff_channel_name,
                        thread_name=workspace.run_thread_name,
                        content=(
                            f"## 🔗 GitHub PR 생성 완료\n\n"
                            f"- **PR:** {pr_result.pr_url}\n"
                            f"- **Branch:** `{pr_result.branch_name}`\n"
                            f"- **Files:** {len(pr_result.files_pushed)}개 파일 푸시됨\n\n"
                            f"개발팀은 위 PR을 리뷰하고 프로덕션 코드를 작성하세요."
                        ),
                    )
                    LOGGER.info("GitHub PR created: %s", pr_result.pr_url)
                except Exception as pr_exc:
                    LOGGER.error("GitHub PR creation failed: %s", pr_exc)
                    await publisher.send_message(
                        channel_name=workspace.handoff_channel_name,
                        thread_name=workspace.run_thread_name,
                        content=f"⚠️ GitHub PR 생성 실패: {pr_exc}\n\n산출물은 로컬에 정상 저장되었습니다.",
                    )
            else:
                LOGGER.info("GitHub PR skipped: token=%s, repo=%s", bool(github_token), github_repo)

            # Update state for revise
            state.last_run = {
                "idea": idea,
                "run_thread": workspace.run_thread_name,
                "final_spec_path": str(result.final_spec_path),
                "playable_dir": str(playable_dir),
                "intervention": intervention,
            }
            
        except Exception as exc:
            await publisher.send_message(
                channel_name=workspace.runs_channel_name,
                thread_name=workspace.run_thread_name,
                content=f"❌ 파이프라인 후반부 실행 실패: {exc}"
            )

    async def _run_revise(self, interaction: discord.Interaction, instruction: str) -> None:
        await interaction.response.defer(thinking=True)
        try:
            guild_id = interaction.guild.id
            state = self.state_for(guild_id)
            if not state.last_run:
                await interaction.followup.send("진행 중인 기획이 없습니다. `/tutti start`로 새로 시작하세요.", ephemeral=True)
                return

            env = self.get_effective_env(guild_id)
            idea = state.last_run["idea"]
            env["DISCORD_PROJECT"] = state.last_run.get("project", env.get("DISCORD_PROJECT", "orchestra-demo"))
            
            run_thread = state.last_run.get("run_thread", "")
            if run_thread.startswith("run-"):
                env["DISCORD_RUN"] = run_thread[4:]
            else:
                env["DISCORD_RUN"] = _slugify(idea) or "latest"
            workspace = build_workspace_from_env(env)
            publisher = LiveDiscordPublisher(interaction.guild, workspace.category_name)

            # Phase 1: Design Review (실시간 메시지 표시)
            stage = await asyncio.to_thread(
                run_design_review, idea, env=env, artifact_dir=self.artifact_root
            )

            await publisher.send_message(
                channel_name=workspace.runs_channel_name,
                thread_name=workspace.run_thread_name,
                content=f"# Revise Run\n\n- Idea: {idea}\n- Instruction: {instruction}",
            )

            for message in stage.messages:
                if message.sender == "human_operator":
                    continue
                await publisher.send_message(
                    channel_name=workspace.runs_channel_name,
                    thread_name=workspace.run_thread_name,
                    content=format_agent_timeline_message(message),
                )

            # HITL: risk-based 자동 승인 (instruction을 기본 intervention으로 저장)
            self.pending_stages[workspace.run_thread_name] = (stage, workspace, env)
            self.pending_stages[f"{workspace.run_thread_name}:instruction"] = instruction

        except Exception as exc:
            await interaction.followup.send(f"Revise failed: {exc}")
            return

        risk = stage.risk_level
        LOGGER.info("Revise CEO risk assessment: %s for run %s", risk, workspace.run_thread_name)

        if risk == "LOW":
            await publisher.send_message(
                channel_name=workspace.runs_channel_name,
                thread_name=workspace.run_thread_name,
                content=(
                    "## ⚡ 자동 승인 (Risk: LOW)\n\n"
                    "CEO가 위험도를 **LOW**로 평가했습니다. 자동으로 수정 명세 및 프로토타입 생성을 진행합니다."
                ),
            )
            await interaction.followup.send(
                f"Revise 자동 승인: `{workspace.run_thread_name}` (Risk: LOW)",
                ephemeral=True,
            )
            await self._run_finalize(interaction, workspace.run_thread_name, "")

        elif risk == "MEDIUM":
            view = InterventionView(self, workspace.run_thread_name)
            await publisher.send_message(
                channel_name=workspace.runs_channel_name,
                thread_name=workspace.run_thread_name,
                content=(
                    "## ⚠️ 주의 필요 (Risk: MEDIUM)\n\n"
                    "CEO가 위험도를 **MEDIUM**으로 평가했습니다.\n"
                    "**15초 후 자동으로 진행**됩니다. 수정이 필요하면 아래 버튼을 눌러주세요."
                ),
                view=view,
            )
            await interaction.followup.send(
                f"Revise 기획 완료: `{workspace.run_thread_name}` (Risk: MEDIUM, 15초 후 자동 진행)",
                ephemeral=True,
            )
            await asyncio.sleep(15)
            if workspace.run_thread_name in self.pending_stages:
                await self._run_finalize(interaction, workspace.run_thread_name, "")

        else:
            # HIGH — 기존과 동일한 HITL 버튼 표시
            view = InterventionView(self, workspace.run_thread_name)
            await publisher.send_message(
                channel_name=workspace.runs_channel_name,
                thread_name=workspace.run_thread_name,
                content=(
                    "## 🛑 승인 필요 (Risk: HIGH)\n\n"
                    + format_approval_needed_message(stage)
                ),
                view=view,
            )
            await interaction.followup.send(
                f"Revise 기획 완료: `{workspace.run_thread_name}` (Risk: HIGH, 승인 대기 중)\n"
                f"Instruction: {instruction}\n"
                f"승인과 추가 수정은 해당 run thread 안에서 진행하세요.",
                ephemeral=True,
            )

    def _register_slash_commands(self) -> None:
        tutti = app_commands.Group(name="tutti", description="Orchestra 게임 디자인 봇")
        bot = self

        @tutti.command(name="start", description="게임 기획 run 시작")
        @app_commands.describe(
            name="프로젝트/쓰레드명 (영문/숫자 권장, 예: dino-run)",
            idea="구체적인 게임 아이디어를 길게 입력하세요"
        )
        async def slash_start(interaction: discord.Interaction, name: str, idea: str) -> None:
            if not interaction.guild:
                await interaction.response.send_message("서버에서만 사용 가능합니다.", ephemeral=True)
                return
            await bot._run_start(interaction, idea, run_name=name)

        @tutti.command(name="revise", description="마지막 run 수정")
        @app_commands.describe(instruction="수정 지시를 입력하세요")
        async def slash_revise(interaction: discord.Interaction, instruction: str) -> None:
            if not interaction.guild:
                await interaction.response.send_message("서버에서만 사용 가능합니다.", ephemeral=True)
                return
            await bot._run_revise(interaction, instruction)

        @tutti.command(name="status", description="현재 상태 확인")
        async def slash_status(interaction: discord.Interaction) -> None:
            if not interaction.guild:
                await interaction.response.send_message("서버에서만 사용 가능합니다.", ephemeral=True)
                return
            state = bot.state_for(interaction.guild.id)
            await interaction.response.send_message(
                build_status_message(state, bot.get_effective_env(interaction.guild.id)), ephemeral=True,
            )

        @tutti.command(name="help", description="도움말")
        async def slash_help(interaction: discord.Interaction) -> None:
            if not interaction.guild:
                await interaction.response.send_message("서버에서만 사용 가능합니다.", ephemeral=True)
                return
            state = bot.state_for(interaction.guild.id)
            await interaction.response.send_message(
                build_help_message(bot.get_effective_env(interaction.guild.id), state), ephemeral=True,
            )

        @tutti.command(name="menu", description="메인 메뉴 버튼 패널")
        async def slash_menu(interaction: discord.Interaction) -> None:
            if not interaction.guild:
                await interaction.response.send_message("서버에서만 사용 가능합니다.", ephemeral=True)
                return
            await interaction.response.send_message(
                build_onboarding_message(
                    mode=os.environ.get("AGENT_MODE", "mock"),
                    model=os.environ.get("DESIGNER_MODEL", "mock"),
                ),
                view=OnboardingView(bot),
            )

        @tutti.command(name="settings", description="에이전트 및 서버 설정")
        async def slash_settings(interaction: discord.Interaction) -> None:
            if not interaction.guild:
                await interaction.response.send_message("서버에서만 사용 가능합니다.", ephemeral=True)
                return
            state = bot.state_for(interaction.guild.id)
            env = bot.get_effective_env(interaction.guild.id)
            server_info = _format_server_config(state)
            await interaction.response.send_message(
                f"{build_agent_settings_message(state, env)}\n\n{server_info}",
                view=SettingsView(bot), ephemeral=True,
            )

        @tutti.command(name="apikey", description="API 키 설정 (DM으로 전송)")
        async def slash_apikey(interaction: discord.Interaction) -> None:
            if not interaction.guild:
                await interaction.response.send_message("서버에서만 사용 가능합니다.", ephemeral=True)
                return
            await interaction.response.defer(ephemeral=True)
            try:
                await interaction.user.send(
                    "API 키를 설정합니다. 아래 버튼을 눌러주세요.",
                    view=ApiKeyView(bot, interaction.guild.id),
                )
                await interaction.followup.send("DM으로 API 키 설정 메시지를 보냈습니다.", ephemeral=True)
            except discord.Forbidden:
                await interaction.followup.send("DM을 보낼 수 없습니다. DM 수신을 허용해주세요.", ephemeral=True)

        @tutti.command(name="github", description="GitHub PR 연동 설정 가이드")
        async def slash_github(interaction: discord.Interaction) -> None:
            if not interaction.guild:
                await interaction.response.send_message("서버에서만 사용 가능합니다.", ephemeral=True)
                return
            state = bot.state_for(interaction.guild.id)
            has_token = "GITHUB_TOKEN" in state.api_keys
            has_repo = bool(state.server_config.get("GITHUB_GAME_REPO"))

            status_token = "✅ 등록됨" if has_token else "❌ 미등록"
            status_repo = f"✅ `{state.server_config['GITHUB_GAME_REPO']}`" if has_repo else "❌ 미설정"

            await interaction.response.send_message(
                "## 🔗 GitHub PR 연동 설정 가이드\n\n"
                "기획이 완료되면 자동으로 GitHub PR을 생성합니다.\n\n"
                "### 현재 상태\n"
                f"- **GitHub Token:** {status_token}\n"
                f"- **Game Repo:** {status_repo}\n\n"
                "### 설정 방법 (3단계)\n\n"
                "**Step 1.** GitHub에서 산출물 전용 레포를 만드세요\n"
                "- [📦 새 레포 만들기](https://github.com/new)\n"
                "- 이름 추천: `tutti-game-artifacts`\n\n"
                "**Step 2.** GitHub PAT(Personal Access Token)를 발급하세요\n"
                "- [🔑 PAT 발급 페이지](https://github.com/settings/tokens/new)\n"
                "- **필수 권한(Scope):** `repo` (전체 레포 접근 권한) 체크\n"
                "- 생성된 토큰(`ghp_xxx...`)을 복사하세요\n\n"
                "**Step 3.** 디스코드에서 등록하세요\n"
                "```\n"
                "/tutti apikey → Key Name: GITHUB_TOKEN, Key: ghp_xxx...\n"
                "/tutti settings → GitHub Game Repo: 본인아이디/tutti-game-artifacts\n"
                "```\n\n"
                "설정 완료 후 `/tutti start`를 실행하면, 파이프라인 마지막에 **자동으로 PR이 생성**됩니다! 🚀",
                ephemeral=True,
            )

        @tutti.command(name="learn", description="에이전트에게 규칙을 학습시킵니다")
        @app_commands.describe(
            rule="학습시킬 규칙 (예: '모든 버튼에 hover 효과를 넣어')",
            scope="적용 범위: global(모든 프로젝트) 또는 project(현재 프로젝트만)",
        )
        @app_commands.choices(scope=[
            app_commands.Choice(name="🌐 Global (모든 프로젝트)", value="global"),
            app_commands.Choice(name="📁 Project (현재 프로젝트만)", value="project"),
        ])
        async def slash_learn(
            interaction: discord.Interaction, rule: str,
            scope: app_commands.Choice[str] | None = None,
        ) -> None:
            if not interaction.guild:
                await interaction.response.send_message("서버에서만 사용 가능합니다.", ephemeral=True)
                return
            from .knowledge import save_rule
            scope_value = scope.value if scope else "global"
            state = bot.state_for(interaction.guild.id)
            project_name = ""
            if scope_value == "project" and state.last_run:
                project_name = state.last_run.get("idea", "default")
            created = save_rule(
                root=bot.artifact_root,
                content=rule,
                scope=scope_value,
                project_name=project_name,
                created_by=str(interaction.user),
            )
            scope_label = "🌐 Global" if scope_value == "global" else f"📁 Project: {project_name}"
            await interaction.response.send_message(
                f"✅ 규칙 학습 완료!\n"
                f"- ID: `{created.id}`\n"
                f"- Scope: {scope_label}\n"
                f"- Rule: {rule}\n\n"
                f"이후 모든 에이전트가 이 규칙을 따릅니다.",
                ephemeral=True,
            )

        @tutti.command(name="rules", description="현재 적용 중인 학습 규칙 목록")
        async def slash_rules(interaction: discord.Interaction) -> None:
            if not interaction.guild:
                await interaction.response.send_message("서버에서만 사용 가능합니다.", ephemeral=True)
                return
            from .knowledge import load_all_rules
            state = bot.state_for(interaction.guild.id)
            project_name = ""
            if state.last_run:
                project_name = state.last_run.get("idea", "")
            store = load_all_rules(bot.artifact_root, project_name)
            await interaction.response.send_message(store.list_rules(), ephemeral=True)

        @tutti.command(name="forget", description="학습된 규칙을 삭제합니다")
        @app_commands.describe(rule_id="삭제할 규칙 ID (예: rule_123456)")
        async def slash_forget(interaction: discord.Interaction, rule_id: str) -> None:
            if not interaction.guild:
                await interaction.response.send_message("서버에서만 사용 가능합니다.", ephemeral=True)
                return
            from .knowledge import delete_rule
            state = bot.state_for(interaction.guild.id)
            project_name = ""
            if state.last_run:
                project_name = state.last_run.get("idea", "")
            removed = delete_rule(bot.artifact_root, rule_id, project_name)
            if removed:
                await interaction.response.send_message(f"✅ 규칙 `{rule_id}` 삭제 완료.", ephemeral=True)
            else:
                await interaction.response.send_message(f"❌ 규칙 `{rule_id}`을(를) 찾을 수 없습니다.", ephemeral=True)

        self.tree.add_command(tutti)


# --- Modals ---

class StartRunModal(discord.ui.Modal, title="Start Orchestra Run"):
    idea = discord.ui.TextInput(
        label="Game idea", placeholder="한 손으로 플레이하는 1분 리듬 탭 게임",
        style=discord.TextStyle.paragraph, required=True, max_length=300,
    )

    def __init__(self, bot: OrchestraDiscordBot) -> None:
        super().__init__()
        self.bot = bot

    async def on_submit(self, interaction: discord.Interaction) -> None:
        if not interaction.guild:
            await interaction.response.send_message("Guild context is required.", ephemeral=True)
            return
        await self.bot._run_start(interaction, self.idea.value)


class ReviseRunModal(discord.ui.Modal, title="Revise Last Run"):
    instruction = discord.ui.TextInput(
        label="Revision instruction", placeholder="속도를 낮추고 튜토리얼을 추가해",
        style=discord.TextStyle.paragraph, required=True, max_length=300,
    )

    def __init__(self, bot: OrchestraDiscordBot) -> None:
        super().__init__()
        self.bot = bot

    async def on_submit(self, interaction: discord.Interaction) -> None:
        if not interaction.guild:
            await interaction.response.send_message("Guild context is required.", ephemeral=True)
            return
        await self.bot._run_revise(interaction, self.instruction.value)


class AgentConfigModal(discord.ui.Modal):
    provider = discord.ui.TextInput(
        label="Provider", placeholder="mock | ollama | openai | google",
        required=True, max_length=40,
    )
    model = discord.ui.TextInput(
        label="Model", placeholder="qwen2.5-coder:7b-instruct",
        required=True, max_length=100,
    )

    def __init__(self, bot: OrchestraDiscordBot, role: str, guild_id: int) -> None:
        super().__init__(title=f"Configure {ROLE_LABELS.get(role, role)}")
        self.bot = bot
        self.role = role
        self.guild_id = guild_id
        current = bot.state_for(guild_id).agent_overrides.get(role, {})
        if current.get("provider"):
            self.provider.default = current["provider"]
        if current.get("model"):
            self.model.default = current["model"]

    async def on_submit(self, interaction: discord.Interaction) -> None:
        if not interaction.guild:
            await interaction.response.send_message("Guild context is required.", ephemeral=True)
            return
        state = self.bot.state_for(self.guild_id)
        state.agent_overrides[self.role] = {"provider": self.provider.value, "model": self.model.value}
        await interaction.response.send_message(
            f"Agent config updated: `{self.role}` → `{self.provider.value}/{self.model.value}`", ephemeral=True,
        )


class ServerConfigModal(discord.ui.Modal, title="Server Settings"):
    ollama_url = discord.ui.TextInput(
        label="Ollama URL", placeholder="http://172.20.128.222:11434",
        required=False, max_length=200,
    )
    preset = discord.ui.TextInput(
        label="Default Preset", placeholder="balanced | fast_draft | deep_review",
        required=False, max_length=20,
    )
    github_repo = discord.ui.TextInput(
        label="GitHub Game Repo", placeholder="owner/repo-name (PR 산출물 전용 레포)",
        required=False, max_length=100,
    )

    def __init__(self, bot: OrchestraDiscordBot, guild_id: int) -> None:
        super().__init__()
        self.bot = bot
        self.guild_id = guild_id
        state = bot.state_for(guild_id)
        if state.server_config.get("ollama_base_url"):
            self.ollama_url.default = state.server_config["ollama_base_url"]
        if state.server_config.get("preset"):
            self.preset.default = state.server_config["preset"]
        if state.server_config.get("GITHUB_GAME_REPO"):
            self.github_repo.default = state.server_config["GITHUB_GAME_REPO"]

    async def on_submit(self, interaction: discord.Interaction) -> None:
        state = self.bot.state_for(self.guild_id)
        if self.ollama_url.value.strip():
            state.server_config["ollama_base_url"] = self.ollama_url.value.strip()
        if self.preset.value.strip():
            state.server_config["preset"] = self.preset.value.strip().lower()
        if self.github_repo.value.strip():
            repo_val = self.github_repo.value.strip()
            # 전체 URL을 입력했을 경우 owner/repo만 추출
            if "github.com/" in repo_val:
                repo_val = repo_val.split("github.com/")[-1]
            if repo_val.endswith(".git"):
                repo_val = repo_val[:-4]
            repo_val = repo_val.strip("/")
            state.server_config["GITHUB_GAME_REPO"] = repo_val
        await interaction.response.send_message(
            f"Server config updated.\n{_format_server_config(state)}", ephemeral=True,
        )


class ApiKeyModal(discord.ui.Modal, title="Set API Key"):
    key_name = discord.ui.TextInput(
        label="Key Name", placeholder="OPENAI_API_KEY / GOOGLE_API_KEY / GITHUB_TOKEN",
        required=True, max_length=30,
    )
    key_value = discord.ui.TextInput(
        label="API Key", placeholder="sk-... / ghp_... / AIza...",
        required=True, max_length=200,
    )

    def __init__(self, bot: OrchestraDiscordBot, guild_id: int) -> None:
        super().__init__()
        self.bot = bot
        self.guild_id = guild_id

    async def on_submit(self, interaction: discord.Interaction) -> None:
        name = self.key_name.value.strip().upper()
        if name not in {"OPENAI_API_KEY", "GOOGLE_API_KEY", "GITHUB_TOKEN"}:
            await interaction.response.send_message(
                "지원하는 키: `OPENAI_API_KEY`, `GOOGLE_API_KEY`, `GITHUB_TOKEN`", ephemeral=True,
            )
            return
        state = self.bot.state_for(self.guild_id)
        state.api_keys[name] = self.key_value.value.strip()
        await interaction.response.send_message(f"`{name}` 설정 완료.", ephemeral=True)


# --- Views ---

class SettingsView(discord.ui.View):
    def __init__(self, bot: OrchestraDiscordBot) -> None:
        super().__init__(timeout=900)
        self.bot = bot

    @discord.ui.button(label="Designer", style=discord.ButtonStyle.secondary)
    async def cfg_designer(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        await interaction.response.send_modal(AgentConfigModal(self.bot, "creative_designer", interaction.guild.id))

    @discord.ui.button(label="Reviewer", style=discord.ButtonStyle.secondary)
    async def cfg_reviewer(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        await interaction.response.send_modal(AgentConfigModal(self.bot, "technical_reviewer", interaction.guild.id))

    @discord.ui.button(label="CEO", style=discord.ButtonStyle.secondary)
    async def cfg_ceo(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        await interaction.response.send_modal(AgentConfigModal(self.bot, "product_ceo", interaction.guild.id))

    @discord.ui.button(label="Writer", style=discord.ButtonStyle.secondary)
    async def cfg_writer(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        await interaction.response.send_modal(AgentConfigModal(self.bot, "spec_writer", interaction.guild.id))

    @discord.ui.button(label="🔧 Server", style=discord.ButtonStyle.primary)
    async def cfg_server(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        await interaction.response.send_modal(ServerConfigModal(self.bot, interaction.guild.id))


class OnboardingView(discord.ui.View):
    def __init__(self, bot: OrchestraDiscordBot) -> None:
        super().__init__(timeout=1800)
        self.bot = bot

    @discord.ui.button(label="📊 Status", style=discord.ButtonStyle.secondary)
    async def show_status(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        if not interaction.guild:
            await interaction.response.send_message("Guild context is required.", ephemeral=True)
            return
        await interaction.response.send_message(
            build_status_message(self.bot.state_for(interaction.guild.id), self.bot.get_effective_env(interaction.guild.id)),
            ephemeral=True,
        )

    @discord.ui.button(label="❓ Help", style=discord.ButtonStyle.secondary)
    async def show_help(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        if not interaction.guild:
            await interaction.response.send_message("Guild context is required.", ephemeral=True)
            return
        await interaction.response.send_message(
            build_help_message(self.bot.get_effective_env(interaction.guild.id), self.bot.state_for(interaction.guild.id)),
            ephemeral=True,
        )

    @discord.ui.button(label="⚙️ Settings", style=discord.ButtonStyle.success)
    async def show_settings(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        if not interaction.guild:
            await interaction.response.send_message("Guild context is required.", ephemeral=True)
            return
        state = self.bot.state_for(interaction.guild.id)
        env = self.bot.get_effective_env(interaction.guild.id)
        await interaction.response.send_message(
            f"{build_agent_settings_message(state, env)}\n\n{_format_server_config(state)}",
            ephemeral=True, view=SettingsView(self.bot),
        )


class ApiKeyView(discord.ui.View):
    def __init__(self, bot: OrchestraDiscordBot, guild_id: int) -> None:
        super().__init__(timeout=300)
        self.bot = bot
        self.guild_id = guild_id

    @discord.ui.button(label="OpenAI Key", style=discord.ButtonStyle.primary)
    async def set_openai(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        await interaction.response.send_modal(ApiKeyModal(self.bot, self.guild_id))

    @discord.ui.button(label="Google Key", style=discord.ButtonStyle.primary)
    async def set_google(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        await interaction.response.send_modal(ApiKeyModal(self.bot, self.guild_id))

    @discord.ui.button(label="GitHub Token", style=discord.ButtonStyle.success)
    async def set_github(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        await interaction.response.send_modal(ApiKeyModal(self.bot, self.guild_id))


# --- Helpers ---

def _format_server_config(state: DiscordBotState) -> str:
    cfg = state.server_config
    lines = ["# Server Config"]
    lines.append(f"- Ollama URL: `{cfg.get('ollama_base_url', 'env default')}`")
    lines.append(f"- Preset: `{cfg.get('preset', 'env default')}`")
    lines.append(f"- GitHub Repo: `{cfg.get('GITHUB_GAME_REPO', 'not set')}`")
    keys = list(state.api_keys.keys())
    lines.append(f"- API Keys set: `{', '.join(keys) if keys else 'none'}`")
    return "\n".join(lines)


def _chunk_message(content: str, limit: int = 1900) -> list[str]:
    if len(content) <= limit:
        return [content]
    chunks: list[str] = []
    current = ""
    for line in content.splitlines(keepends=True):
        if len(current) + len(line) > limit and current:
            chunks.append(current)
            current = ""
        if len(line) > limit:
            if current:
                chunks.append(current)
                current = ""
            for start in range(0, len(line), limit):
                chunks.append(line[start : start + limit])
            continue
        current += line
    if current:
        chunks.append(current)
    return chunks


def _find_writable_channel(guild: discord.Guild) -> discord.TextChannel | None:
    me = guild.me
    if me is None:
        return None
    for channel in guild.text_channels:
        permissions = channel.permissions_for(me)
        if permissions.view_channel and permissions.send_messages:
            return channel
    return None


def _mentions_user(message: discord.Message, user: discord.ClientUser | None) -> bool:
    if user is None:
        return False
    user_id = getattr(user, "id", None)
    for mentioned in getattr(message, "mentions", []) or []:
        if mentioned == user or getattr(mentioned, "id", None) == user_id:
            return True
    return False


def _load_dotenv(path: Path | None = None) -> None:
    """Load a .env file into os.environ (no third-party dependency)."""
    env_path = path or Path(__file__).resolve().parent.parent / ".env"
    if not env_path.exists():
        return
    with env_path.open(encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, _, value = line.partition("=")
            key = key.strip()
            value = value.strip().strip("'\"")
            if key and key not in os.environ:
                os.environ[key] = value


def run_bot() -> None:
    _load_dotenv()
    token = os.environ.get("DISCORD_BOT_TOKEN", "").strip()
    if not token:
        raise RuntimeError("DISCORD_BOT_TOKEN is required to run the Discord bot.")
    logging.basicConfig(level=logging.INFO)
    bot = OrchestraDiscordBot()
    bot.run(token)


if __name__ == "__main__":
    run_bot()
