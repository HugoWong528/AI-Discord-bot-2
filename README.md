# AI Discord Bot

This repository contains **two separate Discord bots**, each in its own folder:

| Part | Folder | Description |
|---|---|---|
| 🗨️ **General Chat** | [`general-chat/`](general-chat/) | AI chatbot that replies to mentions and DMs using multiple AI models with automatic fallback. Responses stream to Discord in real-time. |
| 🏢 **AI Company** | [`ai-company/`](ai-company/) | Simulates a company discussion: give it a task, pick roles (CEO, CTO, Designer, …), and receive a structured **Final Outcome**. See [`ai-company/SETUP.md`](ai-company/SETUP.md). |

Both bots are powered by [Pollinations AI](https://pollinations.ai) and run on Python 3.11.  
Each has its own GitHub Actions workflow so they can be started independently.

For platform-specific deployment instructions (Linux, macOS, Windows, Docker, GitHub Actions) see **[PLATFORM.md](PLATFORM.md)**.  
For Vercel and always-on hosting options see **[VERCEL.md](VERCEL.md)**.  
For Railway.com (easiest always-on hosting) see **[RAILWAY.md](RAILWAY.md)**.

---

## Repository Structure

```
AI-discord-bot/
├── general-chat/
│   ├── bot.py              # General-purpose AI chat bot (streaming responses)
│   └── requirements.txt
├── ai-company/
│   ├── bot.py              # AI company simulation bot (interactive mode)
│   ├── requirements.txt
│   └── SETUP.md            # Detailed setup guide for the AI company bot
├── .github/workflows/
│   ├── discord-bot.yml             # Workflow: General Chat bot
│   └── discord-ai-company-bot.yml  # Workflow: AI Company bot
├── PLATFORM.md             # Platform-specific deployment guide
├── VERCEL.md               # Vercel / always-on hosting guide
├── RAILWAY.md              # Railway.com deployment guide (easiest always-on)
└── README.md
```

---

## Part 1 — General Chat Bot (`general-chat/`)

An AI-powered Discord bot that responds to mentions and direct messages using multiple AI models from [Pollinations AI](https://pollinations.ai). It automatically tries a chain of models (OpenAI, Gemini, Claude, DeepSeek, and more) so you always get a reply even when one model is unavailable.

Responses are **streamed to Discord in real-time** — the bot sends a placeholder message immediately and progressively updates it as tokens arrive, so you see the answer forming word-by-word instead of waiting for the entire reply.

**GitHub Actions secrets required:** `DISCORD_TOKEN`, `POLLINATIONS_TOKEN`

---

## Table of Contents

- [Prerequisites](#prerequisites)
- [Step 1 – Create a Discord Application & Bot](#step-1--create-a-discord-application--bot)
- [Step 2 – Get a Pollinations API Key](#step-2--get-a-pollinations-api-key)
- [Step 3 – Invite the Bot to Your Server](#step-3--invite-the-bot-to-your-server)
- [Deployment](#deployment)
  - [Option A – Run Locally](#option-a--run-locally)
  - [Option B – GitHub Actions](#option-b--github-actions)
  - [Option C – Always-On Hosting (Vercel / Railway / Render)](#option-c--always-on-hosting-vercel--railway--render)
- [How to Use the Bot](#how-to-use-the-bot)
  - [Basic Usage](#1-basic-usage)
  - [Choose a Specific Model](#2-choose-a-specific-model)
  - [Image / Vision Input](#3-image--vision-input)
  - [Direct Messages](#4-direct-messages-dm)
  - [Available Models](#available-models)
- [Configuration Reference](#configuration-reference)

---

## Prerequisites

| Requirement | Notes |
|---|---|
| Python 3.11+ | Only needed for local deployment |
| A Discord account | To create a bot application |
| A Pollinations account | To obtain an API key |

---

## Step 1 – Create a Discord Application & Bot

1. Go to the [Discord Developer Portal](https://discord.com/developers/applications) and click **New Application**.
2. Give your application a name (e.g. `My AI Bot`) and click **Create**.
3. In the left sidebar click **Bot**, then click **Add Bot** → **Yes, do it!**
4. Under the **TOKEN** section click **Reset Token**, then **Copy** the token and save it somewhere safe – this is your `DISCORD_TOKEN`.
5. Scroll down to **Privileged Gateway Intents** and enable **Message Content Intent** (the bot needs this to read messages). Click **Save Changes**.

---

## Step 2 – Get a Pollinations API Key

1. Go to <https://enter.pollinations.ai> and sign in.
2. Create or copy your API key – this is your `POLLINATIONS_TOKEN`.

---

## Step 3 – Invite the Bot to Your Server

1. In the [Discord Developer Portal](https://discord.com/developers/applications), open your application and click **OAuth2 → URL Generator** in the left sidebar.
2. Under **Scopes** check `bot` **and** `applications.commands` (required for the `/ask` slash command).
3. Under **Bot Permissions** check at minimum:
   - `Read Messages / View Channels`
   - `Send Messages`
   - `Read Message History`
4. Copy the generated URL, open it in your browser, and select the server you want to add the bot to.

---

## Deployment

### Option A – Run Locally

```bash
# 1. Clone the repository
git clone https://github.com/hugow0528/AI-discord-bot.git
cd AI-discord-bot

# 2. Install dependencies
pip install -r general-chat/requirements.txt

# 3. Set environment variables
export DISCORD_TOKEN="your_discord_bot_token_here"
export POLLINATIONS_TOKEN="your_pollinations_api_key_here"

# Windows (Command Prompt)
# set DISCORD_TOKEN=your_discord_bot_token_here
# set POLLINATIONS_TOKEN=your_pollinations_api_key_here

# 4. Start the bot
python general-chat/bot.py
```

You should see a log line like:
```
2025-01-01 00:00:00,000 [INFO] __main__: Logged in as MyAIBot#1234 (ID: 123456789012345678)
```

The bot is now online. Keep the terminal window running; closing it will stop the bot.

### Option B – GitHub Actions

GitHub Actions can host the bot with **zero infrastructure setup**. The included workflow (`.github/workflows/discord-bot.yml`) lets you start the bot manually via the **Actions** tab.

> **Note:** The automatic 6-hour cron restart has been disabled. GitHub Actions jobs have a maximum runtime of ~6 hours. For continuous uptime use Railway, Render, or a VPS (see below).

1. **Fork or push this repository** to your own GitHub account.

2. **Add Secrets** – In your repository go to **Settings → Secrets and variables → Actions → New repository secret** and add:

   | Name | Value |
   |---|---|
   | `DISCORD_TOKEN` | Your Discord bot token from Step 1 |
   | `POLLINATIONS_TOKEN` | Your Pollinations API key from Step 2 |

3. **Enable the workflow** – Go to the **Actions** tab in your repository. If prompted, click **I understand my workflows, go ahead and enable them**.

4. **Run the bot** – Click on **Discord AI Bot** in the workflows list, then click **Run workflow → Run workflow**. The bot will come online within a minute.

> **Tip:** You can monitor the bot's logs in real-time from the **Actions** tab by clicking the running workflow job.

---

### Option C – Always-On Hosting (Vercel / Railway / Render)

For a bot that **never goes offline**:

- **[RAILWAY.md](RAILWAY.md)** — **Railway** (recommended, easiest always-on option; full gateway bot, free starter credit)
- **[VERCEL.md](VERCEL.md)** — **Vercel** (HTTP Interactions / slash commands only), **Render** (full gateway bot, free tier available)

---

## How to Use the Bot

Once the bot is online and in your server, you can interact with it in several ways.

### 1. Basic Usage

Mention the bot in any channel it can read, followed by your question:

```
@MyAIBot What is the capital of France?
```

The bot automatically selects the best available model and replies directly to your message.

---

### 2. Get Help (`@about`)

Mention the bot with `@about` to receive a full usage guide and a list of all available `@model` prefixes:

```
@MyAIBot @about
```

The bot will reply with a formatted message describing all features, available models, and the `/ask` slash command.

---

### 3. Choose a Specific Model

Prefix your message with `@<model-name>` (right after mentioning the bot) to tell it which AI model to use. If that model fails, the bot automatically falls back through the rest of the chain.

```
@MyAIBot @deepseek Explain the theory of relativity.
@MyAIBot @gemini-search What's in the news today?
@MyAIBot @claude-fast Write a haiku about autumn.
```

You can also use `@ai` as an explicit alias for "use any available model" (the default behaviour):

```
@MyAIBot @ai What is 2 + 2?
```

---

### 4. Slash Commands

Type `/` in any channel to see the bot's available slash commands.  Discord shows them above the text input as you type.

| Command | Parameters | Description |
|---|---|---|
| `/ask` | `question` (required), `model` (optional) | Ask the AI a question; response streams to Discord in real-time. |
| `/interrupt` | `perspective` (required) | Inject your point of view mid-request and have the AI continue from your perspective instead of hard-cancelling. |
| `/cancel` | — | Hard-cancel your current in-progress AI request. |
| `/about` | — | Show the full usage guide and model list. |
| `/models` | — | List all available AI models with vision support info. |
| `/settings` | `model` (optional) | View or set your preferred AI model. |

When you use `/ask`, click the `model` field to instantly see the **full list of available models** as a dropdown — no typing required.  Select a model and press **Enter** to confirm, or leave it blank for automatic selection.

```
/ask question:What is quantum computing?
/ask question:What is in the news today? model:gemini-search
```

#### Streaming responses

Responses from `/ask` and `@mention` messages are **streamed to Discord in real-time**.  As soon as the AI starts generating, the bot sends a placeholder message (`▌`) and updates it progressively — you see the reply form word-by-word instead of waiting for the complete response.

#### Injecting your perspective (`/interrupt`)

While the AI is generating a response (or at any time), use `/interrupt` to inject your own point of view and redirect the conversation:

```
/interrupt perspective:Focus more on security implications
/interrupt perspective:Actually, I meant for a mobile app, not web
```

The bot cancels any running request, adds your perspective to the conversation context, and generates a new response that takes your input into account.

---

### 3. Image / Vision Input

Attach one or more images to your message and the bot will analyse them using a vision-capable model.  You can combine text and images:

```
@MyAIBot @openai-fast What breed is this dog?   ← with an image attached
@MyAIBot Describe this chart.                   ← with an image attached
```

If you attach an image **without** any text, the bot defaults to *"Describe this image."*

> **Vision-capable models:** `openai`, `openai-fast`, `gemini`, `gemini-fast`, `gemini-large`, `gemini-search`, `claude-fast`
>
> If you explicitly pick a non-vision model (e.g. `@deepseek`) and attach an image, the image is silently ignored and only the text is sent.

---

### 4. Direct Messages (DM)

Open a DM with the bot and send any message – no mention required.  The same `@<model-name>` prefix and image-attachment features work here too:

```
@deepseek Summarise this article for me.
```

---

### Available Models

| Model name | Supports images? | Notes |
|---|:---:|---|
| `openai-fast` | ✅ | Fast OpenAI model; default first choice |
| `openai` | ✅ | Full OpenAI model |
| `gemini-search` | ✅ | Gemini with Google Search grounding |
| `gemini` | ✅ | Standard Gemini model |
| `gemini-fast` | ✅ | Faster Gemini variant |
| `gemini-large` | ✅ | Larger Gemini variant |
| `claude-fast` | ✅ | Fast Claude model |
| `glm` | ❌ | GLM model |
| `qwen-character` | ❌ | Qwen character model |
| `deepseek` | ❌ | DeepSeek model |
| `qwen-safety` | ❌ | Qwen safety model |

The default fallback order (when no model is specified) is:
`openai-fast → gemini-search → openai-fast → openai → glm → claude-fast → qwen-character → deepseek → qwen-safety`

---

### Example Interactions

| You type | What happens |
|---|---|
| `@MyAIBot Explain quantum computing` | Uses the default model chain |
| `@MyAIBot @ai Explain quantum computing` | Same as above (`@ai` = default chain) |
| `@MyAIBot @about` | Returns the full usage guide and model list |
| `@MyAIBot @gemini-search What's in the news?` | Uses `gemini-search` first, then falls back if needed |
| `@MyAIBot @openai-fast` + image attached | Analyses the image with `openai-fast` |
| `@MyAIBot` + image (no text) | Sends *"Describe this image."* to the model |
| *(In DM)* `@deepseek Write a poem` | Uses `deepseek` first in DM |
| `/ask question:Hello model:deepseek` | Slash command; model picked from dropdown |
| `/about` | Shows the full usage guide via slash command |
| `/models` | Lists all AI models via slash command |

---

### Other Notes

- The bot **ignores its own messages** to prevent feedback loops.
- Responses are **streamed in real-time** — the bot edits a placeholder message progressively as tokens arrive.
- If a response exceeds Discord's 2,000-character limit, the bot automatically splits it into multiple messages.
- If all models fail, the bot replies: *"Sorry, all AI models are currently unavailable. Please try again later."*

---

## Configuration Reference

All configuration is done through environment variables:

| Variable | Required | Description |
|---|---|---|
| `DISCORD_TOKEN` | ✅ | Discord bot token obtained from the Developer Portal |
| `POLLINATIONS_TOKEN` | ✅ | Pollinations AI API key from <https://enter.pollinations.ai> |

The AI API endpoint (`https://gen.pollinations.ai/v1/chat/completions`) and the model chain are defined at the top of `general-chat/bot.py` and can be customised there if needed.

---

## Part 2 — AI Company Bot (`ai-company/`)

For full setup and usage instructions, see **[`ai-company/SETUP.md`](ai-company/SETUP.md)**.

### Quick Overview

Give the bot a task and it will simulate a company brainstorming session across multiple roles, then produce a structured **Final Outcome**.

**GitHub Actions secrets required:** `DISCORD_TOKEN_COMPANY`, `POLLINATIONS_TOKEN`

### Slash Commands

| Command | Parameters | Description |
|---|---|---|
| `/company` | `task` (required), `roles` (optional), `interactive` (optional) | Run a multi-role AI company discussion |
| `/build` | `task` (required), `project_name` (optional), `roles` (optional), `interactive` (optional) | Developer team discussion + code generation saved to `project/` |
| `/followup` | `request` (required) | Ask questions or request amendments after a `/build` session |
| `/company_roles` | — | List all available and custom roles |
| `/about` | — | Show the help guide |

### Interactive Mode — Being an Interruptor

Pass `interactive:True` to `/company` or `/build` to become a participant in the discussion.  After each role responds, the bot shows two buttons:

- **▶ Continue** — let the discussion proceed.
- **✏️ Add My Input** — open a text modal to type your perspective (up to 1 000 characters).  Your input becomes **Stakeholder Input** that all subsequent roles and the Facilitator can see and react to, steering the discussion from your point of view.

### Example

```
/company task:Build a food delivery mobile app
```

The bot will produce something like:

```
🏢 AI Company Discussion
📋 Task: Build a food delivery mobile app
👥 Participants: CEO, CTO, Product Manager, Designer, Engineer, Marketing Manager

👤 CEO
We should focus on the top-3 metro areas first to validate PMF before scaling nationally...

👤 CTO
A React Native app backed by a Node.js microservice architecture would let us ship cross-platform quickly...

... (each role contributes) ...

---
✅ Final Outcome

Key decisions:
1. Target three cities for the MVP launch
2. Use React Native + Node.js microservices

Next steps:
1. Define MVP feature set with the Product Manager
2. Hire a mobile engineer and UX researcher
...
```

### Custom Roles

You can supply any role name — even ones not built into the bot:

```
/company task:Design a new city transport system roles:Urban Planner,Civil Engineer,Mayor,Environmentalist
```

### Run the AI Company Bot Locally

```bash
pip install -r ai-company/requirements.txt
export DISCORD_TOKEN_COMPANY="your_company_bot_token"
export POLLINATIONS_TOKEN="your_pollinations_api_key"
python ai-company/bot.py
```