"""
Quick script to test Telegram bot connection.
Run this to verify your Telegram setup works.
"""

import sys
import os

# Fix Windows console encoding
if sys.platform == 'win32':
    import codecs
    sys.stdout = codecs.getwriter('utf-8')(sys.stdout.buffer, 'strict')
    sys.stderr = codecs.getwriter('utf-8')(sys.stderr.buffer, 'strict')

from dotenv import load_dotenv

# Load environment variables
load_dotenv()

def test_telegram():
    """Test Telegram bot configuration."""
    
    # Check if credentials are set
    bot_token = os.getenv("TELEGRAM_BOT_TOKEN")
    chat_id = os.getenv("TELEGRAM_CHAT_ID")
    
    print("Checking Telegram configuration...\n")
    
    if not bot_token:
        print("[X] TELEGRAM_BOT_TOKEN not found in .env file")
        return False
    
    if not chat_id:
        print("[X] TELEGRAM_CHAT_ID not found in .env file")
        return False
    
    print(f"[OK] TELEGRAM_BOT_TOKEN: {bot_token[:20]}...")
    print(f"[OK] TELEGRAM_CHAT_ID: {chat_id}\n")
    
    # Try to send a test message
    print("Sending test message...\n")
    
    try:
        from telegram import Bot
        import telegram
        
        # Create bot instance
        bot = Bot(token=bot_token)
        
        # Send test message
        message = "Test Message - Your Polymarket Research Bot is connected successfully!"
        
        # Use synchronous method to avoid async warning
        import asyncio
        asyncio.run(bot.send_message(
            chat_id=chat_id,
            text=message,
            parse_mode=None
        ))
        
        print("[SUCCESS] Check your Telegram - you should see a test message!")
        return True
        
    except Exception as e:
        print(f"[ERROR] {e}\n")
        print("Common issues:")
        print("  1. Make sure you clicked 'Start' in your bot's chat")
        print("  2. Verify bot token from @BotFather")
        print("  3. Verify chat ID from @userinfobot")
        return False


if __name__ == "__main__":
    success = test_telegram()
    sys.exit(0 if success else 1)
