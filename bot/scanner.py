"""
Market scanner for fetching active markets from Polymarket.

This module handles the retrieval and normalization of market data from the
Polymarket Gamma API. It performs no business logic - only data fetching and
transformation into structured Python objects.
"""

import logging
from typing import Optional
from datetime import datetime
import requests
from requests.exceptions import RequestException, Timeout, ConnectionError

from bot.config import Config
from bot.models import Market

# Configure module logger
logger = logging.getLogger(__name__)


def fetch_markets(limit: Optional[int] = None) -> list[Market]:
    """
    Fetch active markets from Polymarket Gamma API.
    
    Retrieves market data from Polymarket and normalizes it into Market
    dataclass objects. Handles API failures gracefully and returns an empty
    list on error.
    
    Args:
        limit: Maximum number of markets to fetch. If None, uses Config.MAX_MARKETS_TO_SCAN.
    
    Returns:
        List of Market objects representing active markets. Returns empty list
        on API failure or if no markets are found.
    
    Raises:
        No exceptions are raised - all errors are logged and handled gracefully.
    """
    if limit is None:
        limit = Config.MAX_MARKETS_TO_SCAN
    
    logger.info(f"Fetching up to {limit} active markets from Polymarket")
    
    try:
        # Polymarket Gamma API endpoint (public, no auth required)
        url = "https://gamma-api.polymarket.com/markets"
        
        params = {
            "closed": "false",  # Only active markets
            "limit": limit,
            "offset": 0,
        }
        
        logger.debug(f"Requesting markets from {url} with params: {params}")
        
        response = requests.get(
            url,
            params=params,
            timeout=Config.API_TIMEOUT,
            headers={
                "Accept": "application/json",
                "User-Agent": "PolymarketResearchBot/1.0"
            }
        )
        
        response.raise_for_status()
        
        data = response.json()
        logger.info(f"Received response with {len(data) if isinstance(data, list) else 'unknown'} markets")
        
        # Normalize API response to Market objects
        markets = _normalize_markets(data)
        
        logger.info(f"Successfully normalized {len(markets)} markets")
        return markets
        
    except Timeout:
        logger.error(f"Request to Polymarket API timed out after {Config.API_TIMEOUT}s")
        return []
    
    except ConnectionError as e:
        logger.error(f"Connection error while fetching markets: {e}")
        return []
    
    except RequestException as e:
        logger.error(f"API request failed: {e}")
        if hasattr(e, 'response') and e.response is not None:
            logger.error(f"Response status: {e.response.status_code}")
            logger.error(f"Response body: {e.response.text[:500]}")
        return []
    
    except ValueError as e:
        logger.error(f"Failed to parse JSON response: {e}")
        return []
    
    except Exception as e:
        logger.error(f"Unexpected error while fetching markets: {e}", exc_info=True)
        return []


def _normalize_markets(api_data: list[dict]) -> list[Market]:
    """
    Normalize raw API response data into Market dataclass objects.
    
    Handles missing or malformed fields gracefully by skipping invalid entries
    and logging warnings.
    
    Args:
        api_data: List of market dictionaries from Polymarket API.
    
    Returns:
        List of normalized Market objects. Invalid entries are skipped.
    """
    markets: list[Market] = []
    
    if not isinstance(api_data, list):
        logger.warning(f"Expected list of markets, got {type(api_data)}")
        return markets
    

        
    for idx, market_data in enumerate(api_data):
        try:
            market = _parse_market(market_data)
            if market:
                markets.append(market)
        except Exception as e:
            logger.warning(f"Failed to parse market at index {idx}: {e}")
            logger.debug(f"Market data: {market_data}", exc_info=True)
            continue
    
    return markets


def _parse_market(data: dict) -> Optional[Market]:
    """
    Parse a single market dictionary into a Market object.
    
    Extracts and normalizes required fields with safe defaults for missing data.
    
    Args:
        data: Dictionary containing market data from API.
    
    Returns:
        Market object if parsing succeeds, None otherwise.
    """
    try:
        # Extract required fields with safe defaults
        market_id = data.get("id")
        if not market_id:
            logger.debug("Market missing 'id' field, skipping")
            return None
        
        # Title/Question
        title = data.get("question") or data.get("title") or "Unknown Market"
        
        # Description
        description = data.get("description") or data.get("question") or ""
        
        # Probability calculation from outcomePrices
        # Polymarket provides outcomePrices as a JSON string: '["0.65", "0.35"]'
        probability = _extract_probability(data)
        
        # Liquidity (may be string or number)
        liquidity = _safe_float(data.get("liquidity"), 0.0)
        
        # End date parsing
        end_date = _parse_end_date(data.get("endDate") or data.get("end_date"))
        
        # Additional useful fields
        slug = data.get("slug", "")
        category = data.get("category", "")
        volume_24h = _safe_float(data.get("volume24h") or data.get("volume_24h") or data.get("volume24hr"), 0.0)
        
        return Market(
            id=str(market_id),
            title=title,
            description=description,
            probability=probability,
            liquidity=liquidity,
            end_date=end_date,
            slug=slug,
            category=category,
            volume_24h=volume_24h
        )
        
    except Exception as e:
        logger.debug(f"Error parsing market: {e}", exc_info=True)
        return None


def _extract_probability(data: dict) -> float:
    """
    Extract probability from market data.
    
    Handles API response where fields are often JSON strings.
    """
    try:
        import json
        
        # Method 1: outcomePrices (most common)
        # Format: '["0.65", "0.35"]' (string) OR ["0.65", "0.35"] (list)
        outcome_prices = data.get("outcomePrices")
        outcomes = data.get("outcomes")
        
        # Parse JSON strings if needed
        if isinstance(outcome_prices, str):
            try:
                outcome_prices = json.loads(outcome_prices)
            except:
                pass
                
        if isinstance(outcomes, str):
            try:
                outcomes = json.loads(outcomes)
            except:
                pass
        
        # Ensure we have lists
        if not isinstance(outcome_prices, list) or not outcome_prices:
            # Try fallback to bestBid/bestAsk
            best_bid = data.get("bestBid")
            best_ask = data.get("bestAsk")
            if best_bid and best_ask:
                return (float(best_bid) + float(best_ask)) / 2.0
            return 0.5
            
        # Try to find "Yes" outcome
        if isinstance(outcomes, list):
            try:
                yes_index = outcomes.index("Yes")
                return float(outcome_prices[yes_index])
            except (ValueError, IndexError):
                pass
                
        # Default to first outcome (usually Yes for binary)
        return float(outcome_prices[0]) if outcome_prices else 0.5
        
    except Exception as e:
        logger.debug(f"Error extracting probability: {e}")
        return 0.5





def _parse_end_date(date_str: Optional[str]) -> Optional[datetime]:
    """
    Parse end date string into datetime object.
    
    Handles ISO 8601 format and common variations.
    
    Args:
        date_str: Date string from API (ISO 8601 format expected).
    
    Returns:
        Datetime object if parsing succeeds, None otherwise.
    """
    if not date_str:
        return None
    
    try:
        # Try ISO 8601 format first
        return datetime.fromisoformat(date_str.replace('Z', '+00:00'))
    except (ValueError, AttributeError):
        pass
    
    # Try common alternative formats
    formats = [
        "%Y-%m-%dT%H:%M:%S",
        "%Y-%m-%dT%H:%M:%S.%f",
        "%Y-%m-%d %H:%M:%S",
    ]
    
    for fmt in formats:
        try:
            return datetime.strptime(date_str, fmt)
        except ValueError:
            continue
    
    logger.debug(f"Could not parse end_date: {date_str}")
    return None


def _safe_float(value: Optional[str | float | int], default: float = 0.0) -> float:
    """
    Safely convert a value to float with a default fallback.
    
    Args:
        value: Value to convert (string, float, int, or None).
        default: Default value if conversion fails.
    
    Returns:
        Float value or default if conversion fails.
    """
    if value is None:
        return default
    
    if isinstance(value, (int, float)):
        return float(value)
    
    if isinstance(value, str):
        try:
            return float(value)
        except ValueError:
            logger.debug(f"Could not convert '{value}' to float, using default {default}")
            return default
    
    return default

