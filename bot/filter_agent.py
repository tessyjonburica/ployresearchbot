"""
Filter agent for evaluating market research-worthiness.

This module determines whether a market should proceed to the research stage
based on deterministic evaluation criteria. It performs no external API calls
and uses pure decision logic with a conservative bias.
"""

import logging
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Optional

from bot.models import Market

# Configure module logger
logger = logging.getLogger(__name__)


@dataclass
class FilterDecision:
    """
    Represents a filter decision for a market.
    
    Attributes:
        market_id: ID of the market this decision applies to
        research_worthy: Whether market should proceed to research
        priority_level: Priority level ("low", "medium", "high")
        reasoning_summary: Brief summary of evaluation reasoning
        info_dependency_score: Score for information dependence (0.0 to 1.0)
        efficiency_risk_score: Score for market efficiency risk (0.0 to 1.0)
        randomness_risk_score: Score for randomness risk (0.0 to 1.0)
    """
    market_id: str
    research_worthy: bool
    priority_level: str
    reasoning_summary: str
    info_dependency_score: float
    efficiency_risk_score: float
    randomness_risk_score: float


def evaluate_market(market: Market) -> FilterDecision:
    """
    Evaluate a market for research-worthiness.
    
    Uses deterministic scoring across five dimensions:
    1. Information Dependence
    2. Information Accessibility
    3. Market Efficiency Risk
    4. Time Sufficiency
    5. Randomness Risk
    
    Args:
        market: Market object to evaluate
    
    Returns:
        FilterDecision with evaluation results
    """
    logger.debug(f"Evaluating market: {market.id} - {market.title[:50]}...")
    
    # Calculate component scores
    info_dependency = _score_information_dependence(market)
    info_accessibility = _score_information_accessibility(market)
    efficiency_risk = _score_market_efficiency_risk(market)
    time_sufficiency = _score_time_sufficiency(market)
    randomness_risk = _score_randomness_risk(market)
    
    # Store component scores (using info_dependency as primary)
    info_dependency_score = info_dependency
    efficiency_risk_score = efficiency_risk
    randomness_risk_score = randomness_risk
    
    # Calculate composite research-worthiness score
    # Weighted combination with conservative bias
    research_score = (
        info_dependency * 0.30 +      # 30% - How much info matters
        info_accessibility * 0.25 +   # 25% - Can we get the info?
        (1.0 - efficiency_risk) * 0.20 +  # 20% - Lower efficiency = better
        time_sufficiency * 0.15 +        # 15% - Do we have time?
        (1.0 - randomness_risk) * 0.10   # 10% - Lower randomness = better
    )
    
    # Conservative threshold: require score >= 0.6 to be research-worthy
    research_worthy = research_score >= 0.6
    
    # Determine priority level
    if research_score >= 0.8:
        priority_level = "high"
    elif research_score >= 0.65:
        priority_level = "medium"
    else:
        priority_level = "low"
    
    # Generate reasoning summary
    reasoning_summary = _generate_reasoning(
        market,
        research_score,
        research_worthy,
        info_dependency,
        info_accessibility,
        efficiency_risk,
        time_sufficiency,
        randomness_risk
    )
    
    decision = FilterDecision(
        market_id=market.id,
        research_worthy=research_worthy,
        priority_level=priority_level,
        reasoning_summary=reasoning_summary,
        info_dependency_score=info_dependency_score,
        efficiency_risk_score=efficiency_risk_score,
        randomness_risk_score=randomness_risk_score
    )
    
    logger.debug(f"Market {market.id} evaluation: research_worthy={research_worthy}, priority={priority_level}")
    
    return decision


def _score_information_dependence(market: Market) -> float:
    """
    Score how much the outcome depends on information vs randomness.
    
    Higher score = more information-dependent (better for research).
    
    Indicators of high information dependence:
    - Political/election markets
    - Economic indicators
    - Company/product launches
    - Regulatory decisions
    - Sports with clear favorites
    
    Indicators of low information dependence:
    - Pure randomness (coin flips, dice)
    - Very short-term events
    - Highly efficient markets
    
    Args:
        market: Market object
    
    Returns:
        Score between 0.0 and 1.0
    """
    title_lower = market.title.lower()
    description_lower = market.description.lower()
    category_lower = (market.category or "").lower()
    
    text = f"{title_lower} {description_lower} {category_lower}"
    
    # High information dependence keywords
    high_info_keywords = [
        "election", "vote", "poll", "candidate", "president", "senate", "congress",
        "policy", "regulation", "fda", "sec", "approval", "decision", "announcement",
        "earnings", "revenue", "profit", "quarterly", "financial",
        "launch", "release", "product", "feature", "update",
        "trial", "court", "lawsuit", "verdict", "ruling",
        "economic", "gdp", "inflation", "unemployment", "rate",
        "sports", "game", "match", "tournament", "championship"
    ]
    
    # Low information dependence keywords (randomness indicators)
    low_info_keywords = [
        "coin", "flip", "dice", "random", "lottery", "draw",
        "instant", "immediate", "second", "minute"
    ]
    
    # Count keyword matches
    high_info_count = sum(1 for keyword in high_info_keywords if keyword in text)
    low_info_count = sum(1 for keyword in low_info_keywords if keyword in text)
    
    # Base score from keywords
    if high_info_count > 0 and low_info_count == 0:
        base_score = 0.8
    elif high_info_count > 0:
        base_score = 0.6  # Mixed signals
    elif low_info_count > 0:
        base_score = 0.2
    else:
        base_score = 0.5  # Neutral
    
    # Adjust based on market characteristics
    # Longer time horizons = more information can emerge
    if market.end_date:
        now = datetime.utcnow()
        if market.end_date > now:
            days = (market.end_date - now).total_seconds() / 86400.0
            if days >= 7:
                time_bonus = 0.1
            elif days >= 3:
                time_bonus = 0.05
            else:
                time_bonus = -0.1  # Too short
        else:
            time_bonus = -0.2  # Already resolved
    else:
        time_bonus = 0.0
    
    # Adjust based on probability (extreme probabilities suggest information asymmetry)
    if 0.1 <= market.probability <= 0.9:
        prob_bonus = 0.05  # Moderate uncertainty
    else:
        prob_bonus = 0.0  # Extreme probabilities
    
    score = base_score + time_bonus + prob_bonus
    
    # Clamp to [0.0, 1.0]
    return max(0.0, min(1.0, score))


def _score_information_accessibility(market: Market) -> float:
    """
    Score how accessible information is for this market.
    
    Higher score = information is more accessible (better for research).
    
    Factors:
    - Public vs private information
    - Official sources available
    - News coverage likely
    - Data availability
    
    Args:
        market: Market object
    
    Returns:
        Score between 0.0 and 1.0
    """
    title_lower = market.title.lower()
    description_lower = market.description.lower()
    category_lower = (market.category or "").lower()
    
    text = f"{title_lower} {description_lower} {category_lower}"
    
    # High accessibility indicators
    high_access_keywords = [
        "official", "announcement", "press", "release", "statement",
        "public", "government", "federal", "state", "agency",
        "company", "corporation", "earnings", "report",
        "election", "poll", "survey", "data",
        "news", "media", "coverage"
    ]
    
    # Low accessibility indicators (private/insider info)
    low_access_keywords = [
        "insider", "private", "confidential", "secret",
        "internal", "leak", "rumor", "speculation"
    ]
    
    high_access_count = sum(1 for keyword in high_access_keywords if keyword in text)
    low_access_count = sum(1 for keyword in low_access_keywords if keyword in text)
    
    # Base score
    if high_access_count > 0 and low_access_count == 0:
        base_score = 0.8
    elif high_access_count > 0:
        base_score = 0.6
    elif low_access_count > 0:
        base_score = 0.3
    else:
        base_score = 0.5
    
    # Adjust based on liquidity (higher liquidity = more attention = more info)
    if market.liquidity >= 10000:
        liquidity_bonus = 0.1
    elif market.liquidity >= 5000:
        liquidity_bonus = 0.05
    else:
        liquidity_bonus = 0.0
    
    # Adjust based on volume (active markets = more info flow)
    if market.volume_24h >= 1000:
        volume_bonus = 0.1
    elif market.volume_24h >= 500:
        volume_bonus = 0.05
    else:
        volume_bonus = 0.0
    
    score = base_score + liquidity_bonus + volume_bonus
    
    return max(0.0, min(1.0, score))


def _score_market_efficiency_risk(market: Market) -> float:
    """
    Score the risk that the market is already efficient (no edge possible).
    
    Higher score = higher efficiency risk (worse for research).
    
    Factors:
    - Market liquidity (higher = more efficient)
    - Trading volume (higher = more efficient)
    - Time since market creation
    - Category (some categories are more efficient)
    
    Args:
        market: Market object
    
    Returns:
        Score between 0.0 and 1.0 (higher = more efficient = worse)
    """
    # Base efficiency from liquidity
    if market.liquidity >= 50000:
        liquidity_risk = 0.8  # Very efficient
    elif market.liquidity >= 20000:
        liquidity_risk = 0.6
    elif market.liquidity >= 10000:
        liquidity_risk = 0.4
    elif market.liquidity >= 5000:
        liquidity_risk = 0.3
    else:
        liquidity_risk = 0.2  # Less efficient
    
    # Volume risk
    if market.volume_24h >= 5000:
        volume_risk = 0.3
    elif market.volume_24h >= 2000:
        volume_risk = 0.2
    elif market.volume_24h >= 1000:
        volume_risk = 0.1
    else:
        volume_risk = 0.0
    
    # Category-based efficiency (some categories are more efficient)
    category_lower = (market.category or "").lower()
    if any(cat in category_lower for cat in ["crypto", "bitcoin", "ethereum"]):
        category_risk = 0.2  # Crypto markets often efficient
    elif any(cat in category_lower for cat in ["sports", "nfl", "nba", "mlb"]):
        category_risk = 0.3  # Sports markets can be efficient
    else:
        category_risk = 0.1
    
    # Probability-based risk (extreme probabilities suggest efficiency)
    if 0.05 <= market.probability <= 0.95:
        prob_risk = 0.0  # Moderate probability = room for edge
    else:
        prob_risk = 0.2  # Extreme = likely efficient
    
    # Weighted combination
    efficiency_risk = (
        liquidity_risk * 0.40 +
        volume_risk * 0.30 +
        category_risk * 0.20 +
        prob_risk * 0.10
    )
    
    return max(0.0, min(1.0, efficiency_risk))


def _score_time_sufficiency(market: Market) -> float:
    """
    Score whether there is sufficient time for research and information to emerge.
    
    Higher score = more time available (better for research).
    
    Args:
        market: Market object
    
    Returns:
        Score between 0.0 and 1.0
    """
    if not market.end_date:
        return 0.5  # Unknown time = neutral
    
    now = datetime.utcnow()
    if market.end_date <= now:
        return 0.0  # Already resolved
    
    delta = market.end_date - now
    days = delta.total_seconds() / 86400.0
    
    # Optimal range: 7-30 days
    if 7.0 <= days <= 30.0:
        return 1.0
    elif 3.0 <= days < 7.0:
        # Linear interpolation: 3 days = 0.6, 7 days = 1.0
        return 0.6 + (days - 3.0) / 4.0 * 0.4
    elif 30.0 < days <= 90.0:
        # Linear interpolation: 30 days = 1.0, 90 days = 0.5
        return 1.0 - (days - 30.0) / 60.0 * 0.5
    elif 1.0 <= days < 3.0:
        # Very short: 1 day = 0.3, 3 days = 0.6
        return 0.3 + (days - 1.0) / 2.0 * 0.3
    elif days > 90.0:
        # Too far out: uncertainty increases
        return 0.4
    else:
        # Less than 1 day
        return 0.2


def _score_randomness_risk(market: Market) -> float:
    """
    Score the risk that the outcome is largely random (not researchable).
    
    Higher score = higher randomness risk (worse for research).
    
    Args:
        market: Market object
    
    Returns:
        Score between 0.0 and 1.0 (higher = more random = worse)
    """
    title_lower = market.title.lower()
    description_lower = market.description.lower()
    
    text = f"{title_lower} {description_lower}"
    
    # High randomness indicators
    randomness_keywords = [
        "coin", "flip", "dice", "roll", "random", "lottery", "draw",
        "chance", "luck", "gamble", "bet", "instant"
    ]
    
    randomness_count = sum(1 for keyword in randomness_keywords if keyword in text)
    
    # Base score from keywords
    if randomness_count >= 2:
        base_risk = 0.8
    elif randomness_count == 1:
        base_risk = 0.5
    else:
        base_risk = 0.2
    
    # Adjust based on probability (50/50 suggests randomness)
    if 0.45 <= market.probability <= 0.55:
        prob_risk = 0.2
    else:
        prob_risk = 0.0
    
    # Adjust based on time (very short = more random)
    if market.end_date:
        now = datetime.utcnow()
        if market.end_date > now:
            days = (market.end_date - now).total_seconds() / 86400.0
            if days < 1.0:
                time_risk = 0.3  # Very short = likely random
            elif days < 3.0:
                time_risk = 0.1
            else:
                time_risk = 0.0
        else:
            time_risk = 0.0
    else:
        time_risk = 0.0
    
    randomness_risk = base_risk + prob_risk + time_risk
    
    return max(0.0, min(1.0, randomness_risk))


def _generate_reasoning(
    market: Market,
    research_score: float,
    research_worthy: bool,
    info_dependency: float,
    info_accessibility: float,
    efficiency_risk: float,
    time_sufficiency: float,
    randomness_risk: float
) -> str:
    """
    Generate human-readable reasoning summary.
    
    Args:
        market: Market object
        research_score: Composite research score
        research_worthy: Whether market is research-worthy
        info_dependency: Information dependence score
        info_accessibility: Information accessibility score
        efficiency_risk: Market efficiency risk score
        time_sufficiency: Time sufficiency score
        randomness_risk: Randomness risk score
    
    Returns:
        Reasoning summary string
    """
    reasons = []
    
    if research_worthy:
        reasons.append("Research-worthy")
    else:
        reasons.append("Not research-worthy")
    
    # Add key factors
    if info_dependency >= 0.7:
        reasons.append("high info dependence")
    elif info_dependency <= 0.3:
        reasons.append("low info dependence")
    
    if info_accessibility >= 0.7:
        reasons.append("accessible information")
    elif info_accessibility <= 0.3:
        reasons.append("limited information access")
    
    if efficiency_risk >= 0.7:
        reasons.append("high efficiency risk")
    elif efficiency_risk <= 0.3:
        reasons.append("lower efficiency risk")
    
    if time_sufficiency >= 0.7:
        reasons.append("sufficient time")
    elif time_sufficiency <= 0.3:
        reasons.append("limited time")
    
    if randomness_risk >= 0.7:
        reasons.append("high randomness risk")
    elif randomness_risk <= 0.3:
        reasons.append("lower randomness risk")
    
    summary = f"Score: {research_score:.2f}. " + ", ".join(reasons) + "."
    
    return summary

