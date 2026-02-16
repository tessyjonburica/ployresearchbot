"""
Main orchestration module for the prediction market research bot.

This module coordinates the full pipeline:
1. Fetch markets from Polymarket
2. Filter markets by criteria
3. Research selected markets
4. Evaluate decisions
5. Rank opportunities
6. Store results
7. Generate report
"""

import argparse
import logging
import signal
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Optional

from bot.config import Config
from bot.models import Market, Decision
from bot.scanner import fetch_markets
from bot.filter_agent import evaluate_market, FilterDecision
from bot.research_agent import research_market, EvidenceDict
from bot.judge_agent import judge_market
from bot.ranker import rank_opportunities, RankedOpportunity
from bot.storage import Storage
from bot.reporter import generate_report, print_report, generate_daily_report
from bot.telegram_notifier import send_opportunities
from bot.scheduler import start_scheduler, stop_scheduler, get_scheduler_status


# Configure logging
def setup_logging() -> None:
    """Configure logging for the application."""
    log_format = "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
    log_level = getattr(logging, Config.LOG_LEVEL.upper(), logging.INFO)
    
    handlers = [logging.StreamHandler(sys.stdout)]
    
    if Config.LOG_FILE:
        Config.ensure_directories()
        handlers.append(logging.FileHandler(Config.LOG_FILE))
    
    logging.basicConfig(
        level=log_level,
        format=log_format,
        handlers=handlers
    )


logger = logging.getLogger(__name__)


def filter_markets(markets: list[Market]) -> list[Market]:
    """
    Filter markets based on config-driven criteria.
    
    Filters markets by:
    - Minimum liquidity
    - Minimum 24h volume
    - Time to resolution window
    
    Args:
        markets: List of Market objects to filter
    
    Returns:
        Filtered list of Market objects
    """
    logger.info(f"Filtering {len(markets)} markets")
    
    filtered = []
    now = datetime.now(timezone.utc).replace(tzinfo=None)  # Get UTC time without timezone info
    
    for market in markets:
        # Check liquidity
        if market.liquidity < Config.MIN_LIQUIDITY_USD:
            logger.debug(f"Market {market.id} filtered: liquidity ${market.liquidity:.0f} < ${Config.MIN_LIQUIDITY_USD:.0f}")
            continue
        
        # Check volume
        if market.volume_24h < Config.MIN_VOLUME_24H_USD:
            logger.debug(f"Market {market.id} filtered: volume ${market.volume_24h:.0f} < ${Config.MIN_VOLUME_24H_USD:.0f}")
            continue
        
        # Check time to resolution
        if market.end_date:
            delta = market.end_date - now
            days = delta.total_seconds() / 86400.0
            
            if days < Config.MIN_DAYS_TO_RESOLUTION:
                logger.debug(f"Market {market.id} filtered: {days:.1f} days < {Config.MIN_DAYS_TO_RESOLUTION} days")
                continue
            
            if days > Config.MAX_DAYS_TO_RESOLUTION:
                logger.debug(f"Market {market.id} filtered: {days:.1f} days > {Config.MAX_DAYS_TO_RESOLUTION} days")
                continue
        else:
            # No end date - skip if we require time window
            if Config.MIN_DAYS_TO_RESOLUTION > 0 or Config.MAX_DAYS_TO_RESOLUTION < 999:
                logger.debug(f"Market {market.id} filtered: no end_date")
                continue
        
        filtered.append(market)
    
    logger.info(f"Filtered to {len(filtered)} markets")
    return filtered


def run_pipeline() -> Optional[list[RankedOpportunity]]:
    """
    Execute the full research pipeline.
    
    Returns:
        List of ranked opportunities, or None if pipeline fails
    """
    logger.info("=" * 80)
    logger.info("Starting prediction market research pipeline")
    logger.info("=" * 80)
    
    # Validate configuration
    is_valid, errors = Config.validate()
    if not is_valid:
        logger.error("Configuration validation failed:")
        for error in errors:
            logger.error(f"  - {error}")
        return None
    
    # Ensure directories exist
    Config.ensure_directories()
    
    # Initialize storage
    storage = Storage()
    
    # Step 1: Fetch markets
    logger.info("Step 1: Fetching markets from Polymarket")
    markets = fetch_markets(limit=Config.MAX_MARKETS_TO_SCAN)
    
    if not markets:
        logger.error("No markets fetched. Pipeline aborted.")
        return None
    
    logger.info(f"Fetched {len(markets)} markets")
    
    # --- TEMPORARY: Send scanned markets to Telegram ---
    try:
        from bot.telegram_notifier import send_notification
        
        # Format the top 20 markets with more details
        count = len(markets)
        lines = [f"🔍 *Scanned {count} Markets (Showing Top 20)*\n"]
        
        for i, m in enumerate(markets[:20], 1):
            # Clean title
            safe_title = m.title.replace("*", "").replace("_", "").replace("[", "").replace("]", "")
            
            # Format numbers
            prob = m.probability * 100
            liq = f"${m.liquidity:,.0f}"
            vol = f"${m.volume_24h:,.0f}"
            
            # Format date
            date_str = "No date"
            if m.end_date:
                date_str = m.end_date.strftime("%b %d")
            
            # Create detailed entry
            entry = (
                f"*{i}. {safe_title}*\n"
                f"   📊 Prob: {prob:.1f}% | 📅 {date_str}\n"
                f"   💧 Liq: {liq} | 📉 Vol: {vol}\n"
            )
            lines.append(entry)
            
        if count > 20:
            lines.append(f"...and {count-20} more markets.")
            
        # Send as one message (Telegram limit is 4096 chars)
        send_notification("\n".join(lines))
        logger.info("Sent detailed market list to Telegram")
    except Exception as e:
        logger.error(f"Failed to send temporary Telegram message: {e}")
    # ---------------------------------------------------
    
    # Save all fetched markets
    for market in markets:
        storage.save_market(market)
    
    # Step 2: Filter markets (basic criteria: liquidity, volume, time)
    logger.info("Step 2: Filtering markets by basic criteria")
    filtered_markets = filter_markets(markets)
    
    if not filtered_markets:
        logger.warning("No markets passed basic filtering criteria. Pipeline aborted.")
        return None
    
    logger.info(f"{len(filtered_markets)} markets passed basic filtering")
    
    # Step 2b: Evaluate research-worthiness using filter_agent
    logger.info("Step 2b: Evaluating research-worthiness")
    research_worthy_markets: list[tuple[Market, FilterDecision]] = []
    
    for market in filtered_markets:
        try:
            filter_decision = evaluate_market(market)
            
            if filter_decision.research_worthy:
                research_worthy_markets.append((market, filter_decision))
                logger.debug(
                    f"Market {market.id} is research-worthy "
                    f"(priority: {filter_decision.priority_level}, score: {filter_decision.info_dependency_score:.2f})"
                )
            else:
                logger.debug(f"Market {market.id} not research-worthy: {filter_decision.reasoning_summary}")
        
        except Exception as e:
            logger.error(f"Error evaluating market {market.id}: {e}", exc_info=True)
            continue
    
    if not research_worthy_markets:
        logger.warning("No markets passed research-worthiness evaluation. Pipeline aborted.")
        return None
    
    logger.info(f"{len(research_worthy_markets)} markets are research-worthy")
    
    # Sort by priority (high > medium > low) and limit
    research_worthy_markets.sort(
        key=lambda x: {"high": 3, "medium": 2, "low": 1}.get(x[1].priority_level, 0),
        reverse=True
    )
    
    # Limit to MAX_MARKETS_TO_RESEARCH
    markets_to_research = [
        market for market, _ in research_worthy_markets[:Config.MAX_MARKETS_TO_RESEARCH]
    ]
    logger.info(f"Researching top {len(markets_to_research)} research-worthy markets")
    
    # Step 3: Research markets
    logger.info("Step 3: Researching markets with Perplexity")
    research_results: dict[str, tuple[Market, Optional[EvidenceDict]]] = {}
    
    for market in markets_to_research:
        try:
            logger.info(f"Researching market: {market.id} - {market.title[:50]}...")
            evidence = research_market(market)
            
            if evidence:
                research_results[market.id] = (market, evidence)
                storage.save_research_report(market.id, evidence)
                logger.info(f"✓ Research completed for {market.id}")
            else:
                logger.warning(f"✗ Research failed for {market.id}")
        
        except Exception as e:
            logger.error(f"Error researching market {market.id}: {e}", exc_info=True)
            continue
    
    if not research_results:
        logger.error("No markets were successfully researched. Pipeline aborted.")
        return None
    
    logger.info(f"Successfully researched {len(research_results)} markets")
    
    # Step 4: Evaluate decisions
    logger.info("Step 4: Evaluating decisions with Claude")
    decisions: list[Decision] = []
    markets_dict: dict[str, Market] = {}
    
    # Limit to MAX_MARKETS_TO_JUDGE
    markets_to_judge = list(research_results.values())[:Config.MAX_MARKETS_TO_JUDGE]
    
    for market, evidence in markets_to_judge:
        try:
            logger.info(f"Judging market: {market.id} - {market.title[:50]}...")
            decision = judge_market(market, evidence)
            
            if decision:
                decisions.append(decision)
                markets_dict[market.id] = market
                storage.save_decision(decision)
                
                # Log prediction
                storage.log_prediction(
                    market_id=decision.market_id,
                    market_probability=market.probability,
                    estimated_probability=decision.estimated_probability,
                    confidence_level=decision.confidence_level,
                    edge=decision.edge,
                    decision=decision.decision
                )
                
                logger.info(f"✓ Decision made for {market.id}: {decision.decision} (edge: {decision.edge:.1%})")
            else:
                logger.warning(f"✗ Decision failed for {market.id}")
        
        except Exception as e:
            logger.error(f"Error judging market {market.id}: {e}", exc_info=True)
            continue
    
    if not decisions:
        logger.error("No decisions were made. Pipeline aborted.")
        return None
    
    logger.info(f"Successfully evaluated {len(decisions)} markets")
    
    # Step 5: Rank opportunities
    logger.info("Step 5: Ranking opportunities by expected value")
    opportunities = rank_opportunities(decisions, markets_dict, min_edge=0.05)
    
    if not opportunities:
        logger.warning("No opportunities found after ranking")
        return None
    
    logger.info(f"Ranked {len(opportunities)} opportunities")
    
    # Step 6: Results are already stored during pipeline
    logger.info("Step 6: Results stored in database")
    
    return opportunities


def run_pipeline_with_report() -> Optional[list[RankedOpportunity]]:
    """
    Run pipeline and generate report.
    
    Wrapper function that runs the pipeline and generates a report.
    Used by the scheduler for scheduled executions.
    
    Returns:
        List of ranked opportunities, or None if pipeline fails
    """
    opportunities = run_pipeline()
    
    if not opportunities:
        logger.warning("Pipeline completed with no opportunities")
        return None
    
    # Generate report
    logger.info("Step 7: Generating report")
    report = generate_daily_report(opportunities, save_to_file=True)
    
    # Print to console
    print("\n" + "=" * 80)
    print_report(opportunities)
    print("=" * 80 + "\n")
    
    # Step 8: Send Telegram notification (if configured)
    logger.info("Step 8: Sending Telegram notification")
    telegram_sent = send_opportunities(opportunities)
    if telegram_sent:
        logger.info("Telegram notification sent successfully")
    else:
        logger.debug("Telegram notification skipped (not configured or failed)")
    
    logger.info("Pipeline completed successfully")
    logger.info(f"Found {len(opportunities)} ranked opportunities")
    
    return opportunities


def main() -> int:
    """
    Main entry point for the research bot.
    
    Supports two modes:
    - Single run: Execute pipeline once and exit
    - Scheduled: Start scheduler to run pipeline at intervals
    
    Returns:
        Exit code (0 for success, 1 for failure)
    """
    parser = argparse.ArgumentParser(
        description="Prediction Market Research Bot",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Run pipeline once
  python -m bot.main
  
  # Run in scheduled mode (runs every 6 hours by default)
  python -m bot.main --schedule
  
  # Run in scheduled mode with custom interval
  python -m bot.main --schedule --interval 12
        """
    )
    parser.add_argument(
        "--schedule",
        action="store_true",
        help="Run in scheduled mode (continuous execution at intervals)"
    )
    parser.add_argument(
        "--interval",
        type=int,
        default=None,
        help="Hours between pipeline runs (overrides SCAN_INTERVAL_HOURS config)"
    )
    parser.add_argument(
        "--status",
        action="store_true",
        help="Show scheduler status and exit"
    )
    
    args = parser.parse_args()
    
    setup_logging()
    
    # Handle status check
    if args.status:
        status = get_scheduler_status()
        print("\nScheduler Status:")
        print(f"  Running: {status['is_running']}")
        print(f"  Has Pipeline Function: {status['has_pipeline_function']}")
        print(f"  Job Running: {status['job_running']}")
        print(f"  Interval: {status['interval_hours']} hours" if status['interval_hours'] else "  Interval: N/A")
        if status['next_run_time']:
            print(f"  Next Run: {status['next_run_time']}")
        else:
            print("  Next Run: N/A")
        return 0
    
    # Scheduled mode
    if args.schedule:
        return _run_scheduled_mode(args.interval)
    
    # Single run mode (default)
    return _run_single_mode()


def _run_single_mode() -> int:
    """
    Run pipeline once and exit.
    
    Returns:
        Exit code (0 for success, 1 for failure)
    """
    try:
        opportunities = run_pipeline_with_report()
        
        if not opportunities:
            logger.error("Pipeline completed with no opportunities")
            return 1
        
        return 0
    
    except KeyboardInterrupt:
        logger.info("Pipeline interrupted by user")
        return 130
    
    except Exception as e:
        logger.error(f"Fatal error in pipeline: {e}", exc_info=True)
        return 1


def _run_scheduled_mode(interval_hours: Optional[int] = None) -> int:
    """
    Run in scheduled mode with continuous execution.
    
    Args:
        interval_hours: Hours between pipeline runs. If None, uses Config.SCAN_INTERVAL_HOURS
    
    Returns:
        Exit code (0 for success, 1 for failure)
    """
    logger.info("Starting in scheduled mode")
    
    # Setup signal handlers for graceful shutdown
    def signal_handler(signum, frame):
        logger.info(f"Received signal {signum}, shutting down gracefully...")
        stop_scheduler(wait=True)
        sys.exit(0)
    
    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)
    
    try:
        # Start scheduler
        success = start_scheduler(run_pipeline_with_report, interval_hours=interval_hours)
        
        if not success:
            logger.error("Failed to start scheduler")
            return 1
        
        # Log status
        status = get_scheduler_status()
        logger.info("Scheduler started successfully")
        logger.info(f"Interval: {status['interval_hours']} hours")
        if status['next_run_time']:
            logger.info(f"Next run: {status['next_run_time']}")
        
        # Run initial pipeline execution immediately
        logger.info("Running initial pipeline execution...")
        opportunities = run_pipeline_with_report()
        
        if opportunities:
            logger.info(f"Initial run completed: {len(opportunities)} opportunities found")
        else:
            logger.warning("Initial run completed with no opportunities")
        
        # Keep process alive
        logger.info("Scheduler is running. Press Ctrl+C to stop.")
        
        try:
            # Wait indefinitely (scheduler runs in background)
            # Keep process alive - signal handlers will interrupt this
            import time
            logger.info("Scheduler is running. Press Ctrl+C to stop.")
            
            while True:
                time.sleep(1)  # Sleep and check for signals
            
        except KeyboardInterrupt:
            logger.info("Received keyboard interrupt")
            stop_scheduler(wait=True)
            return 0
    
    except Exception as e:
        logger.error(f"Fatal error in scheduled mode: {e}", exc_info=True)
        stop_scheduler(wait=False)
        return 1


if __name__ == "__main__":
    sys.exit(main())

