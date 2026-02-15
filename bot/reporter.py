"""
Reporter module for generating readable output of best opportunities.

This module formats and displays ranked market opportunities with key metrics
and decision rationale in a clean, structured format.
"""

import logging
from datetime import datetime
from pathlib import Path
from typing import Optional

from bot.config import Config
from bot.ranker import RankedOpportunity

# Configure module logger
logger = logging.getLogger(__name__)


def generate_report(
    opportunities: list[RankedOpportunity],
    output_file: Optional[Path] = None,
    max_opportunities: Optional[int] = None
) -> str:
    """
    Generate a formatted report of ranked opportunities.
    
    Args:
        opportunities: List of RankedOpportunity objects (should be pre-sorted)
        output_file: Optional path to save report to file
        max_opportunities: Maximum number of opportunities to include (uses Config if None)
    
    Returns:
        Formatted report string
    """
    if max_opportunities is None:
        max_opportunities = Config.MAX_OPPORTUNITIES_IN_REPORT
    
    # Limit opportunities
    opportunities = opportunities[:max_opportunities]
    
    # Generate report sections
    header = _generate_header(len(opportunities))
    summary = _generate_summary(opportunities)
    opportunities_section = _generate_opportunities_section(opportunities)
    
    # Combine sections
    report = f"{header}\n\n{summary}\n\n{opportunities_section}"
    
    # Save to file if requested
    if output_file:
        _save_report_to_file(report, output_file)
    
    return report


def print_report(opportunities: list[RankedOpportunity]) -> None:
    """
    Print report to console.
    
    Convenience function that generates and prints the report.
    
    Args:
        opportunities: List of RankedOpportunity objects
    """
    report = generate_report(opportunities)
    print(report)


def _generate_header(opportunity_count: int) -> str:
    """
    Generate report header section.
    
    Args:
        opportunity_count: Number of opportunities in report
    
    Returns:
        Header string
    """
    now = datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S UTC")
    
    header = f"""
{'='*80}
  PREDICTION MARKET RESEARCH BOT - OPPORTUNITY REPORT
{'='*80}
Generated: {now}
Opportunities Found: {opportunity_count}
{'='*80}
"""
    return header.strip()


def _generate_summary(opportunities: list[RankedOpportunity]) -> str:
    """
    Generate summary statistics section.
    
    Args:
        opportunities: List of ranked opportunities
    
    Returns:
        Summary string
    """
    if not opportunities:
        return "No opportunities found."
    
    # Calculate statistics
    total = len(opportunities)
    yes_count = sum(1 for opp in opportunities if opp.decision.decision == "yes")
    no_count = sum(1 for opp in opportunities if opp.decision.decision == "no")
    
    avg_score = sum(opp.score for opp in opportunities) / total
    avg_edge = sum(abs(opp.decision.edge) for opp in opportunities) / total
    avg_confidence = sum(opp.decision.confidence_level for opp in opportunities) / total
    total_liquidity = sum(opp.market.liquidity for opp in opportunities)
    
    summary = f"""
SUMMARY STATISTICS
{'-'*80}
Total Opportunities: {total}
  - YES Recommendations: {yes_count}
  - NO Recommendations: {no_count}

Average Metrics:
  - Score: {avg_score:.3f}
  - Edge: {avg_edge:.1%}
  - Confidence: {avg_confidence:.1%}
  - Total Liquidity: ${total_liquidity:,.0f}
"""
    return summary.strip()


def _generate_opportunities_section(opportunities: list[RankedOpportunity]) -> str:
    """
    Generate detailed opportunities section.
    
    Args:
        opportunities: List of ranked opportunities
    
    Returns:
        Opportunities section string
    """
    if not opportunities:
        return "No opportunities to display."
    
    sections = ["RANKED OPPORTUNITIES", "-" * 80]
    
    for idx, opp in enumerate(opportunities, 1):
        opp_text = _format_opportunity(idx, opp)
        sections.append(opp_text)
        sections.append("")  # Blank line between opportunities
    
    return "\n".join(sections)


def _format_opportunity(rank: int, opportunity: RankedOpportunity) -> str:
    """
    Format a single opportunity with all key metrics.
    
    Args:
        rank: Ranking position (1-based)
        opportunity: RankedOpportunity object
    
    Returns:
        Formatted opportunity string
    """
    market = opportunity.market
    decision = opportunity.decision
    
    # Format edge with direction
    edge_pct = abs(decision.edge) * 100
    edge_direction = "OVERPRICED" if decision.edge > 0 else "UNDERPRICED"
    edge_sign = "+" if decision.edge > 0 else ""
    
    # Format time to resolution
    time_str = _format_time_to_resolution(market.end_date)
    
    # Format decision
    decision_emoji = "✅" if decision.decision == "yes" else "❌" if decision.decision == "no" else "⏸️"
    
    lines = [
        f"[{rank}] {market.title}",
        f"    Market ID: {market.id}",
        f"    Category: {market.category or 'N/A'}",
        "",
        f"    SCORE: {opportunity.score:.3f} (Edge: {opportunity.edge_score:.2f} | "
        f"Conf: {opportunity.confidence_score:.2f} | "
        f"Liq: {opportunity.liquidity_score:.2f} | "
        f"Time: {opportunity.time_score:.2f})",
        "",
        f"    KEY METRICS:",
        f"      Market Probability: {market.probability:.1%}",
        f"      Estimated Probability: {decision.estimated_probability:.1%}",
        f"      Edge: {edge_sign}{decision.edge:.1%} ({edge_pct:.1f}% {edge_direction})",
        f"      Confidence: {decision.confidence_level:.1%}",
        f"      Liquidity: ${market.liquidity:,.0f}",
        f"      Volume (24h): ${market.volume_24h:,.0f}",
        f"      Time to Resolution: {time_str}",
        "",
        f"    DECISION: {decision_emoji} {decision.decision.upper()}",
        "",
        f"    REASONING:",
        f"      {decision.reasoning_summary}",
    ]
    
    # Add key risks if present
    if decision.key_risks:
        lines.append("")
        lines.append("    KEY RISKS:")
        for risk in decision.key_risks[:5]:  # Limit to top 5 risks
            lines.append(f"      • {risk}")
    
    return "\n".join(lines)


def _format_time_to_resolution(end_date: Optional[datetime]) -> str:
    """
    Format time to resolution as human-readable string.
    
    Args:
        end_date: Market resolution date
    
    Returns:
        Formatted time string
    """
    if not end_date:
        return "Unknown"
    
    now = datetime.utcnow()
    if end_date <= now:
        return "RESOLVED"
    
    delta = end_date - now
    days = delta.days
    hours = delta.seconds // 3600
    minutes = (delta.seconds % 3600) // 60
    
    if days > 0:
        if hours > 0:
            return f"{days} days, {hours} hours"
        return f"{days} days"
    elif hours > 0:
        if minutes > 0:
            return f"{hours} hours, {minutes} minutes"
        return f"{hours} hours"
    else:
        return f"{minutes} minutes"


def _save_report_to_file(report: str, file_path: Path) -> None:
    """
    Save report to file.
    
    Args:
        report: Report string
        file_path: Path to save file
    """
    try:
        file_path.parent.mkdir(parents=True, exist_ok=True)
        file_path.write_text(report, encoding='utf-8')
        logger.info(f"Report saved to {file_path}")
    except Exception as e:
        logger.error(f"Error saving report to {file_path}: {e}", exc_info=True)


def generate_daily_report(
    opportunities: list[RankedOpportunity],
    save_to_file: bool = True
) -> str:
    """
    Generate a daily report with timestamped filename.
    
    Args:
        opportunities: List of ranked opportunities
        save_to_file: Whether to save to file automatically
    
    Returns:
        Report string
    """
    report = generate_report(opportunities)
    
    if save_to_file:
        # Generate timestamped filename
        timestamp = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
        filename = f"opportunity_report_{timestamp}.txt"
        file_path = Config.REPORT_OUTPUT_DIR / filename
        
        _save_report_to_file(report, file_path)
    
    return report


def format_telegram_message(opportunities: list[RankedOpportunity], max_opportunities: int = 5) -> str:
    """
    Format opportunities as Telegram-ready message.
    
    Creates a condensed format suitable for Telegram messaging.
    
    Args:
        opportunities: List of ranked opportunities
        max_opportunities: Maximum opportunities to include
    
    Returns:
        Telegram-formatted message string
    """
    opportunities = opportunities[:max_opportunities]
    
    if not opportunities:
        return "🔍 No opportunities found."
    
    now = datetime.utcnow().strftime("%Y-%m-%d %H:%M")
    lines = [
        f"📊 *Opportunity Report* - {now}",
        f"Found {len(opportunities)} opportunities\n"
    ]
    
    for idx, opp in enumerate(opportunities, 1):
        market = opp.market
        decision = opp.decision
        
        edge_pct = abs(decision.edge) * 100
        edge_sign = "+" if decision.edge > 0 else ""
        decision_emoji = "✅" if decision.decision == "yes" else "❌" if decision.decision == "no" else "⏸️"
        
        lines.append(f"*{idx}. {market.title[:60]}...*")
        lines.append(f"   {decision_emoji} {decision.decision.upper()} | "
                    f"Edge: {edge_sign}{edge_pct:.1f}% | "
                    f"Conf: {decision.confidence_level:.0%} | "
                    f"Score: {opp.score:.2f}")
        lines.append("")
    
    return "\n".join(lines)

