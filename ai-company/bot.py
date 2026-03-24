import base64
import datetime
import logging
import os
import posixpath
import re
from typing import Callable, Optional

import aiohttp
import discord
from discord import app_commands
from discord.ext import commands

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)

DISCORD_TOKEN = os.environ.get("DISCORD_TOKEN_COMPANY", "")
POLLINATIONS_TOKEN = os.environ.get("POLLINATIONS_TOKEN", "")

# GitHub integration — needed for /build to commit generated code.
# GITHUB_TOKEN is the automatic Actions token passed by the workflow
# (secrets.GITHUB_TOKEN); GITHUB_REPOSITORY is set automatically by
# GitHub Actions (e.g. "owner/repo").
GITHUB_TOKEN = os.environ.get("GITHUB_TOKEN", "")
GITHUB_REPOSITORY = os.environ.get("GITHUB_REPOSITORY", "")
GITHUB_API_BASE = "https://api.github.com"
# Parent folder in the repository where generated projects are stored.
PROJECT_FOLDER = "project"

AI_API_URL = "https://gen.pollinations.ai/v1/chat/completions"

# Model fallback chain — tried in order; next model used on any error
MODEL_CHAIN = [
    "openai-fast",
    "gemini-search",
    "openai",
    "glm",
    "claude-fast",
    "qwen-character",
    "deepseek",
    "qwen-safety",
]

DISCORD_MAX_LENGTH = 2000

# Default company roles used when none are specified
DEFAULT_ROLES = ["CEO", "CTO", "Product Manager", "Designer", "Engineer", "Marketing Manager"]

# Default developer team roles for the /build command
DEFAULT_BUILD_ROLES = ["CTO", "Backend Developer", "Frontend Developer", "QA Engineer", "DevOps Engineer"]

# System prompts for each recognised role
ROLE_PROMPTS: dict[str, str] = {
    "CEO": (
        "You are the CEO of a technology company. "
        "Focus on business strategy, return on investment, market opportunity, and high-level vision. "
        "Be concise and decisive."
    ),
    "CTO": (
        "You are the CTO of a technology company. "
        "Focus on technical architecture, feasibility, scalability, security, and technology stack choices. "
        "Be precise and practical."
    ),
    "Product Manager": (
        "You are the Product Manager. "
        "Focus on user needs, product requirements, prioritization, success metrics, and the product roadmap. "
        "Be user-centric and data-driven."
    ),
    "Designer": (
        "You are the Lead UX/UI Designer. "
        "Focus on user experience, interface design, accessibility, visual identity, and usability. "
        "Be creative and empathetic."
    ),
    "Engineer": (
        "You are the Lead Software Engineer. "
        "Focus on implementation details, technical challenges, development timelines, testing, and code quality. "
        "Be realistic and thorough."
    ),
    "Marketing Manager": (
        "You are the Marketing Manager. "
        "Focus on target audience, brand positioning, growth strategies, content, and messaging. "
        "Be persuasive and market-aware."
    ),
    "Data Scientist": (
        "You are the Data Scientist. "
        "Focus on data requirements, machine learning models, analytics, insights, and data-driven decisions. "
        "Be analytical and evidence-based."
    ),
    "Legal Counsel": (
        "You are the Legal Counsel. "
        "Focus on legal risks, regulatory compliance, intellectual property, privacy laws, and contracts. "
        "Be cautious and thorough."
    ),
    "Finance Manager": (
        "You are the Finance Manager. "
        "Focus on budget planning, cost estimation, revenue projections, financial risks, and ROI analysis. "
        "Be precise and conservative."
    ),
    "HR Manager": (
        "You are the HR Manager. "
        "Focus on team structure, talent requirements, company culture, onboarding, and people management. "
        "Be people-focused and empathetic."
    ),
    # --- Developer team roles ---
    "Frontend Developer": (
        "You are the Frontend Developer. "
        "Focus on UI implementation with React/Vue/HTML/CSS/JavaScript, component design, "
        "responsiveness, and browser compatibility. "
        "Propose concrete frontend architecture and the key components to build."
    ),
    "Backend Developer": (
        "You are the Backend Developer. "
        "Focus on server-side logic, REST/GraphQL API design, database schemas, authentication, "
        "and backend performance. "
        "Propose concrete API endpoints, data models, and backend architecture."
    ),
    "Full Stack Developer": (
        "You are the Full Stack Developer. "
        "Focus on end-to-end implementation, bridging frontend and backend, data flow, "
        "and integration points. "
        "Provide a holistic view of the implementation."
    ),
    "QA Engineer": (
        "You are the QA Engineer. "
        "Focus on testing strategies, unit tests, integration tests, edge cases, "
        "bug prevention, and quality standards. "
        "Outline the key test scenarios and quality gates for the project."
    ),
    "DevOps Engineer": (
        "You are the DevOps Engineer. "
        "Focus on CI/CD pipelines, Docker/containerization, deployment strategies, "
        "monitoring, and infrastructure as code. "
        "Propose the deployment setup and toolchain."
    ),
}

intents = discord.Intents.default()

bot = commands.Bot(command_prefix=commands.when_mentioned, intents=intents)

# Per-channel storage for the last /build session, enabling /followup.
# Structure: { channel_id: { task, discussion, final_outcome, code_files, project_slug } }
build_sessions: dict[int, dict] = {}


# ---------------------------------------------------------------------------
# Discord UI helpers (interrupt feature)
# ---------------------------------------------------------------------------


class UserInputModal(discord.ui.Modal, title="Add Your Perspective"):
    """Modal that collects a user's point of view to inject into the discussion."""

    perspective = discord.ui.TextInput(
        label="Your input / perspective",
        style=discord.TextStyle.paragraph,
        placeholder="Share your thoughts, redirect the discussion, add constraints…",
        required=True,
        max_length=1000,
    )

    async def on_submit(self, interaction: discord.Interaction) -> None:  # type: ignore[override]
        await interaction.response.defer()


class InterruptView(discord.ui.View):
    """Buttons shown after each role response in interactive mode.

    The user can either let the discussion continue or open a modal to inject
    their own perspective before the next role responds.
    """

    def __init__(self) -> None:
        super().__init__(timeout=90)
        self.action: str = "continue"
        self.user_input: Optional[str] = None

    @discord.ui.button(label="▶ Continue", style=discord.ButtonStyle.green)
    async def continue_btn(
        self, interaction: discord.Interaction, button: discord.ui.Button
    ) -> None:
        self.action = "continue"
        for item in self.children:
            item.disabled = True  # type: ignore[union-attr]
        await interaction.response.edit_message(view=self)
        self.stop()

    @discord.ui.button(label="✏️ Add My Input", style=discord.ButtonStyle.blurple)
    async def input_btn(
        self, interaction: discord.Interaction, button: discord.ui.Button
    ) -> None:
        modal = UserInputModal()
        await interaction.response.send_modal(modal)
        await modal.wait()
        self.user_input = modal.perspective.value
        self.action = "input"
        for item in self.children:
            item.disabled = True  # type: ignore[union-attr]
        self.stop()

    async def on_timeout(self) -> None:
        self.action = "continue"
        self.stop()


class RoleSelectView(discord.ui.View):
    """Pre-build role picker rendered as a Discord multi-select menu.

    The user can choose 1–6 roles from every role defined in ROLE_PROMPTS.
    If the view times out the pre-populated ``selected_roles`` (the defaults
    passed at construction) are used automatically.
    """

    def __init__(self, defaults: list[str]) -> None:
        super().__init__(timeout=120)
        self.selected_roles: list[str] = list(defaults)
        options = [
            discord.SelectOption(
                label=role,
                value=role,
                default=role in defaults,
            )
            for role in ROLE_PROMPTS
        ]
        if len(options) > 25:
            logger.warning(
                "ROLE_PROMPTS has %d roles; only the first 25 can appear in the selector "
                "(Discord's per-menu limit).",
                len(options),
            )
        select = discord.ui.Select(
            placeholder="Choose up to 6 roles for this build…",
            min_values=1,
            max_values=6,
            options=options[:25],  # Discord hard-caps at 25 options per menu
        )
        select.callback = self._on_select  # type: ignore[method-assign]
        self.add_item(select)

    async def _on_select(self, interaction: discord.Interaction) -> None:
        self.selected_roles = interaction.data["values"]  # type: ignore[index]
        await interaction.response.defer()
        self.stop()

    async def on_timeout(self) -> None:
        self.stop()


# ---------------------------------------------------------------------------
# General helpers
# ---------------------------------------------------------------------------


def split_message(text: str, limit: int = DISCORD_MAX_LENGTH) -> list[str]:
    """Split *text* into chunks no larger than *limit* characters.

    Prefers splitting on newlines, then spaces, to avoid cutting words.
    """
    if len(text) <= limit:
        return [text]

    chunks: list[str] = []
    while len(text) > limit:
        split_pos = text.rfind("\n", 0, limit)
        if split_pos == -1:
            split_pos = text.rfind(" ", 0, limit)
        if split_pos == -1:
            split_pos = limit
        chunks.append(text[:split_pos])
        text = text[split_pos:].lstrip("\n")
    if text:
        chunks.append(text)
    return chunks


def slugify(text: str) -> str:
    """Convert *text* to a filesystem/URL-safe slug (max 50 chars)."""
    text = text.lower().strip()
    text = re.sub(r"[^\w\s-]", "", text)
    text = re.sub(r"[\s_]+", "-", text)
    text = text.strip("-")
    return text[:50] or "project"


def parse_code_files(text: str) -> list[tuple[str, str]]:
    """Extract ``(filename, content)`` pairs from AI output.

    The AI is instructed to produce files in this exact format::

        ### File: <filename>
        ```<language>
        <code content>
        ```
    """
    pattern = r"### File:\s*([^\n]+)\n```[^\n]*\n(.*?)```"
    matches = re.findall(pattern, text, re.DOTALL)
    return [(filename.strip(), code.rstrip()) for filename, code in matches]


# ---------------------------------------------------------------------------
# AI helpers
# ---------------------------------------------------------------------------


async def call_ai(
    session: aiohttp.ClientSession,
    messages: list[dict],
) -> str:
    """Call the AI API, trying each model in MODEL_CHAIN until one succeeds."""
    headers = {
        "Authorization": f"Bearer {POLLINATIONS_TOKEN}",
        "Content-Type": "application/json",
    }
    for model in MODEL_CHAIN:
        payload = {"model": model, "messages": messages}
        try:
            async with session.post(
                AI_API_URL,
                json=payload,
                headers=headers,
                timeout=aiohttp.ClientTimeout(total=60),
            ) as resp:
                resp.raise_for_status()
                data = await resp.json()
                logger.info("Got reply from model %s", model)
                return data["choices"][0]["message"]["content"]
        except Exception as exc:
            logger.warning("Model %s failed: %s. Trying next...", model, exc)
    raise RuntimeError("All AI models failed.")


async def generate_project_name(
    session: aiohttp.ClientSession,
    task: str,
) -> str:
    """Ask the AI to invent a short, filesystem-safe project slug for *task*.

    Falls back to ``slugify(task)`` if the AI call fails or returns an unusable slug.
    """
    messages = [
        {
            "role": "system",
            "content": (
                "You generate concise, filesystem-safe project names. "
                "Reply with ONLY the project name: lowercase letters, digits, and hyphens, "
                "2–4 words maximum, no spaces, no punctuation, no extra text. "
                "Example: 'todo-rest-api'."
            ),
        },
        {
            "role": "user",
            "content": f"Generate a project name for: {task}",
        },
    ]
    try:
        raw = await call_ai(session, messages)
        # Take the first whitespace-delimited token and apply slugify for safety
        first_token = raw.strip().split()[0] if raw.strip() else ""
        slug = slugify(first_token)
        if slug and slug != "project":
            return slug
    except Exception as exc:
        logger.warning("Project name generation failed: %s", exc)
    return slugify(task)


# Supported tech stacks for the /autorun command
_AUTO_STACKS: dict[str, str] = {
    "python": "Python (Flask, FastAPI, or a standalone CLI/script)",
    "php": "PHP + HTML (a dynamic web page or small PHP web API)",
    "actions": "GitHub Actions (a YAML workflow for CI/CD or automation)",
}


async def generate_auto_task(
    session: aiohttp.ClientSession,
    stack: str | None = None,
) -> tuple[str, str]:
    """Ask the AI to invent a fresh programming task.

    Returns ``(task_description, stack_key)`` where *stack_key* is one of
    ``"python"``, ``"php"``, or ``"actions"``.
    """
    if stack and stack in _AUTO_STACKS:
        stack_hint = f"The project MUST use this tech stack: {_AUTO_STACKS[stack]}."
    else:
        options = " | ".join(f"{k}: {v}" for k, v in _AUTO_STACKS.items())
        stack_hint = f"Choose ONE of these stacks that suits the project best: {options}."

    messages = [
        {
            "role": "system",
            "content": (
                "You are a creative software architect who invents interesting, "
                "self-contained programming projects that a small team can build in one sprint."
            ),
        },
        {
            "role": "user",
            "content": (
                f"Invent a concrete, buildable programming project. {stack_hint}\n"
                "Reply in EXACTLY this format — no extra text:\n"
                "TASK: <one clear sentence describing what to build>\n"
                "STACK: <python | php | actions>"
            ),
        },
    ]
    try:
        raw = await call_ai(session, messages)
        task_match = re.search(r"TASK:\s*(.+)", raw)
        stack_match = re.search(r"STACK:\s*(\w+)", raw)
        task = task_match.group(1).strip() if task_match else raw.strip()[:200]
        chosen = stack_match.group(1).strip().lower() if stack_match else (stack or "python")
        if chosen not in _AUTO_STACKS:
            chosen = stack or "python"
        return task, chosen
    except Exception as exc:
        logger.warning("Auto-task generation failed: %s", exc)
    fallback_stack = stack if stack in _AUTO_STACKS else "python"
    return "Build a simple Python CLI tool that converts CSV files to JSON", fallback_stack


async def run_company_discussion(
    task: str,
    roles: list[str],
    role_done_cb: Optional[Callable] = None,
) -> tuple[list[tuple[str, str]], str]:
    """Simulate a company discussion.

    Each role is queried in turn, with a summary of prior contributions
    included in its context so the discussion builds naturally.  Any user
    input injected via the *role_done_cb* callback is also included so the
    AI roles can react to stakeholder guidance.

    Parameters
    ----------
    task:
        The topic for the discussion.
    roles:
        Ordered list of role names to include.
    role_done_cb:
        Optional ``async (role, reply) -> str | None`` callback invoked
        *after* each role responds.  If the callback returns a non-empty
        string, it is treated as a stakeholder interjection and included in
        the context given to all subsequent roles.

    Returns
    -------
    ``(role_responses, final_outcome)`` where *role_responses* is a list of
    ``(role_name, reply)`` tuples.
    """
    discussion: list[tuple[str, str]] = []
    # User interjections collected during the discussion
    injected_inputs: list[str] = []

    async with aiohttp.ClientSession() as session:
        # --- Each role contributes in sequence ---
        for role in roles:
            system_prompt = ROLE_PROMPTS.get(
                role,
                f"You are the {role} of a technology company. Share your professional perspective.",
            )

            user_content = f"**Task:** {task}\n"

            # Inject any stakeholder input collected so far
            if injected_inputs:
                user_content += "\n**Stakeholder Input (from the human in the room):**\n"
                for idx, inp in enumerate(injected_inputs, 1):
                    user_content += f"> [{idx}] {inp}\n"

            if discussion:
                user_content += "\n**Discussion so far:**\n"
                for prev_role, prev_reply in discussion:
                    truncated = prev_reply[:500] + "…" if len(prev_reply) > 500 else prev_reply
                    user_content += f"\n**{prev_role}:** {truncated}\n"
                user_content += (
                    f"\nNow, as the **{role}**, respond to this task building on the "
                    "discussion above and any stakeholder input. Acknowledge specific "
                    "points raised by other roles where relevant. Be concise (2–4 sentences)."
                )
            else:
                user_content += (
                    f"\nAs the **{role}**, what is your initial take on this task? "
                    "Be concise (2–4 sentences)."
                )

            messages = [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_content},
            ]

            try:
                reply = await call_ai(session, messages)
                discussion.append((role, reply))
                logger.info("Received contribution from role: %s", role)
            except Exception as exc:
                logger.error("Role %s failed: %s", role, exc)
                reply = "*[No response available]*"
                discussion.append((role, reply))

            # Let the caller react (post to Discord, collect user input, etc.)
            if role_done_cb is not None:
                user_input = await role_done_cb(role, reply)
                if user_input:
                    injected_inputs.append(user_input)
                    logger.info("User interjection added after role %s", role)

        # --- Facilitator synthesises the discussion into a final outcome ---
        synthesis_context = f"**Task:** {task}\n\n**Company Discussion:**\n"
        for role, reply in discussion:
            synthesis_context += f"\n**{role}:** {reply}\n"
        if injected_inputs:
            synthesis_context += "\n**Stakeholder Interjections:**\n"
            for idx, inp in enumerate(injected_inputs, 1):
                synthesis_context += f"> [{idx}] {inp}\n"
        synthesis_context += (
            "\nAs the meeting **Facilitator**, synthesise all perspectives above into a "
            "clear, structured **Final Outcome**. Include:\n"
            "1. Key decisions made\n"
            "2. Recommended next steps (prioritised)\n"
            "3. Important risks or considerations\n"
            "Be actionable and concise."
        )

        facilitator_messages = [
            {
                "role": "system",
                "content": (
                    "You are an expert meeting facilitator who synthesises company discussions "
                    "into clear, actionable outcomes. Provide structured, professional summaries."
                ),
            },
            {"role": "user", "content": synthesis_context},
        ]

        try:
            final_outcome = await call_ai(session, facilitator_messages)
        except Exception as exc:
            logger.error("Final synthesis failed: %s", exc)
            final_outcome = "*Unable to generate the final outcome. Please try again.*"

    return discussion, final_outcome


async def generate_code_files(
    task: str,
    discussion: list[tuple[str, str]],
    final_outcome: str,
) -> tuple[list[tuple[str, str]], str]:
    """Ask the AI to generate complete code files based on the team discussion.

    Returns ``(code_files, raw_output)`` where *code_files* is a list of
    ``(filename, content)`` tuples parsed from the AI response.
    """
    discussion_context = f"**Task:** {task}\n\n**Developer Team Discussion:**\n"
    for role, reply in discussion:
        discussion_context += f"\n**{role}:** {reply}\n"
    discussion_context += f"\n**Final Plan:**\n{final_outcome}"

    code_gen_prompt = (
        f"{discussion_context}\n\n"
        "Based on the plan above, generate a complete, working codebase.\n\n"
        "For EACH file, use EXACTLY this format "
        "(the `### File:` header and triple-backtick fence are required so "
        "files can be parsed and committed to the repository automatically):\n\n"
        "### File: <filename with extension and any sub-path>\n"
        "```<language>\n"
        "<complete file content>\n"
        "```\n\n"
        "Include ALL necessary files: source code, configuration files "
        "(e.g. package.json, requirements.txt, pyproject.toml), a Dockerfile if "
        "appropriate, and a README.md with instructions on how to install and run "
        "the project. Make all code complete and functional — not just placeholders."
    )

    _model_list = "\n".join(f"  {i}. {m}" for i, m in enumerate(MODEL_CHAIN, 1))
    code_gen_messages = [
        {
            "role": "system",
            "content": (
                "You are an expert senior software engineer who writes complete, "
                "production-quality code. Generate every file needed for the project. "
                "Use exactly the `### File:` / ``` format so the output can be parsed "
                "and committed to a repository automatically.\n\n"
                "**AI / LLM integration — IMPORTANT:**\n"
                "If the project involves any AI, chatbot, language model, or text-generation "
                "feature, you MUST use the following Pollinations AI API in the generated code "
                "(do NOT use OpenAI's official SDK or any other provider):\n\n"
                "  Endpoint : POST https://gen.pollinations.ai/v1/chat/completions\n"
                "  Header   : Authorization: Bearer sk_DXo1NL0CHvKB6vGWSdNGYHTqb1u3Y22p\n"
                "  Header   : Content-Type: application/json\n"
                "  Body     : {\"model\": \"<model>\", \"messages\": [{\"role\": \"user\", \"content\": \"...\"}]}\n\n"
                f"Try models in this exact order, switching to the next one if a request fails:\n"
                f"{_model_list}\n\n"
                "Implement the fallback loop in the generated code so it automatically retries "
                "the next model on any HTTP error or exception."
            ),
        },
        {"role": "user", "content": code_gen_prompt},
    ]

    async with aiohttp.ClientSession() as session:
        try:
            raw_output = await call_ai(session, code_gen_messages)
        except Exception as exc:
            logger.error("Code generation failed: %s", exc)
            return [], ""

    code_files = parse_code_files(raw_output)
    logger.info("Generated %d code file(s)", len(code_files))
    return code_files, raw_output


# ---------------------------------------------------------------------------
# GitHub helpers
# ---------------------------------------------------------------------------


async def _get_file_sha(
    session: aiohttp.ClientSession, repo: str, path: str
) -> str | None:
    """Return the current SHA of a repo file, or ``None`` if it does not exist."""
    url = f"{GITHUB_API_BASE}/repos/{repo}/contents/{path}"
    headers = {
        "Authorization": f"token {GITHUB_TOKEN}",
        "Accept": "application/vnd.github+json",
    }
    try:
        async with session.get(url, headers=headers) as resp:
            if resp.status == 200:
                data = await resp.json()
                return data.get("sha")
    except Exception:
        pass
    return None


async def _commit_file(
    session: aiohttp.ClientSession,
    path: str,
    content: str,
    commit_message: str,
) -> str | None:
    """Create or update a single file in GITHUB_REPOSITORY.

    Returns the HTML URL of the file on GitHub, or ``None`` on failure.
    """
    url = f"{GITHUB_API_BASE}/repos/{GITHUB_REPOSITORY}/contents/{path}"
    headers = {
        "Authorization": f"token {GITHUB_TOKEN}",
        "Accept": "application/vnd.github+json",
        "Content-Type": "application/json",
    }
    sha = await _get_file_sha(session, GITHUB_REPOSITORY, path)
    payload: dict = {
        "message": commit_message,
        "content": base64.b64encode(content.encode("utf-8")).decode("ascii"),
    }
    if sha:
        payload["sha"] = sha
    try:
        async with session.put(url, json=payload, headers=headers) as resp:
            resp.raise_for_status()
            data = await resp.json()
            return data["content"]["html_url"]
    except Exception as exc:
        logger.error("GitHub commit failed for %s: %s", path, exc)
        return None


def _safe_project_path(folder: str, filename: str) -> str | None:
    """Return the safe repository path ``folder/filename``.

    Returns ``None`` when *filename* would escape outside *folder* via path
    traversal (e.g. ``../../.github/workflows/evil.yml``).  Both ``..``
    segments and absolute paths are rejected.
    """
    # Normalise OS-specific separators to POSIX-style slashes first.
    normalized = posixpath.normpath(filename.replace("\\", "/"))
    # Reject absolute paths and anything that starts with '..'.
    if posixpath.isabs(normalized) or normalized.startswith(".."):
        logger.warning("Rejecting unsafe filename from AI output: %r", filename)
        return None
    # Defense-in-depth: also reject any individual path component equal to '..'
    # in case normpath behaviour changes or the path is constructed unusually.
    if ".." in normalized.split("/"):
        logger.warning("Rejecting unsafe filename (contains '..'): %r", filename)
        return None
    return f"{folder}/{normalized}"


async def commit_project(
    project_slug: str,
    task: str,
    final_outcome: str,
    code_files: list[tuple[str, str]],
) -> tuple[list[str], str | None]:
    """Commit all project files to ``project/<project_slug>/`` in the repo.

    Returns ``(committed_urls, folder_url)``.
    """
    if not GITHUB_TOKEN or not GITHUB_REPOSITORY:
        logger.warning("GitHub commit skipped: GITHUB_TOKEN or GITHUB_REPOSITORY not set.")
        return [], None

    timestamp = datetime.datetime.utcnow().strftime("%Y-%m-%d %H:%M UTC")
    folder = f"{PROJECT_FOLDER}/{project_slug}"
    commit_msg = f"Add project: {project_slug}"

    # Build a README.md that records the task and final outcome.
    readme_lines = [
        f"# {project_slug}",
        "",
        f"**Task:** {task}",
        "",
        f"*Generated by AI Company Bot on {timestamp}*",
        "",
        "---",
        "",
        "## Final Outcome",
        "",
        final_outcome,
    ]
    if code_files:
        readme_lines += [
            "",
            "---",
            "",
            "## Generated Files",
            "",
        ]
        for filename, _ in code_files:
            readme_lines.append(f"- `{filename}`")
    readme_content = "\n".join(readme_lines) + "\n"

    all_files: list[tuple[str, str]] = [("README.md", readme_content)] + list(code_files)

    committed_urls: list[str] = []
    async with aiohttp.ClientSession() as session:
        for filename, content in all_files:
            path = _safe_project_path(folder, filename)
            if path is None:
                logger.warning("Skipping unsafe filename: %r", filename)
                continue
            file_url = await _commit_file(session, path, content, commit_msg)
            if file_url:
                committed_urls.append(file_url)
                logger.info("Committed: %s", path)
            else:
                logger.warning("Failed to commit: %s", path)

    folder_url = (
        f"https://github.com/{GITHUB_REPOSITORY}/tree/main/{folder}"
        if GITHUB_REPOSITORY
        else None
    )
    return committed_urls, folder_url


# ---------------------------------------------------------------------------
# Thread helpers
# ---------------------------------------------------------------------------


async def _create_task_thread(
    msg: discord.WebhookMessage,
    name: str,
    channel: discord.TextChannel | None = None,
) -> discord.Thread | None:
    """Try to create a public thread from *msg*.

    Returns the thread on success, or ``None`` when threads are not supported
    in this channel (e.g., DMs, thread-in-thread) or the bot lacks the
    ``Create Public Threads`` permission.

    *channel* should be provided when *msg* is a ``WebhookMessage`` (e.g.
    returned by ``interaction.followup.send``), because those objects do not
    carry guild info and therefore cannot call ``create_thread`` directly.
    When *channel* is given the full ``discord.Message`` is re-fetched via
    ``channel.fetch_message`` first.  Any fetch failure (``discord.NotFound``,
    ``discord.Forbidden``, etc.) is caught by the ``discord.HTTPException``
    handler below and causes the function to return ``None`` gracefully.
    """
    try:
        if channel is not None:
            full_msg = await channel.fetch_message(msg.id)
            return await full_msg.create_thread(name=name[:100])
        return await msg.create_thread(name=name[:100])
    except (discord.Forbidden, discord.HTTPException, AttributeError, ValueError) as exc:
        logger.warning("Could not create thread: %s — messages will stay in channel.", exc)
        return None


def _prior_context_note(prior_count: int) -> str:
    """Return a human-readable note about how many prior role responses were read."""
    if prior_count == 0:
        return "*(first to speak)*"
    return f"*(read {prior_count} prior response{'s' if prior_count != 1 else ''})*"


# ---------------------------------------------------------------------------
# Bot events
# ---------------------------------------------------------------------------


@bot.event
async def on_ready():
    await bot.tree.sync()
    logger.info("AI Company Bot logged in as %s (ID: %s)", bot.user, bot.user.id)


# ---------------------------------------------------------------------------
# Slash commands
# ---------------------------------------------------------------------------


@bot.tree.command(
    name="company",
    description="Run an AI company discussion on a task and receive a final outcome",
)
@app_commands.describe(
    task="The task or project for the company to discuss (e.g. 'Build a food delivery app')",
    roles=(
        "Comma-separated roles to include (e.g. 'CEO,CTO,Designer'). "
        "Leave blank to use the default set of roles."
    ),
    interactive=(
        "If True, pause after each role so you can add your own perspective "
        "before the next role responds. Default: False."
    ),
)
async def company_slash(
    interaction: discord.Interaction,
    task: str,
    roles: str | None = None,
    interactive: bool = False,
):
    await interaction.response.defer(thinking=True)

    # Parse and validate roles
    if roles:
        role_list = [r.strip() for r in roles.split(",") if r.strip()]
    else:
        role_list = list(DEFAULT_ROLES)

    # Cap at 6 roles so the session stays manageable and fast
    role_list = role_list[:6]

    logger.info(
        "Company discussion started | task=%r | roles=%s | interactive=%s",
        task,
        role_list,
        interactive,
    )

    roles_display = ", ".join(role_list)
    mode_note = " *(interactive — you can add input between roles)*" if interactive else ""
    header = (
        f"🏢 **AI Company Discussion**{mode_note}\n"
        f"📋 **Task:** {task}\n"
        f"👥 **Participants:** {roles_display}\n"
        f"📡 *Each role reads all prior contributions before responding.*\n\n"
        "*Starting discussion… this may take a moment.*"
    )
    header_msg = await interaction.followup.send(header)

    # Create a dedicated thread so all discussion messages are neatly organised
    thread = await _create_task_thread(header_msg, f"🏢 {task}"[:100], interaction.channel)
    # Route all subsequent messages to the thread when available
    send = thread.send if thread else interaction.followup.send

    # Build the optional callback for interactive mode
    role_done_cb: Optional[Callable] = None
    posts_done_in_cb = False

    if interactive:
        posts_done_in_cb = True

        async def _company_role_cb(role: str, reply: str) -> Optional[str]:
            prior_count = role_list.index(role)  # roles before this one
            context_note = _prior_context_note(prior_count)
            msg = f"👤 **{role}** {context_note}\n{reply}"
            for chunk in split_message(msg):
                await send(chunk)

            # Offer interrupt only if there are more roles to go
            remaining = role_list[role_list.index(role) + 1:]
            if remaining:
                view = InterruptView()
                await send(
                    f"*Next up: **{remaining[0]}**.*  "
                    "Would you like to add your perspective first?",
                    view=view,
                )
                await view.wait()
                if view.action == "input" and view.user_input:
                    preview = (
                        view.user_input[:80] + "…"
                        if len(view.user_input) > 80
                        else view.user_input
                    )
                    await send(f"✅ *Your input noted: \"{preview}\"*")
                    return view.user_input
            return None

        role_done_cb = _company_role_cb

    # Run the multi-role discussion
    discussion, final_outcome = await run_company_discussion(
        task, role_list, role_done_cb=role_done_cb
    )

    # Post each role's contribution (non-interactive path only; interactive
    # mode already posted them inside the callback above)
    if not posts_done_in_cb:
        for idx, (role, reply) in enumerate(discussion):
            context_note = _prior_context_note(idx)
            msg = f"👤 **{role}** {context_note}\n{reply}"
            for chunk in split_message(msg):
                await send(chunk)

    # Post the final synthesised outcome
    final_msg = f"---\n✅ **Final Outcome**\n\n{final_outcome}"
    for chunk in split_message(final_msg):
        await send(chunk)


@bot.tree.command(
    name="build",
    description=(
        "Run a developer team discussion, generate code, and save files to the project/ folder"
    ),
)
@app_commands.describe(
    task="Describe what to build (e.g. 'Create a REST API for a todo app in Python')",
    roles=(
        "Comma-separated developer roles to include. "
        "Leave blank to pick roles from a dropdown menu."
    ),
    interactive=(
        "If True, pause after each role so you can add your own perspective "
        "before the next role responds. Default: False."
    ),
)
async def build_slash(
    interaction: discord.Interaction,
    task: str,
    roles: str | None = None,
    interactive: bool = False,
):
    await interaction.response.defer(thinking=True)

    # Step 0a: resolve roles — text param takes precedence; otherwise show selector UI
    if roles:
        role_list = [r.strip() for r in roles.split(",") if r.strip()]
        role_list = role_list[:6]
    else:
        role_view = RoleSelectView(list(DEFAULT_BUILD_ROLES))
        await interaction.followup.send(
            "👥 **Select team roles** *(choose 1–6, or wait 2 min to use defaults):*",
            view=role_view,
            ephemeral=True,
        )
        await role_view.wait()
        role_list = role_view.selected_roles[:6]

    # Step 0b: generate project name via AI
    async with aiohttp.ClientSession() as _name_session:
        project_slug = await generate_project_name(_name_session, task)
    logger.info(
        "Build session started | task=%r | project=%s | roles=%s | interactive=%s",
        task,
        project_slug,
        role_list,
        interactive,
    )

    roles_display = ", ".join(role_list)
    mode_note = " *(interactive)*" if interactive else ""
    header = (
        f"🛠️ **AI Developer Team — Build Session**{mode_note}\n"
        f"📋 **Task:** {task}\n"
        f"📁 **Project:** `{project_slug}`\n"
        f"👥 **Team:** {roles_display}\n"
        f"📡 *Each team member reads all prior contributions before responding.*\n\n"
        "*Team discussion starting… this may take a moment.*"
    )
    header_msg = await interaction.followup.send(header)

    # Create a dedicated thread so all discussion messages are neatly organised
    thread = await _create_task_thread(header_msg, f"🛠️ {project_slug}"[:100], interaction.channel)
    # Route all subsequent messages to the thread when available
    send = thread.send if thread else interaction.followup.send

    # Build the optional callback for interactive mode
    role_done_cb: Optional[Callable] = None
    posts_done_in_cb = False

    if interactive:
        posts_done_in_cb = True

        async def _build_role_cb(role: str, reply: str) -> Optional[str]:
            prior_count = role_list.index(role)
            context_note = _prior_context_note(prior_count)
            msg = f"👤 **{role}** {context_note}\n{reply}"
            for chunk in split_message(msg):
                await send(chunk)

            remaining = role_list[role_list.index(role) + 1:]
            if remaining:
                view = InterruptView()
                await send(
                    f"*Next up: **{remaining[0]}**.*  "
                    "Would you like to add your perspective first?",
                    view=view,
                )
                await view.wait()
                if view.action == "input" and view.user_input:
                    preview = (
                        view.user_input[:80] + "…"
                        if len(view.user_input) > 80
                        else view.user_input
                    )
                    await send(f"✅ *Your input noted: \"{preview}\"*")
                    return view.user_input
            return None

        role_done_cb = _build_role_cb

    # Step 1: run the developer team discussion
    discussion, final_outcome = await run_company_discussion(
        task, role_list, role_done_cb=role_done_cb
    )

    if not posts_done_in_cb:
        for idx, (role, reply) in enumerate(discussion):
            context_note = _prior_context_note(idx)
            msg = f"👤 **{role}** {context_note}\n{reply}"
            for chunk in split_message(msg):
                await send(chunk)

    final_msg = f"---\n✅ **Final Plan**\n\n{final_outcome}"
    for chunk in split_message(final_msg):
        await send(chunk)

    # Step 2: generate code files
    await send("💻 *Generating code files…*")
    code_files, raw_output = await generate_code_files(task, discussion, final_outcome)

    # Helper: store session under both parent channel id and thread id so
    # /followup works whether invoked from the thread or the parent channel.
    def _store_session(code: list[tuple[str, str]]) -> None:
        session: dict = {
            "task": task,
            "discussion": discussion,
            "final_outcome": final_outcome,
            "code_files": code,
            "project_slug": project_slug,
            "thread_id": thread.id if thread else None,
        }
        channel_id = interaction.channel_id or 0
        build_sessions[channel_id] = session
        if thread:
            build_sessions[thread.id] = session

    if not code_files:
        await send(
            "⚠️ No structured code files were detected in the AI output. "
            "The raw output follows:"
        )
        for chunk in split_message(raw_output or "*No output.*"):
            await send(chunk)
        # Still save the session so /followup can be used for refinement
        _store_session([])
        await send(
            "💬 *You can still use `/followup` to ask questions or request a retry.*"
        )
        return

    files_list = "\n".join(f"• `{fn}`" for fn, _ in code_files)
    await send(
        f"📦 **{len(code_files)} file(s) generated:**\n{files_list}\n\n"
        "*Saving to GitHub…*"
    )

    # Step 3: commit to GitHub
    committed_urls, folder_url = await commit_project(
        project_slug, task, final_outcome, code_files
    )

    if committed_urls:
        url_lines = "\n".join(f"• {u}" for u in committed_urls[:20])
        extra = f"\n*(and {len(committed_urls) - 20} more)*" if len(committed_urls) > 20 else ""
        folder_line = f"\n\n📂 **Project folder:** {folder_url}" if folder_url else ""
        await send(
            f"✅ **Project saved to GitHub!**\n{url_lines}{extra}{folder_line}"
        )
    elif GITHUB_TOKEN and GITHUB_REPOSITORY:
        await send(
            "⚠️ Could not commit files to GitHub. Check the bot logs for details."
        )
    else:
        await send(
            "ℹ️ GitHub integration is not configured — files were not saved to the repository.\n"
            "Set the `GITHUB_TOKEN` and `GITHUB_REPOSITORY` environment variables to enable saving."
        )

    # Store the session for /followup
    _store_session(code_files)
    await send(
        "💬 *Project session saved. Use `/followup` to ask questions or request amendments.*"
    )


@bot.tree.command(
    name="followup",
    description="Ask a follow-up question or request amendments to the last /build output",
)
@app_commands.describe(
    request="Your question or amendment request about the last generated project",
)
async def followup_slash(interaction: discord.Interaction, request: str):
    await interaction.response.defer(thinking=True)

    channel_id = interaction.channel_id or 0
    session_data = build_sessions.get(channel_id)

    # Fallback: when invoked from inside a thread that isn't the build thread,
    # try the thread's parent channel so the session is still found.
    if not session_data:
        ch = interaction.channel
        if isinstance(ch, discord.Thread) and ch.parent_id:
            session_data = build_sessions.get(ch.parent_id)

    if not session_data:
        await interaction.followup.send(
            "⚠️ No previous build session found in this channel. "
            "Run `/build` first, then use `/followup` to continue the conversation."
        )
        return

    task = session_data["task"]
    discussion: list[tuple[str, str]] = session_data["discussion"]
    final_outcome: str = session_data["final_outcome"]
    code_files: list[tuple[str, str]] = session_data.get("code_files", [])
    project_slug: str = session_data.get("project_slug", "project")

    logger.info(
        "Follow-up request | project=%s | request=%r", project_slug, request
    )

    # Build context for the AI (truncate large files to keep the prompt manageable)
    context = f"**Original Task:** {task}\n\n"
    context += "**Developer Team Discussion:**\n"
    for role, reply in discussion:
        context += f"\n**{role}:** {reply}\n"
    context += f"\n**Final Plan:**\n{final_outcome}\n"

    if code_files:
        context += "\n**Previously Generated Files:**\n"
        for filename, content in code_files:
            preview = content[:600] + "\n…(truncated)" if len(content) > 600 else content
            context += f"\n### File: {filename}\n```\n{preview}\n```\n"

    followup_prompt = (
        f"{context}\n\n"
        f"**Follow-up Request:** {request}\n\n"
        "Answer the follow-up question clearly. If the request involves modifying or "
        "adding code, use the standard `### File: <filename>` / ``` format so the "
        "changes can be committed automatically."
    )

    messages = [
        {
            "role": "system",
            "content": (
                "You are a senior software engineer helping to refine and extend a "
                "previously generated project. Provide clear, actionable responses. "
                "When modifying or generating code files, always use the "
                "`### File: <filename>` / ``` format."
            ),
        },
        {"role": "user", "content": followup_prompt},
    ]

    async with aiohttp.ClientSession() as http_session:
        try:
            reply = await call_ai(http_session, messages)
        except Exception as exc:
            logger.error("Follow-up AI call failed: %s", exc)
            await interaction.followup.send("⚠️ AI request failed. Please try again.")
            return

    # Route the response to the build thread when one exists
    thread_id = session_data.get("thread_id")
    send = interaction.followup.send  # default
    if thread_id:
        try:
            thread_channel = bot.get_channel(thread_id) or await bot.fetch_channel(thread_id)
            # Only redirect to the thread when the user isn't already inside it.
            # This ensures the deferred "Thinking…" interaction is always resolved
            # via interaction.followup.send and avoids "Application did not respond".
            if thread_channel.id != (interaction.channel_id or 0):
                send = thread_channel.send  # type: ignore[assignment]
                # Acknowledge the original interaction so Discord resolves "Thinking…"
                await interaction.followup.send(
                    "💬 *Responding in the build thread…*", ephemeral=True
                )
        except Exception as exc:
            logger.warning("Could not retrieve build thread %s: %s", thread_id, exc)

    await send(f"💬 **Follow-up:** {request[:120]}")
    for chunk in split_message(reply):
        await send(chunk)

    # Check for new/amended code files in the response
    amended_files = parse_code_files(reply)
    if amended_files:
        # Merge into the session so future /followup calls see the latest state
        existing = dict(code_files)
        for fn, content in amended_files:
            existing[fn] = content
        session_data["code_files"] = list(existing.items())

        if GITHUB_TOKEN and GITHUB_REPOSITORY:
            await send(
                f"📝 *{len(amended_files)} file(s) amended. Saving to GitHub…*"
            )
            committed_urls, folder_url = await commit_project(
                project_slug, task, final_outcome, amended_files
            )
            if committed_urls:
                url_lines = "\n".join(f"• {u}" for u in committed_urls[:10])
                extra = (
                    f"\n*(and {len(committed_urls) - 10} more)*"
                    if len(committed_urls) > 10
                    else ""
                )
                await send(
                    f"✅ **Amendments saved to GitHub:**\n{url_lines}{extra}"
                )
            else:
                await send(
                    "⚠️ Could not commit amended files to GitHub."
                )
        else:
            files_list = "\n".join(f"• `{fn}`" for fn, _ in amended_files)
            await send(
                f"📝 *{len(amended_files)} file(s) included in the response above:*\n"
                f"{files_list}\n"
                "*(GitHub integration not configured — files were not saved automatically.)*"
            )


# ---------------------------------------------------------------------------
# /autorun command — fully autonomous build with user interrupt capability
# ---------------------------------------------------------------------------

_STACK_EMOJI: dict[str, str] = {"python": "🐍", "php": "🐘", "actions": "⚙️"}


@bot.tree.command(
    name="autorun",
    description=(
        "Let the AI autonomously pick and build a programming project — "
        "you can interrupt after any role to steer the discussion"
    ),
)
@app_commands.describe(
    stack=(
        "Preferred tech stack. Leave blank for AI to choose automatically."
    ),
)
@app_commands.choices(stack=[
    app_commands.Choice(name="Python (Flask / FastAPI / CLI)", value="python"),
    app_commands.Choice(name="PHP + HTML (web app / API)", value="php"),
    app_commands.Choice(name="GitHub Actions workflow (CI/CD)", value="actions"),
])
async def autorun_slash(
    interaction: discord.Interaction,
    stack: app_commands.Choice[str] | None = None,
):
    await interaction.response.defer(thinking=True)

    stack_value = stack.value if stack else None

    # Step 1: AI generates a task idea and (if not overridden) the tech stack
    async with aiohttp.ClientSession() as _setup_session:
        task, chosen_stack = await generate_auto_task(_setup_session, stack_value)
        project_slug = await generate_project_name(_setup_session, task)

    role_list = list(DEFAULT_BUILD_ROLES)
    stack_emoji = _STACK_EMOJI.get(chosen_stack, "💻")

    logger.info(
        "AutoRun started | task=%r | project=%s | stack=%s",
        task,
        project_slug,
        chosen_stack,
    )

    header = (
        f"🤖 **AI AutoRun — Autonomous Build Session**\n"
        f"📋 **Task:** {task}\n"
        f"📁 **Project:** `{project_slug}`\n"
        f"🛠️ **Stack:** {stack_emoji} `{chosen_stack}`\n"
        f"👥 **Team:** {', '.join(role_list)}\n"
        f"📡 *Running autonomously — click **✏️ Add My Input** after any role to steer the discussion.*\n\n"
        "*Team discussion starting… this may take a moment.*"
    )
    header_msg = await interaction.followup.send(header)

    # Create a dedicated thread
    thread = await _create_task_thread(
        header_msg, f"🤖 {project_slug}"[:100], interaction.channel
    )
    send = thread.send if thread else interaction.followup.send

    # AutoRun always runs in interactive mode so the user can interject after
    # each role; the InterruptView auto-continues after its 90-second timeout.
    posts_done_in_cb = True

    async def _autorun_role_cb(role: str, reply: str) -> Optional[str]:
        role_idx = role_list.index(role)
        context_note = _prior_context_note(role_idx)
        msg = f"👤 **{role}** {context_note}\n{reply}"
        for chunk in split_message(msg):
            await send(chunk)

        remaining = role_list[role_idx + 1:]
        if remaining:
            view = InterruptView()
            await send(
                f"*Next: **{remaining[0]}** — continuing automatically in 90 s…*  "
                "Want to add your input first?",
                view=view,
            )
            await view.wait()
            if view.action == "input" and view.user_input:
                preview = (
                    view.user_input[:80] + "…"
                    if len(view.user_input) > 80
                    else view.user_input
                )
                await send(f"✅ *Your input noted: \"{preview}\"*")
                return view.user_input
        return None

    # Step 2: run developer team discussion
    discussion, final_outcome = await run_company_discussion(
        task, role_list, role_done_cb=_autorun_role_cb
    )

    final_msg = f"---\n✅ **Final Plan**\n\n{final_outcome}"
    for chunk in split_message(final_msg):
        await send(chunk)

    # Step 3: generate code files
    await send("💻 *Generating code files…*")
    code_files, raw_output = await generate_code_files(task, discussion, final_outcome)

    # Helper: persist session under channel id and thread id for /followup
    def _store_session(code: list[tuple[str, str]]) -> None:
        session_obj: dict = {
            "task": task,
            "discussion": discussion,
            "final_outcome": final_outcome,
            "code_files": code,
            "project_slug": project_slug,
            "thread_id": thread.id if thread else None,
        }
        channel_id = interaction.channel_id or 0
        build_sessions[channel_id] = session_obj
        if thread:
            build_sessions[thread.id] = session_obj

    if not code_files:
        await send(
            "⚠️ No structured code files were detected in the AI output. "
            "The raw output follows:"
        )
        for chunk in split_message(raw_output or "*No output.*"):
            await send(chunk)
        _store_session([])
        await send("💬 *Use `/followup` to ask questions or request a retry.*")
        return

    files_list = "\n".join(f"• `{fn}`" for fn, _ in code_files)
    await send(
        f"📦 **{len(code_files)} file(s) generated:**\n{files_list}\n\n"
        "*Saving to GitHub…*"
    )

    # Step 4: commit to GitHub
    committed_urls, folder_url = await commit_project(
        project_slug, task, final_outcome, code_files
    )

    if committed_urls:
        url_lines = "\n".join(f"• {u}" for u in committed_urls[:20])
        extra = f"\n*(and {len(committed_urls) - 20} more)*" if len(committed_urls) > 20 else ""
        folder_line = f"\n\n📂 **Project folder:** {folder_url}" if folder_url else ""
        await send(
            f"✅ **Project saved to GitHub!**\n{url_lines}{extra}{folder_line}"
        )
    elif GITHUB_TOKEN and GITHUB_REPOSITORY:
        await send("⚠️ Could not commit files to GitHub. Check bot logs for details.")
    else:
        await send(
            "ℹ️ GitHub integration not configured — files were not saved to the repository.\n"
            "Set `GITHUB_TOKEN` and `GITHUB_REPOSITORY` to enable saving."
        )

    _store_session(code_files)
    await send(
        "💬 *AutoRun session saved. Use `/followup` to ask questions or request amendments.*"
    )


@bot.tree.command(
    name="company_roles",
    description="List all available company roles for the /company and /build commands",
)
async def company_roles_slash(interaction: discord.Interaction):
    await interaction.response.defer()

    lines = [
        "**🏢 Available Company Roles**",
        "",
        "**Default roles** (used when no `roles` argument is given to `/company`):",
    ]
    for role in DEFAULT_ROLES:
        lines.append(f"• `{role}`")

    lines += ["", "**Default developer team** (used by `/build`):"]
    for role in DEFAULT_BUILD_ROLES:
        lines.append(f"• `{role}`")

    lines += ["", "**All built-in roles:**"]
    for role, prompt in ROLE_PROMPTS.items():
        # Extract the focus sentence (second sentence of the prompt)
        sentences = prompt.split(". ")
        focus = sentences[1].lstrip("Focus on ") if len(sentences) > 1 else ""
        lines.append(f"• `{role}` — {focus}")

    lines += [
        "",
        "**Custom roles** — supply any role name not in the list above.",
        "The bot generates a suitable system prompt automatically.",
        "",
        "**Usage examples:**",
        "```",
        "/company task:Build a mobile app",
        "/company task:Launch a product roles:CEO,CTO,Marketing Manager",
        "/build task:Create a REST API in Python",
        "/build task:Build a React dashboard roles:CTO,Frontend Developer,QA Engineer",
        "```",
    ]

    content = "\n".join(lines)
    for chunk in split_message(content):
        await interaction.followup.send(chunk)


@bot.tree.command(
    name="about",
    description="Show a guide on how to use the AI Company bot",
)
async def about_slash(interaction: discord.Interaction):
    default_roles_str = "\n".join(f"• {r}" for r in DEFAULT_ROLES)
    build_roles_str = "\n".join(f"• {r}" for r in DEFAULT_BUILD_ROLES)
    msg = (
        "**🏢 AI Company Bot — How to Use**\n\n"
        "Simulate a company brainstorming session or have a developer team generate "
        "and save code to the `project/` folder in the repository.\n\n"
        "**💬 Auto-threads (討論串)**\n"
        "Every `/company`, `/build`, and `/autorun` task automatically creates a dedicated "
        "Discord thread. All role responses, the final outcome, and `/followup` replies are "
        "posted inside that thread, keeping your main channel clean.\n\n"
        "**⚡ Slash Commands**\n"
        "• `/company task:[desc]` — Discussion with default company roles\n"
        "• `/company task:[desc] roles:[r1,r2,…]` — Discussion with specific roles\n"
        "• `/company task:[desc] interactive:True` — Pause after each role so **you** can "
        "add your perspective before the next role responds\n"
        "• `/build task:[desc]` — Developer team discussion + code gen → saved to `project/`; "
        "shows a role-picker dropdown when no roles are specified; project name is AI-generated\n"
        "• `/build task:[desc] roles:[r1,r2,…]` — Skip the dropdown and use specific roles\n"
        "• `/build task:[desc] interactive:True` — Same interactive mode for builds\n"
        "• `/autorun` — **Fully autonomous mode**: the AI picks a task and builds it "
        "from scratch (Python / PHP+HTML / GitHub Actions); you can interrupt after any role\n"
        "• `/autorun stack:python` — Force a specific tech stack for the autonomous build\n"
        "• `/followup request:[...]` — Ask questions or request amendments **after** `/build` or `/autorun`\n"
        "• `/company_roles` — List all available roles\n"
        "• `/about` — Show this help message\n\n"
        "**📡 Cross-role communication**\n"
        "Every role reads *all prior responses* before contributing — confirmed by the "
        "*(read N prior response(s))* indicator shown next to each role.\n\n"
        f"**👥 Default Company Roles**\n{default_roles_str}\n\n"
        f"**🛠️ Default Developer Team (for /build and /autorun)**\n{build_roles_str}\n\n"
        "**💡 Examples**\n"
        "```\n"
        "/company task:Build a food delivery app\n"
        "/company task:Launch a campaign roles:CEO,Marketing Manager,Designer interactive:True\n"
        "/build task:Create a REST API for a todo app in Python\n"
        "/build task:Build a React todo dashboard interactive:True\n"
        "/autorun\n"
        "/autorun stack:php\n"
        "/followup request:Add user authentication to the API\n"
        "```"
    )
    await interaction.response.send_message(msg)


def main():
    if not DISCORD_TOKEN:
        logger.error(
            "DISCORD_TOKEN_COMPANY is not set or is empty. "
            "Add it as a repository secret under Settings → Secrets and variables → Actions "
            "(see ai-company/SETUP.md for instructions)."
        )
        raise SystemExit(1)
    if not POLLINATIONS_TOKEN:
        logger.error(
            "POLLINATIONS_TOKEN is not set or is empty. "
            "Add it as a repository secret under Settings → Secrets and variables → Actions "
            "(see ai-company/SETUP.md for instructions)."
        )
        raise SystemExit(1)
    try:
        bot.run(DISCORD_TOKEN)
    except discord.errors.LoginFailure as exc:
        logger.error(
            "Failed to log in to Discord: %s — "
            "check that DISCORD_TOKEN_COMPANY is a valid bot token.",
            exc,
        )
        raise SystemExit(1) from exc


if __name__ == "__main__":
    main()

