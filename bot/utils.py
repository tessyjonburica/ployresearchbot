"""
Utility functions for the prediction market research bot.

This module provides shared helper utilities used across the codebase.
All functions are pure helpers with no domain logic.
"""

import json
import logging
import time
from datetime import datetime
from functools import wraps
from typing import Any, Callable, Optional, TypeVar

# Configure module logger
logger = logging.getLogger(__name__)

# Type variable for generic function typing
T = TypeVar('T')


def safe_json_loads(text: str, default: Optional[Any] = None) -> Optional[Any]:
    """
    Safely parse JSON from text, handling malformed AI responses.
    
    Attempts to extract JSON from text that may contain markdown code blocks,
    explanatory text, or other formatting. Returns None on failure.
    
    Args:
        text: Text string that may contain JSON
        default: Default value to return if parsing fails (default: None)
    
    Returns:
        Parsed JSON object/dict/list, or default value if parsing fails
    """
    if not text or not isinstance(text, str):
        return default
    
    text = text.strip()
    
    # Remove markdown code blocks if present
    if text.startswith("```json"):
        text = text[7:]
    elif text.startswith("```"):
        text = text[3:]
    
    if text.endswith("```"):
        text = text[:-3]
    
    text = text.strip()
    
    # Try to find JSON object boundaries
    first_brace = text.find("{")
    first_bracket = text.find("[")
    
    # Determine if JSON is object or array
    if first_brace != -1 and (first_bracket == -1 or first_brace < first_bracket):
        # JSON object
        last_brace = text.rfind("}")
        if last_brace != -1 and last_brace > first_brace:
            text = text[first_brace:last_brace + 1]
    elif first_bracket != -1:
        # JSON array
        last_bracket = text.rfind("]")
        if last_bracket != -1 and last_bracket > first_bracket:
            text = text[first_bracket:last_bracket + 1]
    
    if not text:
        return default
    
    try:
        return json.loads(text)
    except json.JSONDecodeError as e:
        logger.debug(f"JSON decode error: {e}")
        logger.debug(f"Failed to parse text: {text[:200]}")
        return default
    except Exception as e:
        logger.debug(f"Unexpected error parsing JSON: {e}")
        return default


def current_utc_timestamp() -> str:
    """
    Get current UTC timestamp as ISO 8601 string.
    
    Returns:
        ISO 8601 formatted timestamp string (e.g., "2024-01-15T10:30:45.123456")
    """
    return datetime.utcnow().isoformat()


def calculate_edge(
    estimated_probability: float,
    market_probability: float
) -> float:
    """
    Calculate edge between estimated and market probability.
    
    Edge = estimated_probability - market_probability
    
    Positive edge means market is underpricing (estimated > market).
    Negative edge means market is overpricing (estimated < market).
    
    Args:
        estimated_probability: Estimated true probability (0.0 to 1.0)
        market_probability: Current market probability (0.0 to 1.0)
    
    Returns:
        Edge value (can be negative, zero, or positive)
    
    Raises:
        ValueError: If probabilities are outside [0.0, 1.0] range
    """
    if not (0.0 <= estimated_probability <= 1.0):
        raise ValueError(
            f"estimated_probability must be between 0.0 and 1.0, got {estimated_probability}"
        )
    
    if not (0.0 <= market_probability <= 1.0):
        raise ValueError(
            f"market_probability must be between 0.0 and 1.0, got {market_probability}"
        )
    
    return estimated_probability - market_probability


def setup_logger(name: str, level: Optional[int] = None) -> logging.Logger:
    """
    Setup and configure a logger with standard formatting.
    
    Creates a logger with the given name and configures it with
    appropriate formatting if not already configured.
    
    Args:
        name: Logger name (typically __name__)
        level: Logging level (default: INFO if not set)
    
    Returns:
        Configured Logger instance
    """
    logger_instance = logging.getLogger(name)
    
    # Only configure if not already configured
    if not logger_instance.handlers:
        if level is None:
            level = logging.INFO
        
        logger_instance.setLevel(level)
        
        # Create console handler if root logger doesn't have one
        root_logger = logging.getLogger()
        if not root_logger.handlers:
            handler = logging.StreamHandler()
            handler.setLevel(level)
            
            formatter = logging.Formatter(
                "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
            )
            handler.setFormatter(formatter)
            
            logger_instance.addHandler(handler)
    
    return logger_instance


def retry_with_backoff(
    max_retries: int = 3,
    initial_delay: float = 1.0,
    max_delay: float = 60.0,
    exponential_base: float = 2.0,
    exceptions: tuple = (Exception,)
) -> Callable[[Callable[..., T]], Callable[..., T]]:
    """
    Decorator for retrying function calls with exponential backoff.
    
    Retries the decorated function on specified exceptions with exponential
    backoff between attempts. Useful for API calls and network operations.
    
    Args:
        max_retries: Maximum number of retry attempts (default: 3)
        initial_delay: Initial delay in seconds before first retry (default: 1.0)
        max_delay: Maximum delay in seconds between retries (default: 60.0)
        exponential_base: Base for exponential backoff calculation (default: 2.0)
        exceptions: Tuple of exceptions to catch and retry on (default: Exception)
    
    Returns:
        Decorator function
    
    Example:
        @retry_with_backoff(max_retries=3, initial_delay=1.0)
        def api_call():
            # API call code
            pass
    """
    def decorator(func: Callable[..., T]) -> Callable[..., T]:
        @wraps(func)
        def wrapper(*args: Any, **kwargs: Any) -> T:
            last_exception = None
            delay = initial_delay
            
            for attempt in range(max_retries + 1):
                try:
                    return func(*args, **kwargs)
                
                except exceptions as e:
                    last_exception = e
                    
                    if attempt < max_retries:
                        logger.warning(
                            f"{func.__name__} failed (attempt {attempt + 1}/{max_retries + 1}): {e}. "
                            f"Retrying in {delay:.2f}s..."
                        )
                        time.sleep(delay)
                        
                        # Calculate next delay with exponential backoff
                        delay = min(delay * exponential_base, max_delay)
                    else:
                        logger.error(
                            f"{func.__name__} failed after {max_retries + 1} attempts: {e}"
                        )
            
            # All retries exhausted, raise last exception
            raise last_exception
        
        return wrapper
    
    return decorator


def clamp(value: float, min_value: float, max_value: float) -> float:
    """
    Clamp a value between minimum and maximum bounds.
    
    Args:
        value: Value to clamp
        min_value: Minimum allowed value
        max_value: Maximum allowed value
    
    Returns:
        Clamped value between min_value and max_value
    
    Raises:
        ValueError: If min_value > max_value
    """
    if min_value > max_value:
        raise ValueError(f"min_value ({min_value}) must be <= max_value ({max_value})")
    
    return max(min_value, min(value, max_value))


def safe_float(value: Any, default: float = 0.0) -> float:
    """
    Safely convert a value to float with a default fallback.
    
    Handles None, strings, integers, and floats. Returns default on failure.
    
    Args:
        value: Value to convert (string, int, float, or None)
        default: Default value if conversion fails (default: 0.0)
    
    Returns:
        Float value or default if conversion fails
    """
    if value is None:
        return default
    
    if isinstance(value, (int, float)):
        return float(value)
    
    if isinstance(value, str):
        try:
            return float(value)
        except ValueError:
            return default
    
    return default


def format_percentage(value: float, decimals: int = 1) -> str:
    """
    Format a float value as a percentage string.
    
    Args:
        value: Float value (0.0 to 1.0 or 0.0 to 100.0)
        decimals: Number of decimal places (default: 1)
    
    Returns:
        Formatted percentage string (e.g., "65.5%")
    """
    # Handle values that might already be percentages (0-100)
    if value > 1.0:
        percentage = value
    else:
        percentage = value * 100.0
    
    return f"{percentage:.{decimals}f}%"


def format_currency(value: float, decimals: int = 0) -> str:
    """
    Format a float value as a currency string.
    
    Args:
        value: Float value to format
        decimals: Number of decimal places (default: 0)
    
    Returns:
        Formatted currency string (e.g., "$1,234.56")
    """
    if decimals == 0:
        return f"${value:,.0f}"
    else:
        return f"${value:,.{decimals}f}"

