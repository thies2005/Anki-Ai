# Medical PDF to Anki Converter

A powerful AI-powered tool that converts medical PDFs into high-yield Anki flashcards using Google Gemini, Z.AI, or OpenRouter models.

![Streamlit](https://img.shields.io/badge/Streamlit-1.41+-red)
![Python](https://img.shields.io/badge/Python-3.11+-blue)
![Docker](https://img.shields.io/badge/Docker-Ready-blue)
![License](https://img.shields.io/badge/License-MIT-green)

---

## Table of Contents

- [Features](#-features)
- [Quick Start](#-quick-start)
- [Configuration](#-configuration)
- [Authentication & Security](#-authentication--security)
- [Docker Deployment](#-docker-deployment)
- [Cloudflare Tunnel Setup](#-cloudflare-tunnel-setup)
- [Usage Guide](#-usage-guide)
- [Settings Reference](#-settings-reference)
- [Troubleshooting](#-troubleshooting)

---

## ✨ Features

### 🧠 AI Providers
- **Google Gemini**: Support for Gemini 2.5, 3.0 Flash, and Gemma 3 27B
- **Z.AI**: Access to GLM-4.7 and GLM-4.5 Air models
- **OpenRouter**: Access to Xiaomi Mimo, DeepSeek, Qwen, and 100+ free models
- **Automatic Fallback**: Rate limit (429) errors automatically switch to backup models

### 🔐 Authentication & Security
- **User Registration**: Email/password signup with bcrypt encryption
- **Password Reset**: Email-based password recovery with time-limited verification codes
- **Secure Password Storage**: Bcrypt hashing with automatic migration from legacy SHA-256
- **Rate Limiting**: 5 attempts per 5 minutes for login, registration, and password reset
- **Password Strength**: Enforced complexity (8+ chars, uppercase, lowercase, digit)
- **Guest Mode**: Try the app without creating an account (keys not saved)
- **Session Management**: Persistent user sessions with encrypted API key storage

### ⚡ Workflow Efficiency
- **Fast Track Mode**: Skip summaries and generate cards immediately from PDFs
- **Split-View**: Generate cards on the left, chat with PDFs on the right
- **Direct Browser Push**: Send cards directly to Anki Desktop (requires AnkiConnect)

### 🃏 Card Generation
- **Tab-Separated Output**: Native Anki import format with deck/tag columns
- **Formatting Modes**: Basic + HTML, Markdown, or Legacy LaTeX
- **Subdeck Organization**: Automatic `Medical::FileName::Chapter` hierarchy
- **AI Chapter Detection**: Automatically split PDFs into chapters

---

## 🚀 Quick Start

### Option 1: Docker (Recommended)

```bash
# Clone repository
git clone https://github.com/yourusername/anki-ai.git
cd anki-ai

# Start with Docker Compose
docker-compose up --build

# Access at http://localhost:8501
```

### Option 2: Manual Setup

```bash
# Clone and enter directory
git clone https://github.com/yourusername/anki-ai.git
cd anki-ai

# Create virtual environment
python -m venv venv
source venv/bin/activate  # Windows: venv\Scripts\activate

# Install dependencies
pip install -r requirements.txt

# Run
streamlit run app.py
```

---

## ⚙️ Configuration

### API Keys

Configure keys in the UI (saved to your profile) or via environment variables.

| Provider | Get Key From | Env Variable |
|----------|--------------|--------------|
| Google Gemini | [Google AI Studio](https://aistudio.google.com/app/apikey) | `GOOGLE_API_KEY` |
| Z.AI | [Z.AI](https://z.ai/) | `ZAI_API_KEY` |
| OpenRouter | [OpenRouter](https://openrouter.ai/keys) | `OPENROUTER_API_KEY` |

### Environment Variables (.env)

```env
# API Keys
GOOGLE_API_KEY=your_gemini_key
ZAI_API_KEY=your_zai_key
OPENROUTER_API_KEY=your_openrouter_key
FALLBACK_KEY_1=optional_backup_key

# SMTP (for password reset and welcome emails)
SMTP_SERVER=smtp.gmail.com
SMTP_PORT=587
SMTP_USE_TLS=True
SMTP_USERNAME=your_email@gmail.com
SMTP_PASSWORD=your_app_password

# AnkiConnect
ANKI_CONNECT_URL=http://localhost:8765
```

### SMTP Setup (Password Reset & Welcome Emails)

For Gmail:
1. Go to [Google Account Security](https://myaccount.google.com/security)
2. Enable 2-Factor Authentication
3. Generate an [App Password](https://myaccount.google.com/apppasswords)
4. Use the App Password in `SMTP_PASSWORD`

For other providers, use their SMTP settings accordingly.

---

## 🔐 Authentication & Security

### Password Requirements

All passwords must meet the following criteria:
- Minimum 8 characters
- At least one uppercase letter
- At least one lowercase letter
- At least one digit

### Rate Limiting

| Operation | Limit | Window |
|-----------|-------|--------|
| Login | 5 attempts | 5 minutes |
| Registration | 5 attempts | 5 minutes |
| Password Reset Request | 5 attempts | 5 minutes |
| Password Reset Verification | 5 attempts | 5 minutes |

### Security Features

- **Bcrypt Hashing**: Passwords are hashed using bcrypt with automatic salt generation
- **Timing-Safe Comparison**: Reset codes use `hmac.compare_digest()` to prevent timing attacks
- **Hashed Reset Codes**: Verification codes are SHA-256 hashed before storage
- **Cryptographically Secure Codes**: Reset codes generated using `secrets.token_hex()`
- **Legacy Migration**: Automatic migration from SHA-256 to bcrypt on first login

---

## 🐳 Docker Deployment

### Basic Usage

```bash
docker-compose up -d
```

### Container Services

| Service | Description | Port |
|---------|-------------|------|
| anki-ai | Main application | 8501 |
| tunnel | Cloudflare tunnel | N/A |

### Data Persistence

User data and API keys are persisted via volume mount:
```yaml
volumes:
  - ./data:/app/data
```

### Health Checks

The application includes health checks that Cloudflare tunnel depends on:
```yaml
healthcheck:
  test: ["CMD", "curl", "-f", "http://localhost:8501/_stcore/health"]
  interval: 30s
  timeout: 10s
```

---

## 🌐 Cloudflare Tunnel Setup

For production deployment with a persistent URL, configure a Cloudflare Tunnel.

### Prerequisites

- A domain managed by Cloudflare
- `cloudflared` installed locally

### Quick Setup

1. **Authenticate with Cloudflare**
   ```bash
   cloudflared tunnel login
   ```

2. **Create a Tunnel**
   ```bash
   cloudflared tunnel create anki-ai
   ```
   Save the tunnel ID that's returned.

3. **Configure the Tunnel**

   Copy `cloudflared/config.yml.example` to `cloudflared/config.yml` and update:
   ```yaml
   tunnel: YOUR_TUNNEL_UUID
   credentials-file: /home/cloudflared/.cloudflared/YOUR_TUNNEL_UUID.json

   ingress:
     - hostname: anki.yourdomain.com
       service: http://anki-ai:8501
     - service: http_status:404
   ```

4. **Copy Credentials**
   ```bash
   mkdir -p cloudflared
   cp ~/.cloudflared/*.cert cloudflared/
   cp ~/.cloudflared/<TUNNEL_UUID>.json cloudflared/
   ```

5. **Add DNS Record**
   ```bash
   cloudflared tunnel route dns anki-ai anki.yourdomain.com
   ```

6. **Start Services**
   ```bash
   docker-compose up -d
   ```

Your app will be accessible at `https://anki.yourdomain.com`

### Alternative: Tunnel Token

For a simpler setup, use a tunnel token in your `.env`:
```env
TUNNEL_TOKEN=eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...
```

> See [CLOUDFLARE_TUNNEL_SETUP.md](CLOUDFLARE_TUNNEL_SETUP.md) for detailed instructions.

---

## 📖 Usage Guide

### 1. Login or Continue as Guest

- **Registered User**: Your API keys and history are saved
- **Guest Mode**: Try the app without registration (keys not saved)

### 2. Configure API Keys

Enter keys in the sidebar or use environment variables.

### 3. Upload PDFs

Drag and drop one or more medical PDFs.

### 4. Choose Processing Mode

| Mode | Description |
|------|-------------|
| **Process Files** | Generates AI summaries + prepares for card generation |
| **⚡ Fast Track** | Skips summaries, jumps straight to card generation |

### 5. Configure Options

- Card density (Low, Normal, High)
- Answer length (Short, Medium, Long)
- Deck organization (Subdecks, Tags, Both)
- Formatting mode

### 6. Generate & Export

- **Download**: Get a `.txt` file for Anki import
- **Push**: Send directly to Anki (requires AnkiConnect)

---

## 🎛️ Settings Reference

| Setting | Options | Description |
|---------|---------|-------------|
| Answer Length | Short, Medium, Long | Controls detail level in card answers |
| Card Density | Low, Normal, High | Number of cards per PDF chunk |
| Highlight Key Terms | On/Off | Bold important keywords |
| Deck Organization | Subdecks, Tags, Both | How cards are organized in Anki |
| Card Formatting | Basic + HTML, Markdown, Legacy LaTeX | Output format for Anki |
| Auto-Detect Chapters | On/Off | Split PDFs into chapter subdecks |
| Show General Chat | On/Off | Enable standalone AI chat panel |

---

## 🧪 Recommended Models

| Use Case | Google Gemini | Z.AI | OpenRouter |
|----------|---------------|------|------------|
| Card Generation | `gemini-3-flash` | `GLM-4.7` | `xiaomi/mimo-v2-flash:free` |
| Summaries | `gemma-3-27b-it` | `GLM-4.5-air` | `google/gemini-2.0-flash-exp:free` |
| Chapter Detection | `gemma-3-27b-it` | `GLM-4.7` | `google/gemma-3-27b-it:free` |

---

## 🛠️ Troubleshooting

### Rate Limit Errors (429)
- The app automatically falls back to other models
- Add fallback API keys for redundancy
- Reduce chunk size to lower API calls

### Duplicate Cards
- Anti-duplicate instructions are built into prompts
- Use smaller chunk sizes for better context
- Try Gemini models (often better deduplication)

### Cards Not Rendering
- Use "Basic + HTML" formatting mode
- Ensure Anki has HTML rendering enabled

### Password Reset Email Not Sending
- Check SMTP configuration in `.env`
- For Gmail, use an App Password (not your account password)
- Check spam folder
- Review logs: `docker logs anki-ai`

### Cloudflare Tunnel Not Starting
- Verify tunnel UUID matches in `config.yml` and filename
- Ensure `cloudflared/` directory contains both `.cert` and `.json` files
- Check container logs: `docker logs anki-tunnel`

### Login Issues After Migration
- Old SHA-256 passwords are automatically migrated to bcrypt on first login
- If login fails, use "Forgot Password" to reset

---

## 📄 License

MIT License - See [LICENSE](LICENSE) file

---

## 🤝 Contributing

Contributions are welcome! Please feel free to submit a Pull Request.

---

*Built for medical students and USMLE preparation.*
