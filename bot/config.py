"""
Configuration management for the prediction market research bot.

This module handles all configuration loading from environment variables
and provides type-safe access to configuration values throughout the application.
"""

import os
from typing import Optional
from pathlib import Path
from dotenv import load_dotenv

# Load environment variables from .env file if it exists
load_dotenv()


class Config:
    """
    Centralized configuration class for the research bot.
    
    All configuration values are loaded from environment variables with
    sensible defaults where appropriate. API keys must be provided via
    environment variables for security.
    """
    
    # API Keys (required)
    ANTHROPIC_API_KEY: Optional[str] = os.getenv("ANTHROPIC_API_KEY")
    PERPLEXITY_API_KEY: Optional[str] = os.getenv("PERPLEXITY_API_KEY")
    
    # Polymarket Configuration
    POLYMARKET_API_URL: str = os.getenv(
        "POLYMARKET_API_URL",
        "https://clob.polymarket.com"
    )
    POLYMARKET_GRAPHQL_URL: str = os.getenv(
        "POLYMARKET_GRAPHQL_URL",
        "https://api.thegraph.com/subgraphs/name/polymarket/clob"
    )
    
    # AI Model Configuration
    CLAUDE_MODEL: str = os.getenv("CLAUDE_MODEL", "claude-3-5-sonnet-20241022")
    PERPLEXITY_MODEL: str = os.getenv("PERPLEXITY_MODEL", "llama-3.1-sonar-large-128k-online")
    
    # Research Parameters
    MAX_MARKETS_TO_SCAN: int = int(os.getenv("MAX_MARKETS_TO_SCAN", "100"))
    MAX_MARKETS_TO_RESEARCH: int = int(os.getenv("MAX_MARKETS_TO_RESEARCH", "10"))
    MAX_MARKETS_TO_JUDGE: int = int(os.getenv("MAX_MARKETS_TO_JUDGE", "5"))
    
    # Filtering Criteria
    MIN_LIQUIDITY_USD: float = float(os.getenv("MIN_LIQUIDITY_USD", "1000.0"))
    MIN_VOLUME_24H_USD: float = float(os.getenv("MIN_VOLUME_24H_USD", "500.0"))
    MAX_DAYS_TO_RESOLUTION: int = int(os.getenv("MAX_DAYS_TO_RESOLUTION", "90"))
    MIN_DAYS_TO_RESOLUTION: int = int(os.getenv("MIN_DAYS_TO_RESOLUTION", "1"))
    
    # AI Request Configuration
    CLAUDE_TEMPERATURE: float = float(os.getenv("CLAUDE_TEMPERATURE", "0.3"))
    CLAUDE_MAX_TOKENS: int = int(os.getenv("CLAUDE_MAX_TOKENS", "4096"))
    PERPLEXITY_MAX_TOKENS: int = int(os.getenv("PERPLEXITY_MAX_TOKENS", "4096"))
    PERPLEXITY_TEMPERATURE: float = float(os.getenv("PERPLEXITY_TEMPERATURE", "0.2"))
    
    # Request Timeouts (seconds)
    API_TIMEOUT: int = int(os.getenv("API_TIMEOUT", "30"))
    RESEARCH_TIMEOUT: int = int(os.getenv("RESEARCH_TIMEOUT", "60"))
    
    # Database Configuration
    DB_PATH: Path = Path(os.getenv("DB_PATH", "data/research_bot.db"))
    DB_BACKUP_DIR: Path = Path(os.getenv("DB_BACKUP_DIR", "data/backups"))
    
    # Scheduler Configuration
    SCAN_INTERVAL_HOURS: int = int(os.getenv("SCAN_INTERVAL_HOURS", "6"))
    REPORT_GENERATION_HOUR: int = int(os.getenv("REPORT_GENERATION_HOUR", "8"))
    REPORT_TIMEZONE: str = os.getenv("REPORT_TIMEZONE", "UTC")
    
    # Report Configuration
    REPORT_OUTPUT_DIR: Path = Path(os.getenv("REPORT_OUTPUT_DIR", "reports"))
    MAX_OPPORTUNITIES_IN_REPORT: int = int(os.getenv("MAX_OPPORTUNITIES_IN_REPORT", "10"))
    
    # Telegram Configuration (optional)
    TELEGRAM_BOT_TOKEN: Optional[str] = os.getenv("TELEGRAM_BOT_TOKEN")
    TELEGRAM_CHAT_ID: Optional[str] = os.getenv("TELEGRAM_CHAT_ID")
    
    # Logging Configuration
    LOG_LEVEL: str = os.getenv("LOG_LEVEL", "INFO")
    LOG_FILE: Optional[Path] = Path(os.getenv("LOG_FILE", "logs/bot.log")) if os.getenv("LOG_FILE") else None
    
    @classmethod
    def validate(cls) -> tuple[bool, list[str]]:
        """
        Validate that all required configuration values are present.
        
        Returns:
            tuple: (is_valid, list_of_errors)
        """
        errors: list[str] = []
        
        if not cls.ANTHROPIC_API_KEY:
            errors.append("ANTHROPIC_API_KEY is required but not set")
        
        if not cls.PERPLEXITY_API_KEY:
            errors.append("PERPLEXITY_API_KEY is required but not set")
        
        # Validate numeric ranges
        if cls.MAX_MARKETS_TO_SCAN < 1:
            errors.append("MAX_MARKETS_TO_SCAN must be at least 1")
        
        if cls.MAX_MARKETS_TO_RESEARCH < 1:
            errors.append("MAX_MARKETS_TO_RESEARCH must be at least 1")
        
        if cls.MIN_LIQUIDITY_USD < 0:
            errors.append("MIN_LIQUIDITY_USD cannot be negative")
        
        if cls.MIN_VOLUME_24H_USD < 0:
            errors.append("MIN_VOLUME_24H_USD cannot be negative")
        
        if cls.MAX_DAYS_TO_RESOLUTION < cls.MIN_DAYS_TO_RESOLUTION:
            errors.append("MAX_DAYS_TO_RESOLUTION must be >= MIN_DAYS_TO_RESOLUTION")
        
        if not (0.0 <= cls.CLAUDE_TEMPERATURE <= 1.0):
            errors.append("CLAUDE_TEMPERATURE must be between 0.0 and 1.0")
        
        if not (0.0 <= cls.PERPLEXITY_TEMPERATURE <= 1.0):
            errors.append("PERPLEXITY_TEMPERATURE must be between 0.0 and 1.0")
        
        return (len(errors) == 0, errors)
    
    @classmethod
    def ensure_directories(cls) -> None:
        """
        Ensure all required directories exist.
        
        Creates directories for database, backups, reports, and logs if they don't exist.
        """
        cls.DB_PATH.parent.mkdir(parents=True, exist_ok=True)
        cls.DB_BACKUP_DIR.mkdir(parents=True, exist_ok=True)
        cls.REPORT_OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
        if cls.LOG_FILE:
            cls.LOG_FILE.parent.mkdir(parents=True, exist_ok=True)

