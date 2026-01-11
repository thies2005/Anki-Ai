# Medical PDF to Anki Converter

A powerful AI-powered tool that converts medical PDFs into high-yield Anki flashcards using Google Gemini or OpenRouter models.

![Streamlit](https://img.shields.io/badge/Streamlit-1.41+-red)
![Python](https://img.shields.io/badge/Python-3.11+-blue)
![Docker](https://img.shields.io/badge/Docker-Ready-blue)

## ✨ Features

### AI Providers
- **Google Gemini**: Support for Gemini 2.5, 3.0 Flash, and Gemma 3 27B
- **OpenRouter**: Access to Xiaomi Mimo, DeepSeek, Qwen, and 100+ free models
- **Automatic Fallback**: Rate limit (429) errors automatically switch to backup models

### Card Generation
- **Tab-Separated Output**: Native Anki import format with deck/tag columns
- **Formatting Modes**: Basic + HTML, Markdown, or Legacy LaTeX
- **Subdeck Organization**: Automatic `Medical::FileName::Chapter` hierarchy
- **AI Chapter Detection**: Automatically split PDFs into chapters
- **Anti-Duplicate**: Smart prompting to minimize duplicate cards

### Interface
- **Split-View Layout**: Generate cards on the left, chat with PDFs on the right
- **AI Summaries**: Auto-generate summaries for every uploaded PDF
- **General AI Chat**: Optional chatbot panel (disabled by default)

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

**Google Gemini:**
1. Get API key from [Google AI Studio](https://aistudio.google.com/app/apikey)
2. Enter in the app sidebar or set `GOOGLE_API_KEY` environment variable
3. Optional: Add fallback keys as `FALLBACK_KEY_1` through `FALLBACK_KEY_10`

**OpenRouter:**
1. Get API key from [OpenRouter](https://openrouter.ai/keys)
2. Enter in the app sidebar or set `OPENROUTER_API_KEY` environment variable

### Environment Variables (.env)

```env
GOOGLE_API_KEY=your_gemini_key
OPENROUTER_API_KEY=your_openrouter_key
FALLBACK_KEY_1=optional_backup_key
```

---

## 📖 Usage

1. **Select Provider**: Choose Google Gemini or OpenRouter
2. **Enter API Key**: Paste your key or use environment variables
3. **Upload PDFs**: Drag and drop one or more medical PDFs
4. **Process Files**: Click "Process Files & Generate Summaries"
5. **Configure Options**: Set card density, formatting, deck organization
6. **Generate Cards**: Click "⚡ Generate All Anki Cards"
7. **Download**: Get your `.txt` file ready for Anki import

### Anki Import

1. Open Anki and select a deck
2. File → Import
3. Select your downloaded `.txt` file
4. Anki auto-detects the format via headers

### Direct Browser Push (New!)

Push cards directly to Anki from the web app—no file downloads needed!

**One-time Setup:**
1. In Anki, go to `Tools > Add-ons`
2. Select **AnkiConnect** and click **Config**
3. Change `"webCorsOriginList": ["http://localhost"]` to:
   ```json
   "webCorsOriginList": ["*"]
   ```
4. Restart Anki

**Usage:**
- Click the **"🌐 Direct Browser Push"** button in the app
- Cards are sent directly to your running Anki instance

> **Note:** This works from Streamlit Cloud because the push happens in your browser, which can reach `localhost`.

---

## 🎛️ Settings

| Setting | Description |
|---------|-------------|
| Answer Length | Short (1-2 words), Medium, Long (conceptual) |
| Card Density | Low (key concepts), Normal, High (comprehensive) |
| Highlight Key Terms | Bold important keywords |
| Deck Organization | Subdecks, Tags, or Both |
| Card Formatting | Basic + HTML, Markdown, Legacy LaTeX |
| Auto-Detect Chapters | Split PDFs into chapter subdecks |
| Show General Chat | Enable standalone AI chat panel |

---

## 🧪 Recommended Models

| Use Case | Google Gemini | OpenRouter |
|----------|---------------|------------|
| Card Generation | `gemini-3-flash` | `xiaomi/mimo-v2-flash:free` |
| Summaries | `gemma-3-27b-it` | `google/gemini-2.0-flash-exp:free` |
| Chapter Detection | `gemma-3-27b-it` | `google/gemma-3-27b-it:free` |

---

## 🛠️ Troubleshooting

**429 Rate Limit Errors**
- The app automatically falls back to other models
- Add fallback API keys for Gemini
- Reduce chunk size to lower API calls

**Duplicate Cards**
- Anti-duplicate instructions are built into prompts
- Use smaller chunk sizes for better context
- Try Gemini models (often better deduplication)

**Cards Not Rendering**
- Use "Basic + HTML" formatting mode
- Ensure Anki has HTML rendering enabled

---

## 📄 License

MIT License - See [LICENSE](LICENSE) file

---

*Built for medical students and USMLE preparation.*
