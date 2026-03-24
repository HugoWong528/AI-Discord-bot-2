# AI Company Bot — Setup & Usage Guide

An AI-powered Discord bot that simulates a company brainstorming session **and** a developer team that generates real code files committed directly to this repository.

Give it a task, pick a set of roles (or use the defaults), and it will have each role discuss the task before a **Facilitator** synthesises everything into a clear, actionable **Final Outcome**.

Use the `/build` command to have the developer team generate complete code files that are automatically saved to the `project/` folder in this repository.

---

## Table of Contents

- [Prerequisites](#prerequisites)
- [Step 1 – Create a Discord Bot](#step-1--create-a-discord-bot)
- [Step 2 – Get a Pollinations API Key](#step-2--get-a-pollinations-api-key)
- [Step 3 – Invite the Bot to Your Server](#step-3--invite-the-bot-to-your-server)
- [Deployment](#deployment)
  - [Option A – Run Locally](#option-a--run-locally)
  - [Option B – GitHub Actions (Recommended)](#option-b--github-actions-recommended)
- [How to Use the Bot](#how-to-use-the-bot)
  - [/company](#company)
  - [/build](#build)
  - [/followup](#followup)
  - [/company\_roles](#company_roles)
  - [/about](#about)
- [Available Roles](#available-roles)
- [Configuration Reference](#configuration-reference)


---

## Prerequisites

| Requirement | Notes |
|---|---|
| Python 3.11+ | Only needed for local deployment |
| A Discord account | To create a bot application |
| A Pollinations account | To obtain an API key |

---

## Step 1 – Create a Discord Bot

1. Go to the [Discord Developer Portal](https://discord.com/developers/applications) and click **New Application**.
2. Give your application a name (e.g. `AI Company Bot`) and click **Create**.
3. In the left sidebar click **Bot**, then click **Add Bot** → **Yes, do it!**
4. Under the **TOKEN** section click **Reset Token**, then **Copy** the token — this is your `DISCORD_TOKEN_COMPANY`.

> **Tip:** If you already have a bot for the General Chat part, you can create a **separate** Discord application here so the two bots have distinct identities and can run simultaneously in the same server.

---

## Step 2 – Get a Pollinations API Key

1. Go to <https://enter.pollinations.ai> and sign in.
2. Create or copy your API key — this is your `POLLINATIONS_TOKEN`.

---

## Step 3 – Invite the Bot to Your Server

1. In the [Discord Developer Portal](https://discord.com/developers/applications), open your application and click **OAuth2 → URL Generator**.
2. Under **Scopes** check `bot` **and** `applications.commands`.
3. Under **Bot Permissions** check at minimum:
   - `Read Messages / View Channels`
   - `Send Messages`
   - `Read Message History`
4. Copy the generated URL, open it in your browser, and select the server.

---

## Deployment

### Option A – Run Locally

```bash
# 1. Clone the repository
git clone https://github.com/hugow0528/AI-discord-bot.git
cd AI-discord-bot

# 2. Install dependencies
pip install -r ai-company/requirements.txt

# 3. Set environment variables
export DISCORD_TOKEN_COMPANY="your_discord_bot_token_here"
export POLLINATIONS_TOKEN="your_pollinations_api_key_here"

# Optional: to enable /build saving files to GitHub
export GITHUB_TOKEN="your_github_personal_access_token"
export GITHUB_REPOSITORY="hugow0528/AI-discord-bot"

# Windows (Command Prompt)
# set DISCORD_TOKEN_COMPANY=your_discord_bot_token_here
# set POLLINATIONS_TOKEN=your_pollinations_api_key_here

# 4. Start the bot
python ai-company/bot.py
```

You should see a log line like:

```
2025-01-01 00:00:00,000 [INFO] __main__: AI Company Bot logged in as AICompanyBot#5678 (ID: 123456789012345678)
```

> **Note:** When running locally, `GITHUB_TOKEN` must be a Personal Access Token (PAT) with `repo` write scope.  
> When running in GitHub Actions, the token is provided automatically (see below).

### Option B – GitHub Actions (Recommended)

The included workflow (`.github/workflows/discord-ai-company-bot.yml`) runs the AI Company bot automatically.

1. **Fork or push this repository** to your own GitHub account.

2. **Add Secrets** — go to **Settings → Secrets and variables → Actions → New repository secret** and add:

   | Name | Value |
   |---|---|
   | `DISCORD_TOKEN_COMPANY` | Your AI Company bot token from Step 1 |
   | `POLLINATIONS_TOKEN` | Your Pollinations API key from Step 2 |

   > `GITHUB_TOKEN` is **not** a secret you need to add — GitHub Actions provides it automatically. The workflow already passes it to the bot with `contents: write` permission so `/build` can commit files to the `project/` folder.

3. **Enable the workflow** — go to the **Actions** tab, click **I understand my workflows, go ahead and enable them** if prompted.

4. **Run the bot** — click **Discord AI Company Bot** in the workflows list, then click **Run workflow → Run workflow**.

The automatic 6-hour cron restart has been disabled. To restart the bot after it stops, trigger the workflow manually again from the **Actions** tab. For continuous uptime without manual restarts, see **[VERCEL.md](../../VERCEL.md)**.

---

## How to Use the Bot

Once the bot is online and in your server, use the following slash commands.

> **Auto-threads (討論串):** Every `/company` and `/build` command automatically creates a dedicated Discord thread named after the task. All role responses, the final outcome, and subsequent `/followup` replies are posted inside that thread, keeping your main channel tidy. The bot requires the **Create Public Threads** permission for this feature; if it is missing, messages fall back to the main channel.

### `/company`

Run a full AI company discussion on any task.

```
/company task:Build a food delivery mobile app
/company task:Launch a new SaaS product roles:CEO,CTO,Marketing Manager,Designer
/company task:Improve database query performance roles:CTO,Engineer,Data Scientist
/company task:Design a loyalty programme interactive:True
```

**Parameters:**

| Parameter | Required | Description |
|---|---|---|
| `task` | ✅ | The task or project for the company to discuss |
| `roles` | ❌ | Comma-separated role names. Defaults to the 6 standard roles when omitted. |
| `interactive` | ❌ | Set to `True` to pause after each role so **you** can add your perspective before the next role responds. Default: `False`. |

**What happens:**

1. Each role receives the task and a full summary of what previous roles said.
   > **Cross-role communication is confirmed** — next to every role name you will see a `(read N prior response(s))` indicator proving that each AI persona reads all earlier contributions before writing its own.
2. Every role contributes a short (2–4 sentence) perspective, explicitly acknowledging specific points raised by other roles.
3. A **Facilitator** synthesises all contributions (plus any stakeholder input you injected) into a structured **Final Outcome** containing key decisions, prioritised next steps, and risks.

> **Note:** Up to 6 roles are supported per session to keep responses focused and fast.

#### Interactive mode — being an interruptor

When you pass `interactive:True`, the bot pauses **after every role** responds and shows two buttons:

- **▶ Continue** — let the discussion proceed as normal.
- **✏️ Add My Input** — open a text modal to type your own perspective (up to 1 000 characters). Your input is immediately available to all subsequent roles and the Facilitator as **Stakeholder Input**, steering the direction of the discussion.

The buttons time out after 90 seconds and default to **Continue**.

---

### `/build`

Run a developer team discussion, generate complete code files, and automatically commit them to the `project/<project-name>/` folder in this repository.

```
/build task:Create a REST API for a todo app in Python
/build task:Build a React dashboard for analytics project_name:analytics-dashboard
/build task:Create a CLI tool to batch rename files roles:CTO,Backend Developer,QA Engineer
/build task:Build a chat app interactive:True
```

**Parameters:**

| Parameter | Required | Description |
|---|---|---|
| `task` | ✅ | Describe what to build |
| `project_name` | ❌ | Short folder name (e.g. `todo-api`). Defaults to a slug derived from the task. |
| `roles` | ❌ | Comma-separated developer roles. Defaults to the developer team (CTO, Backend Developer, Frontend Developer, QA Engineer, DevOps Engineer). |
| `interactive` | ❌ | Set to `True` to pause after each role so you can add your perspective (same mechanism as `/company`). Default: `False`. |

**What happens:**

1. The developer team discusses the task, each role building on the previous contributions.
2. A **Facilitator** produces a structured **Final Plan**.
3. A **Code Generator** produces complete, functional code files based on the plan.
4. All files (including a `README.md` with the outcome) are committed to `project/<project-name>/` in this repository.
5. The bot posts links to the committed files in Discord.
6. The session is saved per channel so you can use `/followup` to continue the conversation.

**Example output saved to GitHub:**

```
project/
  todo-api/
    README.md          ← task description + final plan + file list
    main.py            ← generated source code
    requirements.txt   ← dependencies
    Dockerfile         ← container setup
    tests/
      test_main.py     ← generated tests
```

> **Note:** GitHub saving requires `GITHUB_TOKEN` to be available (automatic in GitHub Actions; must be set manually when running locally).

---

### `/followup`

Ask a follow-up question or request amendments **after** a `/build` session — without starting over.

```
/followup request:Add user authentication with JWT
/followup request:How does the database schema work?
/followup request:Refactor the API to use async/await throughout
```

**Parameters:**

| Parameter | Required | Description |
|---|---|---|
| `request` | ✅ | Your question or amendment request |

**What happens:**

1. The bot retrieves the last `/build` context for the current channel (task, team discussion, final plan, and generated files).
2. Your request is answered with full awareness of the existing codebase.
3. If the response contains new or modified code files (using the `### File:` format), they are automatically merged into the stored session and, if GitHub is configured, committed to the project folder.

> Only the most recent `/build` session per channel is stored. Run `/build` again to start a fresh session.

---



List all built-in roles and their focus areas, plus instructions for using custom roles.

```
/company_roles
```

---

### `/about`

Show a concise help guide for the bot.

```
/about
```

---

## Available Roles

### Default Roles (for `/company`)

| Role | Focus |
|---|---|
| CEO | Business strategy, ROI, market opportunity, high-level vision |
| CTO | Technical architecture, feasibility, scalability, security |
| Product Manager | User needs, requirements, prioritisation, roadmap |
| Designer | UX/UI design, accessibility, visual identity, usability |
| Engineer | Implementation, timelines, testing, code quality |
| Marketing Manager | Target audience, positioning, growth, messaging |

### Default Developer Team (for `/build`)

| Role | Focus |
|---|---|
| CTO | Technical architecture & technology stack decisions |
| Backend Developer | Server-side logic, APIs, database schemas, authentication |
| Frontend Developer | UI components, React/Vue/HTML/CSS, responsiveness |
| QA Engineer | Testing strategy, unit & integration tests, quality gates |
| DevOps Engineer | CI/CD, Docker, deployment, monitoring, infrastructure |

### All Built-in Roles

| Role | Focus |
|---|---|
| CEO | Business strategy & vision |
| CTO | Technical architecture & feasibility |
| Product Manager | User stories & product roadmap |
| Designer | UX/UI & user experience |
| Engineer | Implementation & code quality |
| Marketing Manager | Brand positioning & growth |
| Data Scientist | ML, analytics & data-driven decisions |
| Legal Counsel | Legal risk, compliance & privacy |
| Finance Manager | Budget, cost & ROI analysis |
| HR Manager | Team structure, culture & talent |
| Frontend Developer | React/Vue/HTML/CSS/JS UI implementation |
| Backend Developer | Server-side APIs, databases, authentication |
| Full Stack Developer | End-to-end implementation |
| QA Engineer | Testing strategies & quality assurance |
| DevOps Engineer | CI/CD, Docker, deployment & monitoring |

### Custom Roles

You can supply **any** role name — even ones not in the list above. The bot generates a sensible system prompt automatically:

```
/company task:Design a new city transport system roles:Urban Planner,Civil Engineer,Mayor,Environmentalist
/build task:Build a data pipeline roles:Data Engineer,Backend Developer,DevOps Engineer
```

---

## Configuration Reference

All configuration is done through environment variables:

| Variable | Required | Description |
|---|---|---|
| `DISCORD_TOKEN_COMPANY` | ✅ | Discord bot token for the AI Company bot |
| `POLLINATIONS_TOKEN` | ✅ | Pollinations AI API key from <https://enter.pollinations.ai> |
| `GITHUB_TOKEN` | Required for `/build` | GitHub token with repo write access. Provided automatically in GitHub Actions (`secrets.GITHUB_TOKEN`); for local runs use a Personal Access Token with `repo` write scope. |
| `GITHUB_REPOSITORY` | Required for `/build` | Repository in `owner/repo` format. Set automatically in GitHub Actions. |

The AI API endpoint (`https://gen.pollinations.ai/v1/chat/completions`) and the model chain can be customised at the top of `ai-company/bot.py`.

