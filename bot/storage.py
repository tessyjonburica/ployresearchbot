"""
Storage module for persisting markets, research reports, and decisions.

This module provides a clean repository interface for SQLite database operations.
It handles table creation, insertion, and retrieval with parameterized queries.
"""

import json
import logging
import sqlite3
from datetime import datetime
from pathlib import Path
from typing import Optional, list
from contextlib import contextmanager

from bot.config import Config
from bot.models import Market, Decision
from bot.research_agent import EvidenceDict

# Configure module logger
logger = logging.getLogger(__name__)


class Storage:
    """
    Repository for database operations.
    
    Provides methods for storing and retrieving markets, research reports,
    decisions, and prediction logs. Handles table creation automatically.
    """
    
    def __init__(self, db_path: Optional[Path] = None):
        """
        Initialize storage with database path.
        
        Args:
            db_path: Path to SQLite database file. If None, uses Config.DB_PATH
        """
        self.db_path = db_path or Config.DB_PATH
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._initialize_database()
    
    @contextmanager
    def _get_connection(self):
        """
        Context manager for database connections.
        
        Ensures proper connection handling and transaction management.
        """
        conn = sqlite3.connect(str(self.db_path))
        conn.row_factory = sqlite3.Row  # Enable column access by name
        try:
            yield conn
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()
    
    def _initialize_database(self) -> None:
        """Create database tables if they don't exist."""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            
            # Markets table
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS markets (
                    id TEXT PRIMARY KEY,
                    title TEXT NOT NULL,
                    description TEXT,
                    probability REAL NOT NULL,
                    liquidity REAL NOT NULL,
                    end_date TEXT,
                    slug TEXT,
                    category TEXT,
                    volume_24h REAL DEFAULT 0.0,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                )
            """)
            
            # Research reports table
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS research_reports (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    market_id TEXT NOT NULL,
                    recent_developments TEXT,
                    evidence_yes TEXT,
                    evidence_no TEXT,
                    official_signals TEXT,
                    timeline_constraints TEXT,
                    source_quality TEXT,
                    created_at TEXT NOT NULL,
                    FOREIGN KEY (market_id) REFERENCES markets(id)
                )
            """)
            
            # Decisions table
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS decisions (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    market_id TEXT NOT NULL,
                    estimated_probability REAL NOT NULL,
                    confidence_level REAL NOT NULL,
                    edge REAL NOT NULL,
                    decision TEXT NOT NULL,
                    key_risks TEXT,
                    reasoning_summary TEXT,
                    created_at TEXT NOT NULL,
                    FOREIGN KEY (market_id) REFERENCES markets(id)
                )
            """)
            
            # Predictions log table (for tracking predictions over time)
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS predictions_log (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    market_id TEXT NOT NULL,
                    market_probability REAL NOT NULL,
                    estimated_probability REAL NOT NULL,
                    confidence_level REAL NOT NULL,
                    edge REAL NOT NULL,
                    decision TEXT NOT NULL,
                    logged_at TEXT NOT NULL,
                    FOREIGN KEY (market_id) REFERENCES markets(id)
                )
            """)
            
            # Create indexes for common queries
            cursor.execute("""
                CREATE INDEX IF NOT EXISTS idx_markets_category 
                ON markets(category)
            """)
            
            cursor.execute("""
                CREATE INDEX IF NOT EXISTS idx_markets_end_date 
                ON markets(end_date)
            """)
            
            cursor.execute("""
                CREATE INDEX IF NOT EXISTS idx_research_market_id 
                ON research_reports(market_id)
            """)
            
            cursor.execute("""
                CREATE INDEX IF NOT EXISTS idx_decisions_market_id 
                ON decisions(market_id)
            """)
            
            cursor.execute("""
                CREATE INDEX IF NOT EXISTS idx_decisions_created_at 
                ON decisions(created_at)
            """)
            
            cursor.execute("""
                CREATE INDEX IF NOT EXISTS idx_predictions_market_id 
                ON predictions_log(market_id)
            """)
            
            conn.commit()
            logger.info(f"Database initialized at {self.db_path}")
    
    # Market operations
    
    def save_market(self, market: Market) -> bool:
        """
        Save or update a market in the database.
        
        Args:
            market: Market object to save
        
        Returns:
            True if successful, False otherwise
        """
        try:
            now = datetime.utcnow().isoformat()
            
            with self._get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute("""
                    INSERT OR REPLACE INTO markets 
                    (id, title, description, probability, liquidity, end_date,
                     slug, category, volume_24h, created_at, updated_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 
                            COALESCE((SELECT created_at FROM markets WHERE id = ?), ?),
                            ?)
                """, (
                    market.id,
                    market.title,
                    market.description,
                    market.probability,
                    market.liquidity,
                    market.end_date.isoformat() if market.end_date else None,
                    market.slug,
                    market.category,
                    market.volume_24h,
                    market.id,  # For COALESCE check
                    now,  # Default created_at if new
                    now   # updated_at
                ))
            
            logger.debug(f"Saved market: {market.id}")
            return True
        
        except Exception as e:
            logger.error(f"Error saving market {market.id}: {e}", exc_info=True)
            return False
    
    def get_market(self, market_id: str) -> Optional[Market]:
        """
        Retrieve a market by ID.
        
        Args:
            market_id: Market identifier
        
        Returns:
            Market object if found, None otherwise
        """
        try:
            with self._get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute("""
                    SELECT * FROM markets WHERE id = ?
                """, (market_id,))
                
                row = cursor.fetchone()
                if not row:
                    return None
                
                return self._row_to_market(row)
        
        except Exception as e:
            logger.error(f"Error retrieving market {market_id}: {e}", exc_info=True)
            return None
    
    def get_all_markets(self, limit: Optional[int] = None) -> list[Market]:
        """
        Retrieve all markets.
        
        Args:
            limit: Maximum number of markets to return
        
        Returns:
            List of Market objects
        """
        try:
            with self._get_connection() as conn:
                cursor = conn.cursor()
                query = "SELECT * FROM markets ORDER BY updated_at DESC"
                if limit and isinstance(limit, int) and limit > 0:
                    query += f" LIMIT {int(limit)}"
                
                cursor.execute(query)
                rows = cursor.fetchall()
                
                return [self._row_to_market(row) for row in rows]
        
        except Exception as e:
            logger.error(f"Error retrieving markets: {e}", exc_info=True)
            return []
    
    def _row_to_market(self, row: sqlite3.Row) -> Market:
        """Convert database row to Market object."""
        end_date = None
        if row["end_date"]:
            try:
                end_date = datetime.fromisoformat(row["end_date"])
            except ValueError:
                pass
        
        return Market(
            id=row["id"],
            title=row["title"],
            description=row["description"] or "",
            probability=row["probability"],
            liquidity=row["liquidity"],
            end_date=end_date,
            slug=row["slug"] or "",
            category=row["category"] or "",
            volume_24h=row["volume_24h"] or 0.0
        )
    
    # Research report operations
    
    def save_research_report(self, market_id: str, evidence: EvidenceDict) -> bool:
        """
        Save a research report for a market.
        
        Args:
            market_id: Market identifier
            evidence: Evidence dictionary from research agent
        
        Returns:
            True if successful, False otherwise
        """
        try:
            now = datetime.utcnow().isoformat()
            
            with self._get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute("""
                    INSERT INTO research_reports
                    (market_id, recent_developments, evidence_yes, evidence_no,
                     official_signals, timeline_constraints, source_quality, created_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """, (
                    market_id,
                    json.dumps(evidence.get("recent_developments", [])),
                    json.dumps(evidence.get("evidence_yes", [])),
                    json.dumps(evidence.get("evidence_no", [])),
                    json.dumps(evidence.get("official_signals", [])),
                    json.dumps(evidence.get("timeline_constraints", [])),
                    evidence.get("source_quality", "unknown"),
                    now
                ))
            
            logger.debug(f"Saved research report for market: {market_id}")
            return True
        
        except Exception as e:
            logger.error(f"Error saving research report for {market_id}: {e}", exc_info=True)
            return False
    
    def get_latest_research_report(self, market_id: str) -> Optional[EvidenceDict]:
        """
        Retrieve the latest research report for a market.
        
        Args:
            market_id: Market identifier
        
        Returns:
            EvidenceDict if found, None otherwise
        """
        try:
            with self._get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute("""
                    SELECT * FROM research_reports
                    WHERE market_id = ?
                    ORDER BY created_at DESC
                    LIMIT 1
                """, (market_id,))
                
                row = cursor.fetchone()
                if not row:
                    return None
                
                return {
                    "recent_developments": json.loads(row["recent_developments"] or "[]"),
                    "evidence_yes": json.loads(row["evidence_yes"] or "[]"),
                    "evidence_no": json.loads(row["evidence_no"] or "[]"),
                    "official_signals": json.loads(row["official_signals"] or "[]"),
                    "timeline_constraints": json.loads(row["timeline_constraints"] or "[]"),
                    "source_quality": row["source_quality"] or "unknown"
                }
        
        except Exception as e:
            logger.error(f"Error retrieving research report for {market_id}: {e}", exc_info=True)
            return None
    
    # Decision operations
    
    def save_decision(self, decision: Decision) -> bool:
        """
        Save a decision for a market.
        
        Args:
            decision: Decision object to save
        
        Returns:
            True if successful, False otherwise
        """
        try:
            with self._get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute("""
                    INSERT INTO decisions
                    (market_id, estimated_probability, confidence_level, edge,
                     decision, key_risks, reasoning_summary, created_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """, (
                    decision.market_id,
                    decision.estimated_probability,
                    decision.confidence_level,
                    decision.edge,
                    decision.decision,
                    json.dumps(decision.key_risks),
                    decision.reasoning_summary,
                    decision.created_at.isoformat()
                ))
            
            logger.debug(f"Saved decision for market: {decision.market_id}")
            return True
        
        except Exception as e:
            logger.error(f"Error saving decision for {decision.market_id}: {e}", exc_info=True)
            return False
    
    def get_latest_decision(self, market_id: str) -> Optional[Decision]:
        """
        Retrieve the latest decision for a market.
        
        Args:
            market_id: Market identifier
        
        Returns:
            Decision object if found, None otherwise
        """
        try:
            with self._get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute("""
                    SELECT * FROM decisions
                    WHERE market_id = ?
                    ORDER BY created_at DESC
                    LIMIT 1
                """, (market_id,))
                
                row = cursor.fetchone()
                if not row:
                    return None
                
                return Decision(
                    market_id=row["market_id"],
                    estimated_probability=row["estimated_probability"],
                    confidence_level=row["confidence_level"],
                    edge=row["edge"],
                    decision=row["decision"],
                    key_risks=json.loads(row["key_risks"] or "[]"),
                    reasoning_summary=row["reasoning_summary"] or "",
                    created_at=datetime.fromisoformat(row["created_at"])
                )
        
        except Exception as e:
            logger.error(f"Error retrieving decision for {market_id}: {e}", exc_info=True)
            return None
    
    def get_decisions_by_edge(self, min_edge: float, limit: Optional[int] = None) -> list[Decision]:
        """
        Retrieve decisions with edge above threshold.
        
        Args:
            min_edge: Minimum edge threshold
            limit: Maximum number of decisions to return
        
        Returns:
            List of Decision objects sorted by edge descending
        """
        try:
            with self._get_connection() as conn:
                cursor = conn.cursor()
                query = """
                    SELECT * FROM decisions
                    WHERE ABS(edge) >= ?
                    ORDER BY ABS(edge) DESC
                """
                if limit and isinstance(limit, int) and limit > 0:
                    query += f" LIMIT {int(limit)}"
                
                cursor.execute(query, (min_edge,))
                rows = cursor.fetchall()
                
                decisions = []
                for row in rows:
                    try:
                        decisions.append(Decision(
                            market_id=row["market_id"],
                            estimated_probability=row["estimated_probability"],
                            confidence_level=row["confidence_level"],
                            edge=row["edge"],
                            decision=row["decision"],
                            key_risks=json.loads(row["key_risks"] or "[]"),
                            reasoning_summary=row["reasoning_summary"] or "",
                            created_at=datetime.fromisoformat(row["created_at"])
                        ))
                    except Exception as e:
                        logger.warning(f"Error parsing decision row: {e}")
                        continue
                
                return decisions
        
        except Exception as e:
            logger.error(f"Error retrieving decisions by edge: {e}", exc_info=True)
            return []
    
    # Prediction log operations
    
    def log_prediction(
        self,
        market_id: str,
        market_probability: float,
        estimated_probability: float,
        confidence_level: float,
        edge: float,
        decision: str
    ) -> bool:
        """
        Log a prediction to the predictions log.
        
        Args:
            market_id: Market identifier
            market_probability: Current market probability
            estimated_probability: Estimated true probability
            confidence_level: Confidence in estimate
            edge: Calculated edge
            decision: Decision recommendation
        
        Returns:
            True if successful, False otherwise
        """
        try:
            now = datetime.utcnow().isoformat()
            
            with self._get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute("""
                    INSERT INTO predictions_log
                    (market_id, market_probability, estimated_probability,
                     confidence_level, edge, decision, logged_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?)
                """, (
                    market_id,
                    market_probability,
                    estimated_probability,
                    confidence_level,
                    edge,
                    decision,
                    now
                ))
            
            logger.debug(f"Logged prediction for market: {market_id}")
            return True
        
        except Exception as e:
            logger.error(f"Error logging prediction for {market_id}: {e}", exc_info=True)
            return False
    
    def get_prediction_history(self, market_id: str, limit: Optional[int] = None) -> list[dict]:
        """
        Retrieve prediction history for a market.
        
        Args:
            market_id: Market identifier
            limit: Maximum number of predictions to return
        
        Returns:
            List of prediction dictionaries
        """
        try:
            with self._get_connection() as conn:
                cursor = conn.cursor()
                query = """
                    SELECT * FROM predictions_log
                    WHERE market_id = ?
                    ORDER BY logged_at DESC
                """
                if limit and isinstance(limit, int) and limit > 0:
                    query += f" LIMIT {int(limit)}"
                
                cursor.execute(query, (market_id,))
                rows = cursor.fetchall()
                
                return [
                    {
                        "market_id": row["market_id"],
                        "market_probability": row["market_probability"],
                        "estimated_probability": row["estimated_probability"],
                        "confidence_level": row["confidence_level"],
                        "edge": row["edge"],
                        "decision": row["decision"],
                        "logged_at": row["logged_at"]
                    }
                    for row in rows
                ]
        
        except Exception as e:
            logger.error(f"Error retrieving prediction history for {market_id}: {e}", exc_info=True)
            return []

