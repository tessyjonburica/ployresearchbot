"""
Judge agent for estimating true probability vs market probability using Claude.

This module takes market data and research evidence, then uses Claude to estimate
the true probability and calculate edge. It performs conservative probability
estimation with strict validation.
"""

import json
import logging
from datetime import datetime, timedelta
from typing import Optional

import requests
from requests.exceptions import RequestException, Timeout, ConnectionError

from bot.config import Config
from bot.models import Market, Decision
from bot.research_agent import EvidenceDict

# Configure module logger
logger = logging.getLogger(__name__)


def judge_market(
    market: Market,
    evidence: EvidenceDict,
    max_retries: int = 2
) -> Optional[Decision]:
    """
    Estimate true probability vs market probability using Claude.
    
    Takes market data and research evidence, then uses Claude to perform
    conservative probability estimation. Returns a Decision object with
    estimated probability, confidence, edge, and recommendation.
    
    Args:
        market: Market object with current market probability
        evidence: EvidenceDict from research agent
        max_retries: Maximum retry attempts for malformed responses
    
    Returns:
        Decision object with probability estimate and analysis, or None on failure
    """
    if not Config.ANTHROPIC_API_KEY:
        logger.error("ANTHROPIC_API_KEY not configured")
        return None
    
    logger.info(f"Judging market: {market.id} - {market.title[:50]}...")
    
    # Calculate time to resolution
    time_to_resolution = _calculate_time_to_resolution(market.end_date)
    
    # Build deterministic prompt
    prompt = _build_judgment_prompt(market, evidence, time_to_resolution, market.liquidity)
    
    # Call Claude API with retries
    for attempt in range(1, max_retries + 1):
        try:
            logger.debug(f"Claude API call attempt {attempt}/{max_retries}")
            
            response_text = _call_claude_api(prompt)
            
            if not response_text:
                logger.warning(f"Empty response from Claude (attempt {attempt})")
                if attempt < max_retries:
                    continue
                return None
            
            # Parse and validate response
            decision_data = _parse_and_validate_response(response_text, market.id)
            
            if decision_data:
                # Create Decision object
                decision = _create_decision(market, decision_data, evidence)
                logger.info(f"Successfully judged market {market.id}: edge={decision.edge:.3f}")
                return decision
            else:
                logger.warning(f"Failed to parse Claude response (attempt {attempt})")
                if attempt < max_retries:
                    continue
        
        except Exception as e:
            logger.error(f"Error during judgment attempt {attempt}: {e}", exc_info=True)
            if attempt < max_retries:
                continue
    
    logger.error(f"Failed to judge market {market.id} after {max_retries} attempts")
    return None


def _calculate_time_to_resolution(end_date: Optional[datetime]) -> Optional[str]:
    """
    Calculate time to resolution as a human-readable string.
    
    Args:
        end_date: Market resolution date
    
    Returns:
        String describing time to resolution, or None if date is unavailable
    """
    if not end_date:
        return None
    
    now = datetime.utcnow()
    if end_date <= now:
        return "resolved"
    
    delta = end_date - now
    days = delta.days
    hours = delta.seconds // 3600
    
    if days > 0:
        return f"{days} days, {hours} hours"
    elif hours > 0:
        minutes = (delta.seconds % 3600) // 60
        return f"{hours} hours, {minutes} minutes"
    else:
        minutes = delta.seconds // 60
        return f"{minutes} minutes"


def _build_judgment_prompt(
    market: Market,
    evidence: EvidenceDict,
    time_to_resolution: Optional[str],
    liquidity: float
) -> str:
    """
    Build a deterministic prompt for Claude probability estimation.
    
    The prompt emphasizes conservative estimation, uncertainty expression,
    and rejection of weak evidence.
    
    Args:
        market: Market object
        evidence: Evidence dictionary from research
        time_to_resolution: Time until market resolution
        liquidity: Market liquidity in USD
    
    Returns:
        Formatted prompt string
    """
    # Format evidence for prompt
    evidence_text = _format_evidence_for_prompt(evidence)
    
    time_str = time_to_resolution if time_to_resolution else "unknown"
    
    prompt = f"""You are a conservative probability estimator for prediction markets. Your task is to estimate the TRUE probability of a market outcome based on available evidence, then compare it to the current market probability.

MARKET INFORMATION:
Question: {market.title}
Description: {market.description}
Current Market Probability: {market.probability:.1%}
Liquidity: ${liquidity:,.0f}
Time to Resolution: {time_str}

EVIDENCE:
{evidence_text}

INSTRUCTIONS:
1. Estimate the TRUE probability of a YES outcome (0.0 to 1.0)
2. Assess your confidence in this estimate (0.0 to 1.0)
3. Calculate the edge (true_probability - market_probability)
4. Make a decision: "yes" if edge > 0.05, "no" if edge < -0.05, "pass" otherwise
5. Identify key risks that could affect the outcome
6. Provide a brief reasoning summary

CRITICAL RULES:
- Be CONSERVATIVE in probability estimates
- Express UNCERTAINTY when evidence is weak
- REJECT weak evidence - if evidence quality is "low" or evidence is insufficient, use confidence < 0.5
- If source_quality is "low" or evidence lists are mostly empty, be very conservative
- Edge must be significant (>5%) to recommend "yes" or "no"
- Always identify risks, even for high-confidence estimates

Return ONLY valid JSON (no markdown, no code blocks, no explanatory text). Use this exact structure:

{{
  "estimated_probability": 0.65,
  "confidence_level": 0.7,
  "key_risks": ["risk 1", "risk 2", ...],
  "reasoning_summary": "Brief summary of your reasoning (max 200 words)"
}}

All probabilities must be between 0.0 and 1.0. Be conservative."""
    
    return prompt


def _format_evidence_for_prompt(evidence: EvidenceDict) -> str:
    """
    Format evidence dictionary into readable text for prompt.
    
    Args:
        evidence: Evidence dictionary
    
    Returns:
        Formatted evidence text
    """
    lines = []
    
    if evidence.get("recent_developments"):
        lines.append("RECENT DEVELOPMENTS:")
        for dev in evidence["recent_developments"][:10]:
            lines.append(f"  - {dev}")
        lines.append("")
    
    if evidence.get("evidence_yes"):
        lines.append("EVIDENCE SUPPORTING YES:")
        for ev in evidence["evidence_yes"][:10]:
            lines.append(f"  - {ev}")
        lines.append("")
    
    if evidence.get("evidence_no"):
        lines.append("EVIDENCE SUPPORTING NO:")
        for ev in evidence["evidence_no"][:10]:
            lines.append(f"  - {ev}")
        lines.append("")
    
    if evidence.get("official_signals"):
        lines.append("OFFICIAL SIGNALS:")
        for signal in evidence["official_signals"][:10]:
            lines.append(f"  - {signal}")
        lines.append("")
    
    if evidence.get("timeline_constraints"):
        lines.append("TIMELINE CONSTRAINTS:")
        for constraint in evidence["timeline_constraints"][:10]:
            lines.append(f"  - {constraint}")
        lines.append("")
    
    source_quality = evidence.get("source_quality", "unknown")
    lines.append(f"SOURCE QUALITY: {source_quality.upper()}")
    
    if not lines or (len(evidence.get("recent_developments", [])) == 0 and
                     len(evidence.get("evidence_yes", [])) == 0 and
                     len(evidence.get("evidence_no", [])) == 0):
        lines.append("WARNING: Limited evidence available. Be very conservative.")
    
    return "\n".join(lines)


def _call_claude_api(prompt: str) -> Optional[str]:
    """
    Call Anthropic Claude API with the judgment prompt.
    
    Args:
        prompt: Judgment prompt string
    
    Returns:
        Response text from API, or None on failure
    """
    url = "https://api.anthropic.com/v1/messages"
    
    headers = {
        "x-api-key": Config.ANTHROPIC_API_KEY,
        "anthropic-version": "2023-06-01",
        "Content-Type": "application/json",
    }
    
    payload = {
        "model": Config.CLAUDE_MODEL,
        "max_tokens": Config.CLAUDE_MAX_TOKENS,
        "temperature": Config.CLAUDE_TEMPERATURE,
        "messages": [
            {
                "role": "user",
                "content": prompt
            }
        ],
    }
    
    try:
        logger.debug(f"Calling Claude API with model {Config.CLAUDE_MODEL}")
        
        response = requests.post(
            url,
            json=payload,
            headers=headers,
            timeout=Config.API_TIMEOUT,
        )
        
        response.raise_for_status()
        
        data = response.json()
        
        # Extract content from response
        if "content" in data and len(data["content"]) > 0:
            content_block = data["content"][0]
            if "text" in content_block:
                content = content_block["text"]
                logger.debug(f"Received response of length {len(content)}")
                return content
        
        logger.warning("Unexpected Claude API response structure")
        logger.debug(f"Response data: {json.dumps(data, indent=2)[:500]}")
        return None
    
    except Timeout:
        logger.error(f"Claude API request timed out after {Config.API_TIMEOUT}s")
        return None
    
    except ConnectionError as e:
        logger.error(f"Connection error calling Claude API: {e}")
        return None
    
    except RequestException as e:
        logger.error(f"Claude API request failed: {e}")
        if hasattr(e, 'response') and e.response is not None:
            logger.error(f"Response status: {e.response.status_code}")
            try:
                error_body = e.response.json()
                logger.error(f"Error details: {json.dumps(error_body, indent=2)}")
            except:
                logger.error(f"Response text: {e.response.text[:500]}")
        return None
    
    except Exception as e:
        logger.error(f"Unexpected error calling Claude API: {e}", exc_info=True)
        return None


def _parse_and_validate_response(response_text: str, market_id: str) -> Optional[dict]:
    """
    Parse and validate JSON response from Claude.
    
    Strictly validates that response is valid JSON and contains required fields.
    Rejects non-JSON responses.
    
    Args:
        response_text: Raw response text from Claude
        market_id: Market ID for logging context
    
    Returns:
        Validated decision data dictionary, or None if validation fails
    """
    if not response_text or not response_text.strip():
        logger.warning(f"Empty response text for market {market_id}")
        return None
    
    # Extract JSON from response (handle markdown code blocks)
    cleaned_text = _extract_json_from_response(response_text)
    
    if not cleaned_text:
        logger.warning(f"Could not extract JSON from response for market {market_id}")
        logger.debug(f"Response text: {response_text[:500]}")
        return None
    
    try:
        # Parse JSON
        data = json.loads(cleaned_text)
        
        if not isinstance(data, dict):
            logger.warning(f"Response is not a JSON object for market {market_id}")
            return None
        
        # Validate required fields and numeric ranges
        if not _validate_decision_data(data, market_id):
            return None
        
        return data
    
    except json.JSONDecodeError as e:
        logger.error(f"JSON decode error for market {market_id}: {e}")
        logger.debug(f"Failed to parse text: {cleaned_text[:500]}")
        return None
    
    except Exception as e:
        logger.error(f"Error validating decision data for market {market_id}: {e}", exc_info=True)
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
    
    # Find JSON object boundaries
    first_brace = text.find("{")
    last_brace = text.rfind("}")
    
    if first_brace != -1 and last_brace != -1 and last_brace > first_brace:
        text = text[first_brace:last_brace + 1]
    
    return text if text else None


def _validate_decision_data(data: dict, market_id: str) -> bool:
    """
    Validate decision data against required schema and numeric ranges.
    
    Ensures all required fields are present and within valid ranges.
    
    Args:
        data: Parsed JSON data
        market_id: Market ID for logging context
    
    Returns:
        True if validation passes, False otherwise
    """
    required_fields = ["estimated_probability", "confidence_level", "key_risks", "reasoning_summary"]
    
    # Check required fields
    for field in required_fields:
        if field not in data:
            logger.warning(f"Missing required field '{field}' in decision for market {market_id}")
            return False
    
    # Validate estimated_probability (0.0 to 1.0)
    try:
        prob = float(data["estimated_probability"])
        if not (0.0 <= prob <= 1.0):
            logger.warning(f"estimated_probability {prob} out of range [0.0, 1.0] for market {market_id}")
            return False
    except (ValueError, TypeError):
        logger.warning(f"Invalid estimated_probability type for market {market_id}")
        return False
    
    # Validate confidence_level (0.0 to 1.0)
    try:
        conf = float(data["confidence_level"])
        if not (0.0 <= conf <= 1.0):
            logger.warning(f"confidence_level {conf} out of range [0.0, 1.0] for market {market_id}")
            return False
    except (ValueError, TypeError):
        logger.warning(f"Invalid confidence_level type for market {market_id}")
        return False
    
    # Validate key_risks is a list
    if not isinstance(data["key_risks"], list):
        logger.warning(f"key_risks must be a list for market {market_id}")
        return False
    
    # Validate reasoning_summary is a string
    if not isinstance(data["reasoning_summary"], str):
        logger.warning(f"reasoning_summary must be a string for market {market_id}")
        return False
    
    return True


def _create_decision(
    market: Market,
    decision_data: dict,
    evidence: EvidenceDict
) -> Decision:
    """
    Create Decision object from validated decision data.
    
    Calculates edge and determines decision recommendation based on
    estimated probability vs market probability.
    
    Args:
        market: Market object
        decision_data: Validated decision data from Claude
        evidence: Evidence dictionary for context
    
    Returns:
        Decision object
    """
    estimated_prob = float(decision_data["estimated_probability"])
    confidence = float(decision_data["confidence_level"])
    
    # Calculate edge
    edge = estimated_prob - market.probability
    
    # Determine decision based on edge and confidence
    # Require significant edge (>5%) and reasonable confidence (>0.4)
    if edge > 0.05 and confidence > 0.4:
        decision = "yes"
    elif edge < -0.05 and confidence > 0.4:
        decision = "no"
    else:
        decision = "pass"
    
    # Extract and clean key risks
    key_risks = []
    if isinstance(decision_data.get("key_risks"), list):
        key_risks = [str(risk).strip() for risk in decision_data["key_risks"] if risk][:10]
    
    # Extract and clean reasoning summary
    reasoning_summary = str(decision_data.get("reasoning_summary", "")).strip()[:500]
    
    return Decision(
        market_id=market.id,
        estimated_probability=estimated_prob,
        confidence_level=confidence,
        edge=edge,
        decision=decision,
        key_risks=key_risks,
        reasoning_summary=reasoning_summary,
        created_at=datetime.utcnow()
    )

