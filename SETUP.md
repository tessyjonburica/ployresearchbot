# 🤖 Polymarket Research Bot - Complete Setup Guide

## 📋 Step-by-Step Setup with Telegram Notifications

### **Step 1: Install Python**
- Ensure you have **Python 3.10 or higher** installed
- Check version: `python --version`
- If not installed, download from https://www.python.org/downloads/

### **Step 2: Install Dependencies**
```bash
cd c:\Users\TESLIM\Desktop\ployresearchbot
pip install -r requirements.txt
```

### **Step 3: Get Your API Keys**

#### **3a. Anthropic Claude API Key**
1. Go to https://console.anthropic.com/
2. Sign up or log in
3. Navigate to "API Keys" section
4. Click "Create Key"
5. Copy your API key (starts with `sk-ant-`)

#### **3b. Perplexity API Key**
1. Go to https://www.perplexity.ai/
2. Sign up or log in
3. Go to https://www.perplexity.ai/settings/api
4. Generate a new API key
5. Copy your API key

#### **3c. Create Telegram Bot**
1. Open Telegram app
2. Search for **@BotFather**
3. Start a chat and send `/newbot`
4. Follow prompts to name your bot
5. Copy the **bot token** (looks like: `123456789:ABCdefGHIjklMNOpqrsTUVwxyz`)

#### **3d. Get Your Telegram Chat ID**
1. In Telegram, search for **@userinfobot**
2. Start a chat and send any message
3. Copy your **Chat ID** (a number like: `123456789`)

### **Step 4: Configure Environment Variables**
```bash
# Copy the example file
copy .env.example .env

# Edit the .env file
notepad .env
```

**Fill in your credentials:**
```env
ANTHROPIC_API_KEY=sk-ant-your-actual-key-here
PERPLEXITY_API_KEY=your-actual-perplexity-key-here
TELEGRAM_BOT_TOKEN=123456789:ABCdefGHIjklMNOpqrsTUVwxyz
TELEGRAM_CHAT_ID=123456789
```

### **Step 5: Test the Bot**

#### **Quick Test (Single Run)**
```bash
python -m bot.main
```

This will:
- ✅ Scan Polymarket markets
- ✅ Research and analyze opportunities
- ✅ Generate a report in the `reports/` folder
- ✅ Send top opportunities to your Telegram

#### **Scheduled Mode (Runs Every 6 Hours)**
```bash
python -m bot.main --schedule
```

Press `Ctrl+C` to stop.

### **Step 6: Verify Telegram Integration**

After running the bot, you should receive a Telegram message like:

```
🎯 Polymarket Opportunities - 2026-02-15 20:17

Found 3 opportunities:

1. 🏆 [Market Title]
   Edge: +12.3% | Confidence: High | Score: 8.2/10
   Decision: YES
   polymarket.com/event/...

2. [...]
```

---

## 🔧 Troubleshooting

### **"No module named 'requests'"**
```bash
pip install -r requirements.txt
```

### **"ANTHROPIC_API_KEY is required but not set"**
- Make sure your `.env` file exists in the project root
- Check that API keys are correctly set (no quotes needed)
- Restart terminal after creating `.env`

### **Telegram message not received**
1. Verify bot token is correct (from @BotFather)
2. Verify chat ID is correct (from @userinfobot)
3. Make sure you've started a chat with your bot first
4. Check logs for Telegram errors: `logs/bot.log`

### **No opportunities found**
This is normal! The bot is conservative and only reports markets with:
- Sufficient edge (>5%)
- Good confidence
- Adequate liquidity
- Researchable topics

Try adjusting filters in `.env`:
```env
MIN_LIQUIDITY_USD=500.0
MIN_VOLUME_24H_USD=100.0
```

---

## 📊 What Happens When Bot Runs

1. **Scans** 100 markets from Polymarket
2. **Filters** by liquidity ($1000+) and volume ($500+)
3. **Evaluates** research-worthiness (information-dependent markets)
4. **Researches** top 10 markets using Perplexity AI
5. **Judges** top 5 markets using Claude AI
6. **Ranks** by expected value
7. **Saves** report to `reports/` folder
8. **Sends** top 5 opportunities to Telegram

---

## 🎯 Recommended Usage

### **For Daily Updates**
```bash
# Run every 12 hours
python -m bot.main --schedule --interval 12
```

### **For Active Trading**
```bash
# Run every 6 hours (default)
python -m bot.main --schedule
```

### **For Testing**
```bash
# Single run
python -m bot.main
```

---

## 📁 Directory Structure After Setup

```
ployresearchbot/
├── bot/                    # Source code
├── data/                   # SQLite database (auto-created)
│   └── research_bot.db
├── logs/                   # Log files (auto-created)
│   └── bot.log
├── reports/                # Generated reports (auto-created)
│   └── report_2026-02-15_20-17-06.txt
├── .env                    # Your configuration (YOU CREATE THIS)
├── .env.example           # Configuration template
├── requirements.txt        # Python dependencies
└── SETUP.md               # This file
```

---

## 🚀 Quick Start Commands

```bash
# 1. Install dependencies
pip install -r requirements.txt

# 2. Copy and configure .env
copy .env.example .env
notepad .env

# 3. Run the bot
python -m bot.main
```

---

## 💡 Tips

- **Start with a single run** to test your setup
- **Check the reports folder** for detailed analysis
- **Monitor logs** for any issues
- **Adjust filters** if you're getting too few/many opportunities
- **Keep your API keys secret** - never commit `.env` to git

---

## 📞 Need Help?

- Check `logs/bot.log` for detailed error messages
- Verify all API keys are valid and have credits
- Ensure you've started a chat with your Telegram bot
- Try reducing `MAX_MARKETS_TO_RESEARCH` if API costs are high

Happy trading! 🎯
