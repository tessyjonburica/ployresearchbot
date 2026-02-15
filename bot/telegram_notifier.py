"""
Telegram notifier for delivering research results.

This module handles sending ranked prediction market opportunities to Telegram.
It uses the python-telegram-bot library for message delivery.
"""

import logging
from typing import Optional

from telegram import Bot
from telegram.error import TelegramError, TimedOut, NetworkError

from bot.config import Config
from bot.ranker import RankedOpportunity

# Configure module logger
logger = logging.getLogger(__name__)


def format_opportunities(opportunities: list[RankedOpportunity]) -> str:
    """
    Format ranked opportunities into a readable Telegram message.
    
    Creates a formatted message with key information for each opportunity:
    - Market title
    - Market probability
    - Estimated probability
    - Edge
    - Confidence
    - Short rationale
    
    Args:
        opportunities: List of ranked opportunities (should be pre-sorted)
    
    Returns:
        Formatted message string ready for Telegram
    """
    if not opportunities:
        return "🔍 No opportunities found."
    
    lines = []
    
    # Header
    lines.append("📊 *Prediction Market Opportunities*")
    lines.append(f"Found {len(opportunities)} ranked opportunities\n")
    
    # Format each opportunity
    for idx, opp in enumerate(opportunities, 1):
        market = opp.market
        decision = opp.decision
        
        # Calculate edge percentage
        edge_pct = decision.edge * 100
        edge_sign = "+" if decision.edge > 0 else ""
        
        # Decision emoji
        decision_emoji = "✅" if decision.decision == "yes" else "❌" if decision.decision == "no" else "⏸️"
        
        # Format opportunity
        lines.append(f"*{idx}. {market.title}*")
        lines.append(f"")
        lines.append(f"📈 Market: {market.probability:.1%}")
        lines.append(f"🎯 Estimated: {decision.estimated_probability:.1%}")
        lines.append(f"💰 Edge: {edge_sign}{edge_pct:.1f}%")
        lines.append(f"🎲 Confidence: {decision.confidence_level:.1%}")
        lines.append(f"⚡ Decision: {decision_emoji} {decision.decision.upper()}")
        
        # Short rationale (truncate if too long)
        rationale = decision.reasoning_summary
        if len(rationale) > 200:
            rationale = rationale[:197] + "..."
        if rationale:
            lines.append(f"💭 {rationale}")
        
        lines.append("")  # Blank line between opportunities
    
    return "\n".join(lines)


def send_telegram_message(message: str) -> bool:
    """
    Send a message to Telegram safely with error handling.
    
    Handles network errors, timeouts, and other Telegram API errors.
    Returns False on any failure, True on success.
    
    Args:
        message: Message text to send (supports Markdown formatting)
    
    Returns:
        True if message sent successfully, False otherwise
    """
    if not Config.TELEGRAM_BOT_TOKEN or not Config.TELEGRAM_CHAT_ID:
        logger.debug("Telegram not configured (missing token or chat_id)")
        return False
    
    if not message or not message.strip():
        logger.warning("Empty message, not sending")
        return False
    
    try:
        # Initialize bot
        bot = Bot(token=Config.TELEGRAM_BOT_TOKEN)
        
        # Parse chat_id (handle both string and int)
        try:
            chat_id = int(Config.TELEGRAM_CHAT_ID)
        except ValueError:
            chat_id = Config.TELEGRAM_CHAT_ID
        
        logger.debug(f"Sending message to Telegram chat {chat_id}")
        
        # Send message with timeout
        bot.send_message(
            chat_id=chat_id,
            text=message,
            parse_mode="Markdown",
            disable_web_page_preview=True,
            timeout=Config.API_TIMEOUT
        )
        
        logger.info("Telegram message sent successfully")
        return True
    
    except TimedOut:
        logger.error(f"Telegram API request timed out after {Config.API_TIMEOUT}s")
        return False
    
    except NetworkError as e:
        logger.error(f"Network error sending Telegram message: {e}")
        return False
    
    except TelegramError as e:
        logger.error(f"Telegram API error: {e}")
        return False
    
    except Exception as e:
        logger.error(f"Unexpected error sending Telegram message: {e}", exc_info=True)
        return False


def send_daily_report(opportunities: list[RankedOpportunity]) -> bool:
    """
    Format and send daily opportunity report to Telegram.
    
    Formats the opportunities using format_opportunities() and sends
    the message via send_telegram_message().
    
    Args:
        opportunities: List of ranked opportunities to report
    
    Returns:
        True if report sent successfully, False otherwise
    """
    if not opportunities:
        logger.debug("No opportunities to send in daily report")
        return False
    
    try:
        # Format opportunities
        message = format_opportunities(opportunities)
        
        # Send message
        return send_telegram_message(message)
    
    except Exception as e:
        logger.error(f"Error sending daily report: {e}", exc_info=True)
        return False


def send_opportunities(
    opportunities: list[RankedOpportunity],
    max_opportunities: Optional[int] = None
) -> bool:
    """
    Send opportunity report to Telegram (backward compatibility).
    
    This function is kept for backward compatibility with existing code.
    It calls send_daily_report() internally.
    
    Args:
        opportunities: List of ranked opportunities
        max_opportunities: Maximum opportunities to include (unused, kept for compatibility)
    
    Returns:
        True if sent successfully, False otherwise
    """
    return send_daily_report(opportunities)


def send_notification(text: str) -> bool:
    """
    Send a simple text notification to Telegram.
    
    Convenience function for sending plain text notifications.
    
    Args:
        text: Notification text to send
    
    Returns:
        True if sent successfully, False otherwise
    """
    if not text or not text.strip():
        logger.warning("Empty notification text, not sending")
        return False
    
    return send_telegram_message(text)
