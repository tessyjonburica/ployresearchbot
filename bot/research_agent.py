"""
Research agent for gathering structured evidence about prediction markets.

This module queries the Perplexity API to collect factual evidence about markets.
It performs NO reasoning or probability estimation - only evidence gathering.
"""

import json
import logging
import re
import time
from typing import Optional, TypedDict
from datetime import datetime

import requests
from requests.exceptions import RequestException, Timeout, ConnectionError

from bot.config import Config
from bot.models import Market

# Configure module logger
logger = logging.getLogger(__name__)


class EvidenceDict(TypedDict, total=False):
    """
    Structured evidence dictionary returned from research.
    
    All fields are required in the final output, but may be empty lists/strings
    if data is unavailable.
    """
    recent_developments: list[str]
    evidence_yes: list[str]
    evidence_no: list[str]
    official_signals: list[str]
    timeline_constraints: list[str]
    source_quality: str


def research_market(market: Market, max_retries: int = 3) -> Optional[EvidenceDict]:
    """
    Gather structured evidence about a prediction market using Perplexity API.
    
    This function performs evidence gathering only - no reasoning or probability
    estimation. It queries Perplexity with a deterministic prompt and returns
    structured JSON evidence.
    
    Args:
        market: Market object to research
        max_retries: Maximum number of retry attempts for malformed responses
    
    Returns:
        EvidenceDict with structured evidence, or None if research fails after retries.
    """
    if not Config.PERPLEXITY_API_KEY:
        logger.error("PERPLEXITY_API_KEY not configured")
        return None
    
    logger.info(f"Researching market: {market.id} - {market.title[:50]}...")
    
    prompt = _build_research_prompt(market)
    
    for attempt in range(1, max_retries + 1):
        try:
            logger.debug(f"Perplexity API call attempt {attempt}/{max_retries}")
            
            response_text = _call_perplexity_api(prompt)
            
            if not response_text:
                logger.warning(f"Empty response from Perplexity (attempt {attempt})")
                if attempt < max_retries:
                    time.sleep(2 ** attempt)  # Exponential backoff
                    continue
                return None
            
            evidence = _parse_and_validate_response(response_text, market.id)
            
            if evidence:
                logger.info(f"Successfully gathered evidence for market {market.id}")
                return evidence
            else:
                logger.warning(f"Failed to parse response (attempt {attempt})")
                if attempt < max_retries:
                    time.sleep(2 ** attempt)
                    continue
        
        except Exception as e:
            logger.error(f"Error during research attempt {attempt}: {e}", exc_info=True)
            if attempt < max_retries:
                time.sleep(2 ** attempt)
                continue
    
    logger.error(f"Failed to gather evidence for market {market.id} after {max_retries} attempts")
    return None


def _build_research_prompt(market: Market) -> str:
    """
    Build a deterministic prompt template for Perplexity research.
    
    The prompt is designed to gather evidence only, with explicit instructions
    to avoid reasoning or probability estimation.
    
    Args:
        market: Market object to research
    
    Returns:
        Formatted prompt string
    """
    end_date_str = ""
    if market.end_date:
        end_date_str = f"Resolution Date: {market.end_date.strftime('%Y-%m-%d %H:%M:%S UTC')}"
    
    prompt = f"""Research the following prediction market question and provide ONLY factual evidence. Do NOT estimate probabilities or make predictions.

MARKET QUESTION: {market.title}

DESCRIPTION: {market.description}

{end_date_str}

INSTRUCTIONS:
1. Gather recent developments relevant to this question
2. List factual evidence that would support a YES outcome
3. List factual evidence that would support a NO outcome
4. Identify any official signals (announcements, statements, etc.)
5. Note timeline constraints or deadlines
6. Assess the quality of available sources

CRITICAL: Provide ONLY evidence and facts. NO reasoning, NO probability estimates, NO conclusions.

Return your response as valid JSON only (no markdown, no code blocks, no explanatory text). Use this exact structure:

{{
  "recent_developments": ["fact 1", "fact 2", ...],
  "evidence_yes": ["evidence supporting yes", ...],
  "evidence_no": ["evidence supporting no", ...],
  "official_signals": ["official statement or announcement", ...],
  "timeline_constraints": ["deadline or time constraint", ...],
  "source_quality": "high|medium|low"
}}

If information is unavailable, use empty arrays [] or "unknown" for source_quality. Do not fabricate sources or evidence."""
    
    return prompt


def _call_perplexity_api(prompt: str) -> Optional[str]:
    """
    Call Perplexity API with the research prompt.
    
    Args:
        prompt: Research prompt string
    
    Returns:
        Response text from API, or None on failure
    """
    url = "https://api.perplexity.ai/chat/completions"
    
    headers = {
        "Authorization": f"Bearer {Config.PERPLEXITY_API_KEY}",
        "Content-Type": "application/json",
    }
    
    payload = {
        "model": Config.PERPLEXITY_MODEL,
        "messages": [
            {
                "role": "user",
                "content": prompt
            }
        ],
        "temperature": Config.PERPLEXITY_TEMPERATURE,
        "max_tokens": Config.PERPLEXITY_MAX_TOKENS,
    }
    
    try:
        logger.debug(f"Calling Perplexity API with model {Config.PERPLEXITY_MODEL}")
        
        response = requests.post(
            url,
            json=payload,
            headers=headers,
            timeout=Config.RESEARCH_TIMEOUT,
        )
        
        response.raise_for_status()
        
        data = response.json()
        
        # Extract content from response
        if "choices" in data and len(data["choices"]) > 0:
            message = data["choices"][0].get("message", {})
            content = message.get("content", "")
            
            if content:
                logger.debug(f"Received response of length {len(content)}")
                return content
        
        logger.warning("Unexpected Perplexity API response structure")
        logger.debug(f"Response data: {json.dumps(data, indent=2)[:500]}")
        return None
    
    except Timeout:
        logger.error(f"Perplexity API request timed out after {Config.RESEARCH_TIMEOUT}s")
        return None
    
    except ConnectionError as e:
        logger.error(f"Connection error calling Perplexity API: {e}")
        return None
    
    except RequestException as e:
        logger.error(f"Perplexity API request failed: {e}")
        if hasattr(e, 'response') and e.response is not None:
            logger.error(f"Response status: {e.response.status_code}")
            try:
                error_body = e.response.json()
                logger.error(f"Error details: {json.dumps(error_body, indent=2)}")
            except:
                logger.error(f"Response text: {e.response.text[:500]}")
        return None
    
    except Exception as e:
        logger.error(f"Unexpected error calling Perplexity API: {e}", exc_info=True)
        return None


def _parse_and_validate_response(response_text: str, market_id: str) -> Optional[EvidenceDict]:
    """
    Parse and validate JSON response from Perplexity.
    
    Handles various response formats (with/without markdown code blocks)
    and validates the schema against EvidenceDict requirements.
    
    Args:
        response_text: Raw response text from Perplexity
        market_id: Market ID for logging context
    
    Returns:
        Validated EvidenceDict, or None if parsing/validation fails
    """
    if not response_text or not response_text.strip():
        logger.warning(f"Empty response text for market {market_id}")
        return None
    
    # Clean response text - remove markdown code blocks if present
    cleaned_text = _extract_json_from_response(response_text)
    
    if not cleaned_text:
        logger.warning(f"Could not extract JSON from response for market {market_id}")
        return None
    
    try:
        # Parse JSON
        data = json.loads(cleaned_text)
        
        if not isinstance(data, dict):
            logger.warning(f"Response is not a JSON object for market {market_id}")
            return None
        
        # Validate and normalize schema
        evidence = _validate_evidence_schema(data, market_id)
        
        return evidence
    
    except json.JSONDecodeError as e:
        logger.error(f"JSON decode error for market {market_id}: {e}")
        logger.debug(f"Failed to parse text: {cleaned_text[:500]}")
        return None
    
    except Exception as e:
        logger.error(f"Error validating evidence for market {market_id}: {e}", exc_info=True)
        return None


def _extract_json_from_response(text: str) -> Optional[str]:
    """
    Extract JSON from response text, handling markdown code blocks.
    
    Args:
        text: Raw response text
    
    Returns:
        Extracted JSON string, or None if extraction fails
    """
    text = text.strip()
    
    # Remove markdown code blocks
    if text.startswith("```json"):
        text = text[7:]
    elif text.startswith("```"):
        text = text[3:]
    
    if text.endswith("```"):
        text = text[:-3]
    
    text = text.strip()
    
    # Try to find JSON object boundaries
    # Look for first { and last }
    first_brace = text.find("{")
    last_brace = text.rfind("}")
    
    if first_brace != -1 and last_brace != -1 and last_brace > first_brace:
        text = text[first_brace:last_brace + 1]
    
    return text if text else None


def _validate_evidence_schema(data: dict, market_id: str) -> EvidenceDict:
    """
    Validate and normalize evidence data against required schema.
    
    Ensures all required fields are present with appropriate types.
    Uses safe defaults for missing or invalid fields.
    
    Args:
        data: Parsed JSON data
        market_id: Market ID for logging context
    
    Returns:
        Validated EvidenceDict with all required fields
    """
    evidence: EvidenceDict = {
        "recent_developments": [],
        "evidence_yes": [],
        "evidence_no": [],
        "official_signals": [],
        "timeline_constraints": [],
        "source_quality": "unknown",
    }
    
    # Validate and extract recent_developments
    if "recent_developments" in data:
        devs = data["recent_developments"]
        if isinstance(devs, list):
            evidence["recent_developments"] = [
                str(item).strip() for item in devs if item
            ][:20]  # Limit to 20 items
        else:
            logger.warning(f"Invalid type for recent_developments in market {market_id}")
    
    # Validate and extract evidence_yes
    if "evidence_yes" in data:
        yes_ev = data["evidence_yes"]
        if isinstance(yes_ev, list):
            evidence["evidence_yes"] = [
                str(item).strip() for item in yes_ev if item
            ][:20]
        else:
            logger.warning(f"Invalid type for evidence_yes in market {market_id}")
    
    # Validate and extract evidence_no
    if "evidence_no" in data:
        no_ev = data["evidence_no"]
        if isinstance(no_ev, list):
            evidence["evidence_no"] = [
                str(item).strip() for item in no_ev if item
            ][:20]
        else:
            logger.warning(f"Invalid type for evidence_no in market {market_id}")
    
    # Validate and extract official_signals
    if "official_signals" in data:
        signals = data["official_signals"]
        if isinstance(signals, list):
            evidence["official_signals"] = [
                str(item).strip() for item in signals if item
            ][:20]
        else:
            logger.warning(f"Invalid type for official_signals in market {market_id}")
    
    # Validate and extract timeline_constraints
    if "timeline_constraints" in data:
        constraints = data["timeline_constraints"]
        if isinstance(constraints, list):
            evidence["timeline_constraints"] = [
                str(item).strip() for item in constraints if item
            ][:20]
        else:
            logger.warning(f"Invalid type for timeline_constraints in market {market_id}")
    
    # Validate and extract source_quality
    if "source_quality" in data:
        quality = str(data["source_quality"]).strip().lower()
        if quality in ["high", "medium", "low", "unknown"]:
            evidence["source_quality"] = quality
        else:
            logger.warning(f"Invalid source_quality value '{quality}' in market {market_id}, using 'unknown'")
    
    return evidence

