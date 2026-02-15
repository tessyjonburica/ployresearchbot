"""
Data models for the prediction market research bot.

This module defines the core dataclasses used throughout the application
for representing markets, research reports, and decisions.
"""

from dataclasses import dataclass
from datetime import datetime
from typing import Optional


@dataclass
class Market:
    """
    Represents a prediction market from Polymarket.
    
    Attributes:
        id: Unique market identifier
        title: Market question/title
        description: Market description
        probability: Current implied probability (0.0 to 1.0)
        liquidity: Available liquidity in USD
        end_date: Market resolution date
        slug: URL-friendly identifier
        category: Market category/topic
        volume_24h: 24-hour trading volume in USD
    """
    id: str
    title: str
    description: str
    probability: float
    liquidity: float
    end_date: Optional[datetime]
    slug: str = ""
    category: str = ""
    volume_24h: float = 0.0


@dataclass
class Decision:
    """
    Represents a probability estimation decision for a market.
    
    Attributes:
        market_id: ID of the market this decision applies to
        estimated_probability: True probability estimate (0.0 to 1.0)
        confidence_level: Confidence in the estimate (0.0 to 1.0)
        edge: Calculated edge vs market probability (estimated - market)
        decision: Decision recommendation ("yes", "no", "pass")
        key_risks: List of key risks identified
        reasoning_summary: Brief summary of reasoning
        created_at: Timestamp when decision was made
    """
    market_id: str
    estimated_probability: float
    confidence_level: float
    edge: float
    decision: str
    key_risks: list[str]
    reasoning_summary: str
    created_at: datetime

