# Platform Deployment Guide

This guide explains how to deploy either Discord bot on every supported platform.  
Pick the section that matches your environment.

---

## Table of Contents

- [Prerequisites](#prerequisites)
- [Linux](#linux)
- [macOS](#macos)
- [Windows](#windows)
- [Docker](#docker)
- [GitHub Actions (Recommended)](#github-actions-recommended)
- [Environment Variables Reference](#environment-variables-reference)
- [Troubleshooting](#troubleshooting)

---

## Prerequisites

| Requirement | Notes |
|---|---|
| Python 3.11+ | Not needed for Docker or GitHub Actions deployments |
| Discord bot token | Obtained from the [Discord Developer Portal](https://discord.com/developers/applications) |
| Pollinations API key | Obtained from <https://enter.pollinations.ai> |

---

## Linux

Tested on Ubuntu 22.04 / Debian 12 and compatible distributions.

### 1. Install Python 3.11

```bash
sudo apt update
sudo apt install -y python3.11 python3.11-venv python3-pip
```

### 2. Clone and set up the project

```bash
git clone https://github.com/hugow0528/AI-discord-bot.git
cd AI-discord-bot
```

### 3. Create a virtual environment and install dependencies

**General Chat bot:**

```bash
python3.11 -m venv .venv
source .venv/bin/activate
pip install -r general-chat/requirements.txt
```

**AI Company bot:**

```bash
python3.11 -m venv .venv
source .venv/bin/activate
pip install -r ai-company/requirements.txt
```

### 4. Set environment variables

```bash
export DISCORD_TOKEN="your_discord_bot_token"
export POLLINATIONS_TOKEN="your_pollinations_api_key"
# AI Company bot uses a different token variable:
# export DISCORD_TOKEN_COMPANY="your_company_bot_token"
```

### 5. Run the bot

```bash
# General Chat bot
python general-chat/bot.py

# AI Company bot
python ai-company/bot.py
```

### 6. (Optional) Run as a systemd service

Create `/etc/systemd/system/ai-discord-bot.service`:

```ini
[Unit]
Description=AI Discord Bot
After=network.target

[Service]
Type=simple
User=YOUR_USER
WorkingDirectory=/path/to/AI-discord-bot
EnvironmentFile=/path/to/AI-discord-bot/.env
ExecStart=/path/to/AI-discord-bot/.venv/bin/python general-chat/bot.py
Restart=on-failure
RestartSec=10

[Install]
WantedBy=multi-user.target
```

Create `.env` (never commit this file):

```
DISCORD_TOKEN=your_token_here
POLLINATIONS_TOKEN=your_key_here
```

Enable and start:

```bash
sudo systemctl daemon-reload
sudo systemctl enable ai-discord-bot
sudo systemctl start ai-discord-bot
sudo systemctl status ai-discord-bot   # verify it is running
```

---

## macOS

Tested on macOS 13 (Ventura) and later.

### 1. Install Python 3.11 via Homebrew

```bash
brew install python@3.11
```

### 2. Clone and set up the project

```bash
git clone https://github.com/hugow0528/AI-discord-bot.git
cd AI-discord-bot
```

### 3. Create a virtual environment and install dependencies

**General Chat bot:**

```bash
python3.11 -m venv .venv
source .venv/bin/activate
pip install -r general-chat/requirements.txt
```

**AI Company bot:**

```bash
python3.11 -m venv .venv
source .venv/bin/activate
pip install -r ai-company/requirements.txt
```

### 4. Set environment variables and run

```bash
export DISCORD_TOKEN="your_discord_bot_token"
export POLLINATIONS_TOKEN="your_pollinations_api_key"

python general-chat/bot.py   # or ai-company/bot.py
```

### 5. (Optional) Run as a launchd service

Create `~/Library/LaunchAgents/com.ai-discord-bot.plist`:

```xml
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN"
  "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
  <key>Label</key>
  <string>com.ai-discord-bot</string>
  <key>ProgramArguments</key>
  <array>
    <string>/path/to/AI-discord-bot/.venv/bin/python</string>
    <string>/path/to/AI-discord-bot/general-chat/bot.py</string>
  </array>
  <key>EnvironmentVariables</key>
  <dict>
    <key>DISCORD_TOKEN</key>
    <string>your_token_here</string>
    <key>POLLINATIONS_TOKEN</key>
    <string>your_key_here</string>
  </dict>
  <key>RunAtLoad</key>
  <true/>
  <key>KeepAlive</key>
  <true/>
  <key>StandardOutPath</key>
  <string>/tmp/ai-discord-bot.log</string>
  <key>StandardErrorPath</key>
  <string>/tmp/ai-discord-bot.err</string>
</dict>
</plist>
```

Load it:

```bash
launchctl load ~/Library/LaunchAgents/com.ai-discord-bot.plist
```

---

## Windows

Tested on Windows 10 and Windows 11.

### 1. Install Python 3.11

Download the installer from <https://www.python.org/downloads/> and run it.  
**Important:** Check **"Add Python to PATH"** during installation.

### 2. Clone and set up the project

```cmd
git clone https://github.com/hugow0528/AI-discord-bot.git
cd AI-discord-bot
```

If you do not have Git installed, download it from <https://git-scm.com/download/win>.

### 3. Create a virtual environment and install dependencies

Open **Command Prompt** or **PowerShell**:

```cmd
python -m venv .venv
.venv\Scripts\activate
```

**General Chat bot:**

```cmd
pip install -r general-chat\requirements.txt
```

**AI Company bot:**

```cmd
pip install -r ai-company\requirements.txt
```

### 4. Set environment variables and run

**Command Prompt:**

```cmd
set DISCORD_TOKEN=your_discord_bot_token
set POLLINATIONS_TOKEN=your_pollinations_api_key
python general-chat\bot.py
```

**PowerShell:**

```powershell
$env:DISCORD_TOKEN = "your_discord_bot_token"
$env:POLLINATIONS_TOKEN = "your_pollinations_api_key"
python general-chat\bot.py
```

### 5. (Optional) Run on startup using Task Scheduler

The easiest approach is to create a small batch file that sets environment variables and launches the bot, then schedule that batch file.

1. Create `run-bot.bat` (e.g. in `C:\bots\AI-discord-bot\`):

   ```bat
   @echo off
   set DISCORD_TOKEN=your_discord_bot_token
   set POLLINATIONS_TOKEN=your_pollinations_api_key
   C:\bots\AI-discord-bot\.venv\Scripts\python.exe C:\bots\AI-discord-bot\general-chat\bot.py
   ```

2. Open **Task Scheduler** → **Create Basic Task**.
3. Set **Trigger** to *When the computer starts* (or *At log on*).
4. Set **Action** to *Start a program* and enter the full path to `run-bot.bat`.
5. Click **Finish**. Right-click the new task → **Properties** → **General** → enable **Run whether user is logged on or not** if you want it to run in the background.

---

## Docker

Both bots share the same Dockerfile structure. Create a `Dockerfile` inside each bot's subfolder.

### General Chat bot

Create `general-chat/Dockerfile`:

```dockerfile
FROM python:3.11-slim

WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY bot.py .

CMD ["python", "bot.py"]
```

Build and run (from the repository root):

```bash
docker build -t ai-discord-bot ./general-chat
docker run -d \
  -e DISCORD_TOKEN="your_token" \
  -e POLLINATIONS_TOKEN="your_key" \
  --name ai-discord-bot \
  ai-discord-bot
```

### AI Company bot

Create `ai-company/Dockerfile`:

```dockerfile
FROM python:3.11-slim

WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY bot.py .

CMD ["python", "bot.py"]
```

```bash
docker build -t ai-company-bot ./ai-company
docker run -d \
  -e DISCORD_TOKEN_COMPANY="your_token" \
  -e POLLINATIONS_TOKEN="your_key" \
  --name ai-company-bot \
  ai-company-bot
```

### Docker Compose (both bots)

Using the Dockerfiles created above, add a `docker-compose.yml` to the repository root:

```yaml
services:
  general-chat:
    build:
      context: ./general-chat
    environment:
      DISCORD_TOKEN: "${DISCORD_TOKEN}"
      POLLINATIONS_TOKEN: "${POLLINATIONS_TOKEN}"
    restart: unless-stopped

  ai-company:
    build:
      context: ./ai-company
    environment:
      DISCORD_TOKEN_COMPANY: "${DISCORD_TOKEN_COMPANY}"
      POLLINATIONS_TOKEN: "${POLLINATIONS_TOKEN}"
    restart: unless-stopped
```

Create a `.env` file (never commit it):

```
DISCORD_TOKEN=your_general_chat_token
DISCORD_TOKEN_COMPANY=your_company_token
POLLINATIONS_TOKEN=your_pollinations_key
```

Start both bots:

```bash
docker compose up -d
```

---

## GitHub Actions

GitHub Actions is the easiest way to keep both bots running with **zero infrastructure cost**.  
Each bot has its own workflow file in `.github/workflows/`.

### How it works

- Each workflow starts the corresponding bot and keeps it running for up to 6 hours (GitHub's job time limit).
- The `workflow_dispatch` trigger lets you start or restart the bot manually from the **Actions** tab at any time.
- The automatic `cron` schedule has been **disabled** (commented out in the workflow files). For continuous 24/7 uptime, use Railway, Render, or a VPS (see **[VERCEL.md](VERCEL.md)**).
- Logs are visible in real time from the **Actions** tab.

### Setup

1. **Fork or push** this repository to your own GitHub account.

2. **Add Secrets** — go to **Settings → Secrets and variables → Actions → New repository secret** and add:

   | Secret name | Bot | Description |
   |---|---|---|
   | `DISCORD_TOKEN` | General Chat | Token for the general chat bot |
   | `DISCORD_TOKEN_COMPANY` | AI Company | Token for the AI company bot |
   | `POLLINATIONS_TOKEN` | Both | Your Pollinations AI API key |

   > `GITHUB_TOKEN` is provided automatically by GitHub Actions — you do not need to add it.

3. **Enable workflows** — go to the **Actions** tab and click **I understand my workflows, go ahead and enable them** if prompted.

4. **Run a workflow** — click the desired workflow in the left sidebar, then click **Run workflow → Run workflow**.

### Workflow files

| File | Bot |
|---|---|
| `.github/workflows/discord-bot.yml` | General Chat bot |
| `.github/workflows/discord-ai-company-bot.yml` | AI Company bot |

Both workflows are independent and can be started or stopped separately.

---

## Always-On Hosting (Vercel / Railway / Render)

For a bot that never goes offline, see **[VERCEL.md](VERCEL.md)** — it covers Vercel (HTTP Interactions), Railway, and Render.

---

## Environment Variables Reference

### General Chat bot (`general-chat/bot.py`)

| Variable | Required | Description |
|---|---|---|
| `DISCORD_TOKEN` | ✅ | Discord bot token |
| `POLLINATIONS_TOKEN` | ✅ | Pollinations AI API key |

### AI Company bot (`ai-company/bot.py`)

| Variable | Required | Description |
|---|---|---|
| `DISCORD_TOKEN_COMPANY` | ✅ | Discord bot token |
| `POLLINATIONS_TOKEN` | ✅ | Pollinations AI API key |
| `GITHUB_TOKEN` | Required for `/build` | GitHub token with repo write access. Provided automatically in GitHub Actions. |
| `GITHUB_REPOSITORY` | Required for `/build` | Repository in `owner/repo` format. Set automatically in GitHub Actions. |

---

## Troubleshooting

### `DISCORD_TOKEN` / `DISCORD_TOKEN_COMPANY` not set

```
KeyError: 'DISCORD_TOKEN'
```

Make sure the environment variable is exported before running the bot.  
On Linux/macOS: `export DISCORD_TOKEN="..."` — on Windows: `set DISCORD_TOKEN=...`

### Message Content Intent warning

```
discord.ext.commands.bot: Privileged message content intent is missing, commands may not work as expected.
```

This warning only affects the **General Chat** bot, which reads message content to respond to mentions.  
Fix: in the [Discord Developer Portal](https://discord.com/developers/applications) open your bot → **Bot** → scroll to **Privileged Gateway Intents** → enable **Message Content Intent** → **Save Changes**.

> The **AI Company** bot uses slash commands only and does **not** require the Message Content Intent.

### PyNaCl / voice warning

```
discord.client: PyNaCl is not installed, voice will NOT be supported
```

This warning is suppressed once you install dependencies with `pip install -r requirements.txt` (PyNaCl is included).  
Neither bot uses voice, so this has no functional impact.

### Slash commands not appearing in Discord

Slash commands are registered globally when the bot first comes online.  
It can take up to **1 hour** for them to propagate to all servers. If they never appear:

1. Ensure `applications.commands` scope was checked when generating the invite URL.
2. Restart the bot to force a fresh `tree.sync()` call.

### Bot goes offline after ~6 hours on GitHub Actions

This is expected — GitHub Actions jobs have a maximum runtime.  
The automatic cron restart has been **disabled** in the workflow files.  
To restart the bot, go to the **Actions** tab → click the workflow → **Run workflow**.  
For continuous uptime, use Railway, Render, or a dedicated Linux server (see **[VERCEL.md](VERCEL.md)**).
