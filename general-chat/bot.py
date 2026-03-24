import asyncio
import json
import logging
import os
from typing import AsyncGenerator, Callable, Coroutine, Any

import aiohttp
import discord
from discord import app_commands
from discord.ext import commands

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)

DISCORD_TOKEN = os.environ.get("DISCORD_TOKEN", "")
POLLINATIONS_TOKEN = os.environ.get("POLLINATIONS_TOKEN", "")

AI_API_URL = "https://gen.pollinations.ai/v1/chat/completions"

# Model fallback chain (openai-fast appears twice intentionally)
MODEL_CHAIN = [
    "openai-fast",
    "gemini-search",
    "openai-fast",
    "openai",
    "glm",
    "claude-fast",
    "qwen-character",
    "deepseek",
    "qwen-safety",
]

# Unique set of all selectable model names (preserves original chain minus duplicates)
ALL_MODELS: set[str] = set(MODEL_CHAIN)

# Models that accept image input (vision)
VISION_MODELS: set[str] = {
    "openai",
    "openai-fast",
    "gemini",
    "gemini-fast",
    "gemini-large",
    "gemini-search",
    "claude-fast",
}

# Human-readable info for each model: (short description, supports_vision)
MODEL_INFO: dict[str, tuple[str, bool]] = {
    "openai-fast": ("Fast OpenAI model — default first choice", True),
    "openai": ("Full OpenAI model", True),
    "gemini-search": ("Gemini with Google Search grounding", True),
    "gemini": ("Standard Gemini model", True),
    "gemini-fast": ("Faster Gemini variant", True),
    "gemini-large": ("Larger Gemini variant", True),
    "claude-fast": ("Fast Claude model", True),
    "glm": ("GLM model", False),
    "qwen-character": ("Qwen character model", False),
    "deepseek": ("DeepSeek model", False),
    "qwen-safety": ("Qwen safety-focused model", False),
}

# Static choices list for the /ask model parameter (shown immediately in Discord UI).
# Discord caps slash-command choices at 25; MODEL_INFO has fewer than that.
MODEL_CHOICES: list[app_commands.Choice[str]] = [
    app_commands.Choice(
        name=f"{model}{' [vision]' if MODEL_INFO.get(model, ('', False))[1] else ''}",
        value=model,
    )
    for model in sorted(MODEL_INFO)
][:25]

DISCORD_MAX_LENGTH = 2000

# Minimum seconds between Discord message edits while streaming (rate-limit safety).
STREAM_EDIT_INTERVAL = 1.5

# Maximum characters shown in a streaming placeholder edit.  Kept slightly
# below DISCORD_MAX_LENGTH so the appended "▌" cursor never pushes past 2000.
STREAM_DISPLAY_LIMIT = 1950

# Maximum number of messages (user + assistant) to keep per channel for context.
# 20 messages = 10 conversation turns.
MAX_HISTORY = 20

intents = discord.Intents.default()
intents.message_content = True

bot = commands.Bot(command_prefix=commands.when_mentioned, intents=intents)

# Per-channel (or per-DM) conversation history.
# Key: channel / thread ID.  Value: list of {"role": ..., "content": ...} dicts.
conversation_history: dict[int, list[dict]] = {}

# Per-user preferred model set via /settings (in-memory, resets on bot restart).
user_preferred_models: dict[int, str] = {}

# Tracks in-progress AI requests so they can be cancelled via /cancel.
# Key: user ID.  Value: the asyncio.Task for that request.
active_requests: dict[int, asyncio.Task] = {}


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def build_about_message() -> str:
    """Return a formatted help/about message listing all @ prefixes and usage."""
    lines = [
        "**🤖 AI Discord Bot — How to Use**",
        "",
        "Mention me in any channel (or send me a DM) followed by your question.",
        "You can optionally prefix your message with `@<model>` to choose a specific AI model.",
        "",
        "**📌 Usage**",
        "```",
        "@BotName <your question>",
        "@BotName @<model> <your question>   ← use a specific model",
        "@BotName @ai <your question>        ← use default model chain",
        "@BotName @about                     ← show this help message",
        "```",
        "You can also attach images — vision-capable models will analyse them.",
        "",
        "**📋 Available `@model` prefixes**",
        "```",
        f"{'Prefix':<22} {'Vision':<8} Description",
        "-" * 60,
    ]
    for model in sorted(MODEL_INFO):
        desc, vision = MODEL_INFO[model]
        vision_mark = "✅" if vision else "  "
        lines.append(f"@{model:<21} {vision_mark:<8} {desc}")
    lines += [
        "```",
        "",
        "**⚡ Slash Commands**",
        "• `/ask question:[prompt] model:[optional]` — Ask a question; pick a model from the dropdown.",
        "• `/interrupt perspective:[text]` — Inject your point of view mid-request and have the AI continue from there.",
        "• `/cancel` — Hard-cancel your current in-progress AI request.",
        "• `/about` — Show this help guide.",
        "• `/models` — List all available AI models.",
        "• `/settings model:[optional]` — View or set your preferred AI model.",
    ]
    return "\n".join(lines)


def build_model_chain(preferred_model: str | None) -> list[str]:
    """Return a model chain that starts with *preferred_model* (if given) and
    uses the remaining models from MODEL_CHAIN as fallbacks."""
    if preferred_model is None:
        return MODEL_CHAIN
    # Remove all occurrences of the preferred model from the default chain so
    # it is only tried once (at the front), then fall back through the rest.
    rest = [m for m in MODEL_CHAIN if m != preferred_model]
    return [preferred_model] + rest


def parse_model_prefix(content: str) -> tuple[str | None, str]:
    """Detect an optional ``@<model-name>``, ``@ai``, or ``@about`` prefix in *content*.

    Returns ``(token, remaining_content)`` where *token* can be:

    * ``"about"``   – the user wants the help/about message.
    * a model name  – a recognised model from ``ALL_MODELS``.
    * ``None``      – no recognised prefix (or ``@ai``, which means "default chain").
    """
    stripped = content.strip()
    candidate = stripped[1:] if stripped.startswith("@") else stripped  # remove at most one leading '@'

    parts = candidate.split(None, 1)
    if not parts:
        return None, content

    first_word = parts[0].lower()
    remainder = parts[1].strip() if len(parts) > 1 else ""

    # @about shows the usage/help guide
    if first_word == "about":
        return "about", remainder

    # @ai is an explicit alias meaning "use the default chain"
    if first_word == "ai":
        return None, remainder

    if first_word in ALL_MODELS:
        return first_word, remainder

    # No recognised model prefix – return the original content unchanged
    return None, content


async def call_ai(
    session: aiohttp.ClientSession,
    model: str,
    user_message: str,
    image_urls: list[str] | None = None,
    history: list[dict] | None = None,
) -> str:
    headers = {
        "Authorization": f"Bearer {POLLINATIONS_TOKEN}",
        "Content-Type": "application/json",
    }

    # Build the message content.  Use the multi-part vision format only when
    # the model is known to support images and the user actually attached some.
    if image_urls and model in VISION_MODELS:
        message_content: list[dict[str, object]] | str = [{"type": "text", "text": user_message}]
        for url in image_urls:
            message_content.append({"type": "image_url", "image_url": {"url": url}})
    else:
        message_content = user_message

    # Build the messages list: prior conversation history + current user turn.
    messages: list[dict] = list(history) if history else []
    messages.append({"role": "user", "content": message_content})

    payload = {
        "model": model,
        "messages": messages,
    }
    async with session.post(
        AI_API_URL,
        json=payload,
        headers=headers,
        timeout=aiohttp.ClientTimeout(total=30),
    ) as resp:
        resp.raise_for_status()
        data = await resp.json()
        return data["choices"][0]["message"]["content"]


async def _iter_stream_chunks(
    session: aiohttp.ClientSession,
    model: str,
    user_message: str,
    image_urls: list[str] | None = None,
    history: list[dict] | None = None,
) -> AsyncGenerator[str, None]:
    """Yield text tokens from the AI API using Server-Sent Events (SSE) streaming."""
    headers = {
        "Authorization": f"Bearer {POLLINATIONS_TOKEN}",
        "Content-Type": "application/json",
    }

    if image_urls and model in VISION_MODELS:
        message_content: list[dict[str, object]] | str = [{"type": "text", "text": user_message}]
        for url in image_urls:
            message_content.append({"type": "image_url", "image_url": {"url": url}})
    else:
        message_content = user_message

    messages_list: list[dict] = list(history) if history else []
    messages_list.append({"role": "user", "content": message_content})

    payload = {"model": model, "messages": messages_list, "stream": True}
    async with session.post(
        AI_API_URL,
        json=payload,
        headers=headers,
        timeout=aiohttp.ClientTimeout(total=120),
    ) as resp:
        resp.raise_for_status()
        pending = ""
        async for raw in resp.content.iter_any():
            pending += raw.decode("utf-8", errors="replace")
            while "\n" in pending:
                line, pending = pending.split("\n", 1)
                line = line.strip()
                if not line.startswith("data: "):
                    continue
                data_str = line[6:]
                if data_str == "[DONE]":
                    return
                try:
                    obj = json.loads(data_str)
                    delta = obj["choices"][0]["delta"].get("content") or ""
                    if delta:
                        yield delta
                except (json.JSONDecodeError, KeyError, IndexError):
                    pass


async def get_ai_reply_streaming(
    user_message: str,
    preferred_model: str | None = None,
    image_urls: list[str] | None = None,
    history: list[dict] | None = None,
    progress_cb: Callable[[str], Coroutine[Any, Any, None]] | None = None,
) -> tuple[str, str | None, bool]:
    """Stream the AI reply and return ``(reply_text, model_used, is_fallback)``.

    *progress_cb* is an async callable that receives the accumulated text so
    far.  It is called at most once every *STREAM_EDIT_INTERVAL* seconds so the
    caller can update a Discord message progressively.

    Falls back to non-streaming ``call_ai`` when SSE yields no tokens.
    """
    chain = build_model_chain(preferred_model)

    if image_urls:
        chain = [m for m in chain if m in VISION_MODELS]
        if not chain:
            return (
                "⚠️ No vision-capable models are available right now. "
                "Please try again later or send a text-only message.",
                None,
                False,
            )

    first_model = chain[0]
    last_progress = 0.0

    async with aiohttp.ClientSession() as session:
        for model in chain:
            accumulated = ""
            try:
                async for chunk in _iter_stream_chunks(
                    session, model, user_message, image_urls, history
                ):
                    accumulated += chunk
                    if progress_cb is not None:
                        now = asyncio.get_running_loop().time()
                        if now - last_progress >= STREAM_EDIT_INTERVAL:
                            try:
                                await progress_cb(accumulated)
                                last_progress = now
                            except Exception:
                                pass

                if accumulated:
                    logger.info(
                        "Streaming reply from model %s (len=%d)", model, len(accumulated)
                    )
                    return accumulated, model, (model != first_model)

                # SSE returned no tokens — fall back to a regular non-streaming call
                logger.warning(
                    "Model %s streaming returned empty; falling back to non-streaming.", model
                )
                accumulated = await call_ai(session, model, user_message, image_urls, history)
                logger.info("Non-streaming fallback reply from model %s", model)
                return accumulated, model, (model != first_model)

            except asyncio.CancelledError:
                raise
            except Exception as exc:
                logger.warning(
                    "Model %s failed (streaming): %s. Trying next model...", model, exc
                )

    return "Sorry, all AI models are currently unavailable. Please try again later.", None, False


async def get_ai_reply(
    user_message: str,
    preferred_model: str | None = None,
    image_urls: list[str] | None = None,
    history: list[dict] | None = None,
) -> tuple[str, str | None, bool]:
    """Return ``(reply_text, model_used, is_fallback)``.

    *model_used* is ``None`` when every model in the chain failed.
    *is_fallback* is ``True`` when the first model in the effective chain failed
    and a subsequent model was used instead.

    If *image_urls* is provided, the chain is automatically filtered to only
    vision-capable models (vision-aware routing).
    """
    chain = build_model_chain(preferred_model)

    # Vision-aware routing: only attempt models that can handle images.
    if image_urls:
        chain = [m for m in chain if m in VISION_MODELS]
        if not chain:
            return (
                "⚠️ No vision-capable models are available right now. "
                "Please try again later or send a text-only message.",
                None,
                False,
            )

    first_model = chain[0]
    async with aiohttp.ClientSession() as session:
        for model in chain:
            try:
                reply = await call_ai(session, model, user_message, image_urls, history)
                logger.info("Got reply from model %s", model)
                return reply, model, (model != first_model)
            except Exception as exc:
                logger.warning("Model %s failed: %s. Trying next model...", model, exc)
    return "Sorry, all AI models are currently unavailable. Please try again later.", None, False


def _open_fence(text: str) -> str | None:
    """Return the opening fence token (e.g. ``'```python'``) if *text* ends with
    an unclosed Markdown code fence, otherwise ``None``.

    Walks every triple-backtick occurrence in order, toggling between "open" and
    "closed" states and capturing the language identifier of each opening fence.
    """
    open_token: str | None = None
    pos = 0
    while True:
        idx = text.find("```", pos)
        if idx == -1:
            break
        if open_token is None:
            # New opening fence – capture optional language identifier.
            rest = text[idx + 3 :]
            nl = rest.find("\n")
            lang = rest[:nl].strip() if nl != -1 else rest.strip()
            open_token = "```" + lang
        else:
            # Closing fence – fence is now balanced.
            open_token = None
        pos = idx + 3
    return open_token


def split_message(text: str, limit: int = DISCORD_MAX_LENGTH) -> list[str]:
    """Split text into chunks no larger than *limit* characters.

    Prefers splitting on newlines, then spaces, to avoid cutting words.
    Closes any open Markdown code fences (triple backticks) at the end of each
    chunk and re-opens them (preserving the language identifier) at the start of
    the next chunk to keep Discord formatting intact across splits.
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

        chunk = text[:split_pos]

        # Close any open code fence and reopen it in the next chunk, preserving
        # the language identifier so syntax highlighting continues correctly.
        fence = _open_fence(chunk)
        if fence is not None:
            chunk += "\n```"
            text = fence + "\n" + text[split_pos:].lstrip("\n")
        else:
            text = text[split_pos:].lstrip("\n")

        chunks.append(chunk)

    if text:
        chunks.append(text)
    return chunks


def _fallback_footer(model_used: str | None, preferred_model: str | None, is_fallback: bool) -> str:
    """Return a footer string when the bot used a fallback model, or an empty string."""
    if not model_used:
        return ""
    if is_fallback:
        return f"\n\n*— Response generated by **{model_used}** (fallback)*"
    if preferred_model and model_used != preferred_model:
        return f"\n\n*— Response generated by **{model_used}** (fallback from {preferred_model})*"
    return ""


def get_image_urls(message: discord.Message) -> list[str]:
    """Return the URLs of all image attachments in *message*."""
    return [
        a.url
        for a in message.attachments
        if a.content_type and a.content_type.startswith("image/")
    ]


def _update_history(channel_id: int, user_text: str, assistant_reply: str) -> None:
    """Append the latest exchange to the channel's conversation history and
    trim to at most *MAX_HISTORY* messages."""
    history = conversation_history.setdefault(channel_id, [])
    history.append({"role": "user", "content": user_text})
    history.append({"role": "assistant", "content": assistant_reply})
    if len(history) > MAX_HISTORY:
        conversation_history[channel_id] = history[-MAX_HISTORY:]


# ---------------------------------------------------------------------------
# Bot events
# ---------------------------------------------------------------------------


@bot.event
async def on_ready():
    await bot.tree.sync()
    logger.info("Logged in as %s (ID: %s)", bot.user, bot.user.id)


# ---------------------------------------------------------------------------
# Slash commands
# ---------------------------------------------------------------------------


@bot.tree.command(name="ask", description="Ask the AI a question with optional model selection")
@app_commands.describe(
    question="Your question or prompt for the AI",
    model="AI model to use (leave blank for automatic selection)",
)
@app_commands.choices(model=MODEL_CHOICES)
async def ask_slash(interaction: discord.Interaction, question: str, model: str | None = None):
    preferred_model = model if model else None
    await interaction.response.defer(thinking=True)

    history_key = interaction.channel_id if interaction.channel_id is not None else interaction.user.id
    history = conversation_history.get(history_key, [])

    # Send a streaming placeholder that will be progressively edited.
    placeholder_msg = await interaction.followup.send("▌")

    async def _on_progress(text: str) -> None:
        display = text[-STREAM_DISPLAY_LIMIT:] + "▌" if len(text) > STREAM_DISPLAY_LIMIT else text + "▌"
        try:
            await placeholder_msg.edit(content=display)
        except discord.HTTPException:
            pass

    task = asyncio.create_task(
        get_ai_reply_streaming(question, preferred_model, history=history, progress_cb=_on_progress)
    )
    active_requests[interaction.user.id] = task
    try:
        reply, model_used, is_fallback = await task
    except asyncio.CancelledError:
        await placeholder_msg.edit(content="⛔ Your in-progress request has been cancelled.")
        return
    finally:
        active_requests.pop(interaction.user.id, None)

    # Update conversation history on success.
    if model_used:
        _update_history(history_key, question, reply)

    # Append a footer when the bot fell back to a different model than requested.
    display_reply = reply + _fallback_footer(model_used, preferred_model, is_fallback)

    chunks = split_message(display_reply)
    await placeholder_msg.edit(content=chunks[0])
    for chunk in chunks[1:]:
        await interaction.followup.send(chunk)


@bot.tree.command(
    name="interrupt",
    description="Inject your point of view to redirect the AI and have it continue from your perspective",
)
@app_commands.describe(
    perspective="Your point of view, correction, or additional context for the AI to consider"
)
async def interrupt_slash(interaction: discord.Interaction, perspective: str):
    # Cancel any running request for this user first.
    existing = active_requests.pop(interaction.user.id, None)
    if existing and not existing.done():
        existing.cancel()

    await interaction.response.defer(thinking=True)

    history_key = interaction.channel_id if interaction.channel_id is not None else interaction.user.id
    history = conversation_history.get(history_key, [])
    preferred = user_preferred_models.get(interaction.user.id)

    # Build a short word-boundary-safe preview for the header line.
    if len(perspective) > 80:
        cut = perspective[:80].rsplit(None, 1)[0] if " " in perspective[:80] else perspective[:80]
        preview = cut + "…"
    else:
        preview = perspective
    placeholder_msg = await interaction.followup.send(
        f"✏️ *Your perspective noted — generating response…* ▌"
    )

    async def _on_progress(text: str) -> None:
        display = text[-STREAM_DISPLAY_LIMIT:] + "▌" if len(text) > STREAM_DISPLAY_LIMIT else text + "▌"
        try:
            await placeholder_msg.edit(content=display)
        except discord.HTTPException:
            pass

    task = asyncio.create_task(
        get_ai_reply_streaming(perspective, preferred, history=history, progress_cb=_on_progress)
    )
    active_requests[interaction.user.id] = task
    try:
        reply, model_used, is_fallback = await task
    except asyncio.CancelledError:
        await placeholder_msg.edit(content="⛔ Interrupted.")
        return
    finally:
        active_requests.pop(interaction.user.id, None)

    if model_used:
        _update_history(history_key, perspective, reply)

    display_reply = reply + _fallback_footer(model_used, preferred, is_fallback)
    header = f"✏️ *Based on your perspective: \"{preview}\"*\n\n"
    chunks = split_message(header + display_reply)
    await placeholder_msg.edit(content=chunks[0])
    for chunk in chunks[1:]:
        await interaction.followup.send(chunk)


@bot.tree.command(name="cancel", description="Hard-cancel your current in-progress AI request")
async def cancel_slash(interaction: discord.Interaction):
    task = active_requests.pop(interaction.user.id, None)
    if task and not task.done():
        task.cancel()
        await interaction.response.send_message("⛔ Your in-progress request has been cancelled.")
    else:
        await interaction.response.send_message("You don't have any active request to cancel. Use `/ask` to start a new request.")


@bot.tree.command(name="about", description="Show a help guide with all available commands and models")
async def about_slash(interaction: discord.Interaction):
    await interaction.response.send_message(build_about_message())


@bot.tree.command(name="models", description="List all available AI models with their capabilities")
async def models_slash(interaction: discord.Interaction):
    lines = ["**📋 Available AI Models**", ""]
    for model in sorted(MODEL_INFO):
        desc, vision = MODEL_INFO[model]
        vision_mark = "✅" if vision else "❌"
        lines.append(f"**`{model}`** {vision_mark} — {desc}")
    lines += [
        "",
        "*Tip: Use `/ask` and pick a model from the dropdown, or mention me with `@<model>` in a message.*",
    ]
    await interaction.response.send_message("\n".join(lines))


@bot.tree.command(name="settings", description="View or set your preferred AI model")
@app_commands.describe(model="Your preferred AI model (leave blank to view current setting)")
@app_commands.choices(model=MODEL_CHOICES)
async def settings_slash(interaction: discord.Interaction, model: str | None = None):
    if model is None:
        current = user_preferred_models.get(interaction.user.id)
        if current:
            desc, vision = MODEL_INFO.get(current, ("Unknown model", False))
            vision_tag = " [vision]" if vision else ""
            await interaction.response.send_message(
                f"Your preferred model is **{current}**{vision_tag} — {desc}.\n"
                "Use `/settings model:...` to change it, or `/settings` with no argument to reset to auto."
            )
        else:
            await interaction.response.send_message(
                "You have no preferred model set. The bot uses automatic model selection.\n"
                "Use `/settings model:...` to set one."
            )
    else:
        user_preferred_models[interaction.user.id] = model
        desc, vision = MODEL_INFO.get(model, ("Unknown model", False))
        vision_tag = " [vision]" if vision else ""
        await interaction.response.send_message(
            f"✅ Preferred model set to **{model}**{vision_tag} — {desc}.\n"
            "Your preference will be used whenever you mention me without an explicit `@model` prefix."
        )


# ---------------------------------------------------------------------------
# Message event
# ---------------------------------------------------------------------------


@bot.event
async def on_message(message: discord.Message):
    # Ignore messages from the bot itself
    if message.author == bot.user:
        return

    # Only respond to direct mentions or DMs
    if bot.user.mentioned_in(message) or isinstance(message.channel, discord.DMChannel):
        # Strip the bot mention from the message content
        content = message.content
        for mention in message.mentions:
            content = content.replace(f"<@{mention.id}>", "").replace(f"<@!{mention.id}>", "")
        content = content.strip()

        # Detect optional @<model-name>, @ai, or @about prefix
        token, content = parse_model_prefix(content)

        # @about → send the usage/help guide
        if token == "about":
            await message.reply(build_about_message())
            return

        # Determine preferred model: explicit @model prefix > /settings preference > auto
        if token is not None:
            preferred_model: str | None = token
        else:
            preferred_model = user_preferred_models.get(message.author.id)

        # Collect image attachments (for vision-capable models)
        image_urls = get_image_urls(message)

        # Warn when the user explicitly chose a non-vision model but attached images.
        # Automatically fall back to vision-aware routing so the image is not silently ignored.
        if image_urls and preferred_model and preferred_model not in VISION_MODELS:
            await message.reply(
                f"⚠️ **{preferred_model}** doesn't support image input. "
                "I'll automatically switch to a vision-capable model for this request."
            )
            preferred_model = None  # Vision-aware routing will pick the right model

        if not content and not image_urls:
            def _model_line(m: str) -> str:
                desc, _ = MODEL_INFO.get(m, ("", False))
                return f"• `@{m}` — {desc}"

            model_list = "\n".join(_model_line(m) for m in sorted(ALL_MODELS))
            await message.reply(
                "Please send a message (or attach an image) for me to reply to!\n\n"
                "**💡 Tips:**\n"
                "• Prefix with `@<model>` to pick a specific AI model.\n"
                "• Mention me with `@about` to see the full usage guide.\n"
                "• Use the `/ask` slash command for quick access with autocomplete.\n\n"
                f"**Available models:**\n{model_list}"
            )
            return

        # When only an image is sent with no text, use a sensible default prompt
        if not content:
            content = "Describe this image."

        # ------------------------------------------------------------------
        # Thread-based conversations: create a Public Thread from the message
        # when the bot is mentioned in a regular text channel.  This keeps the
        # main channel clean and groups the AI conversation in a sidebar thread.
        # ------------------------------------------------------------------
        reply_channel: discord.abc.Messageable = message.channel
        if isinstance(message.channel, discord.TextChannel):
            try:
                thread_name = f"AI Chat — {message.author.display_name}"[:100]
                reply_channel = await message.create_thread(
                    name=thread_name,
                    auto_archive_duration=60,
                )
            except discord.HTTPException as exc:
                logger.warning("Could not create thread: %s", exc)
                # Fall back to the original channel if thread creation fails

        # Retrieve conversation history for this channel / thread
        history_key = reply_channel.id
        history = conversation_history.get(history_key, [])

        # Send a streaming placeholder that will be progressively edited.
        if isinstance(reply_channel, discord.Thread):
            placeholder_msg = await reply_channel.send("▌")
        else:
            placeholder_msg = await message.reply("▌")

        async def _on_progress(text: str) -> None:
            display = text[-STREAM_DISPLAY_LIMIT:] + "▌" if len(text) > STREAM_DISPLAY_LIMIT else text + "▌"
            try:
                await placeholder_msg.edit(content=display)
            except discord.HTTPException:
                pass

        task = asyncio.create_task(
            get_ai_reply_streaming(content, preferred_model, image_urls, history, _on_progress)
        )
        active_requests[message.author.id] = task
        try:
            reply, model_used, is_fallback = await task
        except asyncio.CancelledError:
            await placeholder_msg.edit(content="⛔ Your in-progress request has been cancelled.")
            return
        finally:
            active_requests.pop(message.author.id, None)

        # Append fallback footer when a different model than intended was used.
        display_reply = reply + _fallback_footer(model_used, preferred_model, is_fallback)

        # Update conversation history on success.
        if model_used:
            _update_history(history_key, content, reply)

        chunks = split_message(display_reply)
        # Update the placeholder with the first chunk; send the rest as new messages.
        await placeholder_msg.edit(content=chunks[0])
        for chunk in chunks[1:]:
            await reply_channel.send(chunk)

    await bot.process_commands(message)


def main():
    if not DISCORD_TOKEN:
        logger.error(
            "DISCORD_TOKEN is not set or is empty. "
            "Add it as an environment variable before starting the bot."
        )
        raise SystemExit(1)
    if not POLLINATIONS_TOKEN:
        logger.error(
            "POLLINATIONS_TOKEN is not set or is empty. "
            "Add it as an environment variable before starting the bot."
        )
        raise SystemExit(1)
    try:
        bot.run(DISCORD_TOKEN)
    except discord.errors.LoginFailure as exc:
        logger.error(
            "Failed to log in to Discord: %s — "
            "check that DISCORD_TOKEN is a valid bot token.",
            exc,
        )
        raise SystemExit(1) from exc


if __name__ == "__main__":
    main()
