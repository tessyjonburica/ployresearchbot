"""
Ranker module for sorting markets by expected value.

This module ranks evaluated markets based on a deterministic scoring formula
that considers edge, confidence, liquidity, and time feasibility.
"""

import logging
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Optional

from bot.models import Market, Decision

# Configure module logger
logger = logging.getLogger(__name__)


@dataclass
class RankedOpportunity:
    """
    Represents a ranked market opportunity with scoring breakdown.
    
    Attributes:
        market: Market object
        decision: Decision object
        score: Overall ranking score (higher is better)
        edge_score: Component score from edge size
        confidence_score: Component score from confidence level
        liquidity_score: Component score from market liquidity
        time_score: Component score from time feasibility
        explanation: Human-readable explanation of ranking
    """
    market: Market
    decision: Decision
    score: float
    edge_score: float
    confidence_score: float
    liquidity_score: float
    time_score: float
    explanation: str


# Scoring weights (configurable constants)
EDGE_WEIGHT = 0.40      # 40% - Most important: size of edge
CONFIDENCE_WEIGHT = 0.30  # 30% - Confidence in estimate
LIQUIDITY_WEIGHT = 0.20  # 20% - Market depth
TIME_WEIGHT = 0.10       # 10% - Time to resolution


def rank_opportunities(
    decisions: list[Decision],
    markets: dict[str, Market],
    min_edge: float = 0.05
) -> list[RankedOpportunity]:
    """
    Rank markets by expected value using deterministic scoring formula.
    
    Filters out decisions with edge below threshold and ranks remaining
    opportunities by composite score.
    
    Args:
        decisions: List of Decision objects to rank
        markets: Dictionary mapping market_id to Market objects
        min_edge: Minimum absolute edge to include (default 0.05 = 5%)
    
    Returns:
        List of RankedOpportunity objects sorted by score (descending)
    """
    logger.info(f"Ranking {len(decisions)} decisions with minimum edge {min_edge}")
    
    opportunities: list[RankedOpportunity] = []
    
    for decision in decisions:
        # Skip if market not found
        if decision.market_id not in markets:
            logger.warning(f"Market {decision.market_id} not found for decision")
            continue
        
        # Skip if edge is too small
        if abs(decision.edge) < min_edge:
            logger.debug(f"Skipping market {decision.market_id}: edge {decision.edge:.3f} < {min_edge}")
            continue
        
        # Skip "pass" decisions
        if decision.decision == "pass":
            logger.debug(f"Skipping market {decision.market_id}: decision is 'pass'")
            continue
        
        market = markets[decision.market_id]
        
        # Calculate component scores
        edge_score = _calculate_edge_score(decision.edge)
        confidence_score = _calculate_confidence_score(decision.confidence_level)
        liquidity_score = _calculate_liquidity_score(market.liquidity)
        time_score = _calculate_time_score(market.end_date)
        
        # Calculate weighted composite score
        composite_score = (
            edge_score * EDGE_WEIGHT +
            confidence_score * CONFIDENCE_WEIGHT +
            liquidity_score * LIQUIDITY_WEIGHT +
            time_score * TIME_WEIGHT
        )
        
        # Generate explanation
        explanation = _generate_explanation(
            market,
            decision,
            edge_score,
            confidence_score,
            liquidity_score,
            time_score,
            composite_score
        )
        
        opportunity = RankedOpportunity(
            market=market,
            decision=decision,
            score=composite_score,
            edge_score=edge_score,
            confidence_score=confidence_score,
            liquidity_score=liquidity_score,
            time_score=time_score,
            explanation=explanation
        )
        
        opportunities.append(opportunity)
    
    # Sort by score descending
    opportunities.sort(key=lambda x: x.score, reverse=True)
    
    logger.info(f"Ranked {len(opportunities)} opportunities")
    return opportunities


def _calculate_edge_score(edge: float) -> float:
    """
    Calculate score component from edge size.
    
    Uses absolute value of edge. Larger edges score higher.
    Score is normalized to 0.0-1.0 range.
    
    Formula: min(1.0, abs(edge) / 0.20)
    - Edge of 0.20 (20%) = score of 1.0
    - Edge of 0.10 (10%) = score of 0.5
    - Edge of 0.05 (5%) = score of 0.25
    
    Args:
        edge: Edge value (can be positive or negative)
    
    Returns:
        Edge score between 0.0 and 1.0
    """
    abs_edge = abs(edge)
    # Normalize: 20% edge = 1.0, scale linearly
    score = min(1.0, abs_edge / 0.20)
    return score


def _calculate_confidence_score(confidence: float) -> float:
    """
    Calculate score component from confidence level.
    
    Uses confidence directly (already 0.0-1.0).
    Higher confidence = higher score.
    
    Args:
        confidence: Confidence level (0.0 to 1.0)
    
    Returns:
        Confidence score (same as input, 0.0 to 1.0)
    """
    # Confidence is already normalized, use directly
    return max(0.0, min(1.0, confidence))


def _calculate_liquidity_score(liquidity: float) -> float:
    """
    Calculate score component from market liquidity.
    
    Higher liquidity = higher score.
    Uses logarithmic scaling to avoid extreme values dominating.
    
    Formula: min(1.0, log10(liquidity / 1000) / 2.0)
    - $10,000 liquidity ≈ 0.5
    - $100,000 liquidity ≈ 1.0
    - $1,000 liquidity ≈ 0.0
    
    Args:
        liquidity: Market liquidity in USD
    
    Returns:
        Liquidity score between 0.0 and 1.0
    """
    if liquidity <= 0:
        return 0.0
    
    # Logarithmic scaling: $1000 = 0.0, $100k = 1.0
    import math
    try:
        # Normalize: log10(liquidity / 1000) / 2.0
        # This gives: $1k=0, $10k≈0.5, $100k=1.0
        log_score = math.log10(liquidity / 1000.0) / 2.0
        return max(0.0, min(1.0, log_score))
    except (ValueError, ZeroDivisionError):
        return 0.0


def _calculate_time_score(end_date: Optional[datetime]) -> float:
    """
    Calculate score component from time to resolution.
    
    Prefers markets with 7-30 days to resolution.
    Too soon (< 7 days) or too far (> 90 days) score lower.
    
    Scoring:
    - 7-30 days: 1.0 (optimal)
    - 1-7 days: linear 0.5 to 1.0
    - 30-90 days: linear 1.0 to 0.5
    - < 1 day or > 90 days: 0.0
    
    Args:
        end_date: Market resolution date
    
    Returns:
        Time score between 0.0 and 1.0
    """
    if not end_date:
        return 0.5  # Unknown time = neutral score
    
    now = datetime.utcnow()
    if end_date <= now:
        return 0.0  # Already resolved
    
    delta = end_date - now
    days = delta.total_seconds() / 86400.0  # Convert to days
    
    # Optimal range: 7-30 days
    if 7.0 <= days <= 30.0:
        return 1.0
    
    # 1-7 days: linear from 0.5 to 1.0
    if 1.0 <= days < 7.0:
        return 0.5 + (days - 1.0) / 6.0 * 0.5
    
    # 30-90 days: linear from 1.0 to 0.5
    if 30.0 < days <= 90.0:
        return 1.0 - (days - 30.0) / 60.0 * 0.5
    
    # Too soon (< 1 day) or too far (> 90 days)
    return 0.0


def _generate_explanation(
    market: Market,
    decision: Decision,
    edge_score: float,
    confidence_score: float,
    liquidity_score: float,
    time_score: float,
    composite_score: float
) -> str:
    """
    Generate human-readable explanation of ranking.
    
    Args:
        market: Market object
        decision: Decision object
        edge_score: Calculated edge score
        confidence_score: Calculated confidence score
        liquidity_score: Calculated liquidity score
        time_score: Calculated time score
        composite_score: Overall composite score
    
    Returns:
        Explanation string
    """
    edge_pct = decision.edge * 100
    edge_direction = "overpriced" if decision.edge > 0 else "underpriced"
    
    # Format time to resolution
    time_str = "unknown"
    if market.end_date:
        now = datetime.utcnow()
        if market.end_date > now:
            delta = market.end_date - now
            days = delta.days
            if days > 0:
                time_str = f"{days} days"
            else:
                hours = delta.seconds // 3600
                time_str = f"{hours} hours"
        else:
            time_str = "resolved"
    
    explanation = (
        f"Score: {composite_score:.3f} | "
        f"Edge: {abs(edge_pct):.1f}% ({edge_direction}) | "
        f"Confidence: {decision.confidence_level:.1%} | "
        f"Liquidity: ${market.liquidity:,.0f} | "
        f"Time: {time_str} | "
        f"Decision: {decision.decision.upper()}"
    )
    
    return explanation


def rank_opportunities_with_markets(
    decisions: list[Decision],
    markets: list[Market]
) -> list[RankedOpportunity]:
    """
    Convenience function to rank opportunities from lists.
    
    Converts market list to dictionary for internal use.
    
    Args:
        decisions: List of Decision objects
        markets: List of Market objects
    
    Returns:
        List of RankedOpportunity objects sorted by score
    """
    market_dict = {market.id: market for market in markets}
    return rank_opportunities(decisions, market_dict)

