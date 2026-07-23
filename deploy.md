# 🚀 CheckMate — On-Demand Public Deployment Guide

This guide explains how to instantly launch **CheckMate** and publish a **secure public HTTPS URL** whenever you need to share access, evaluate RFPs remotely, or present live demos.

---

## ⚡ Option 1: Quick 1-Click Script (Recommended)

Whenever you want to start CheckMate with an instant public HTTPS URL:

Open your terminal in the project folder and run:

```bash
./start_public_tunnel.sh
```

### What this script does automatically:
1. Checks and starts the CheckMate Python server on `http://127.0.0.1:8765`.
2. Connects to Cloudflare's global edge network.
3. Displays your active public HTTPS URL (e.g., `https://<name>.trycloudflare.com`).

---

## 💻 Option 2: Manual Terminal Commands

If you prefer running commands manually in two terminal tabs:

### Step 1: Start CheckMate Local Engine
```bash
.venv/bin/python main.py
```

### Step 2: Open Public HTTPS Tunnel
```bash
cloudflared tunnel --url http://127.0.0.1:8765
```

---

## 🔒 Security & Privacy Features

- **HTTPS Encryption**: All public traffic through `trycloudflare.com` is encrypted via TLS 1.3.
- **Zero Exposed API Keys**: API keys reside encrypted in your local database (`.bod_data/bod_web.db`) and are **never** sent to Cloudflare or public clients.
- **Full On-Demand Control**: Press `Ctrl + C` in your terminal at any time to immediately revoke public access.

---

## ☁️ Option 3: Permanent 24/7 Cloud Hosting ($0 Free, Zero Credit Card)

If you need CheckMate running 24/7 without keeping your Mac turned on:

1. **Koyeb (`koyeb.com`)**:
   - Create a free account at [koyeb.com](https://www.koyeb.com) (No credit card needed).
   - Import GitHub repository `xee999/CheckMate`.
   - Select **Docker** environment and port `8765`.
   - Click **Deploy** to get a permanent 24/7 URL (`https://checkmate-app.koyeb.app`).
