"""
Scheduler module for automated pipeline execution.

This module provides scheduling functionality using APScheduler to run the
research pipeline at configurable intervals. It handles execution safety,
overlap prevention, and graceful shutdown.
"""

import logging
import threading
from typing import Callable, Optional
from datetime import datetime

from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.interval import IntervalTrigger
from apscheduler.events import EVENT_JOB_EXECUTED, EVENT_JOB_ERROR
import pytz

from bot.config import Config

# Configure module logger
logger = logging.getLogger(__name__)


class Scheduler:
    """
    Scheduler for automated pipeline execution.
    
    Manages scheduled execution of the research pipeline with overlap prevention,
    error handling, and graceful shutdown support.
    """
    
    def __init__(self):
        """Initialize the scheduler."""
        self.scheduler: Optional[BackgroundScheduler] = None
        self.pipeline_function: Optional[Callable] = None
        self.is_running = False
        self._execution_lock = threading.Lock()
        self._job_id = "pipeline_job"
    
    def start(
        self,
        pipeline_function: Callable,
        interval_hours: Optional[int] = None
    ) -> bool:
        """
        Start the scheduler with the given pipeline function.
        
        Args:
            pipeline_function: Callable that executes the research pipeline
            interval_hours: Hours between pipeline runs. If None, uses Config.SCAN_INTERVAL_HOURS
        
        Returns:
            True if scheduler started successfully, False otherwise
        """
        if self.is_running:
            logger.warning("Scheduler is already running")
            return False
        
        if not callable(pipeline_function):
            logger.error("pipeline_function must be callable")
            return False
        
        self.pipeline_function = pipeline_function
        
        # Use config interval if not provided
        if interval_hours is None:
            interval_hours = Config.SCAN_INTERVAL_HOURS
        
        if interval_hours < 1:
            logger.error(f"Invalid interval_hours: {interval_hours}. Must be >= 1")
            return False
        
        try:
            # Create scheduler with timezone support
            timezone = pytz.timezone(Config.REPORT_TIMEZONE)
            self.scheduler = BackgroundScheduler(timezone=timezone)
            
            # Add event listeners for monitoring
            self.scheduler.add_listener(
                self._on_job_executed,
                EVENT_JOB_EXECUTED | EVENT_JOB_ERROR
            )
            
            # Schedule the pipeline job
            trigger = IntervalTrigger(hours=interval_hours)
            self.scheduler.add_job(
                func=self._safe_execute_pipeline,
                trigger=trigger,
                id=self._job_id,
                name="Research Pipeline",
                replace_existing=True,
                max_instances=1  # Prevent overlapping runs
            )
            
            # Start the scheduler
            self.scheduler.start()
            self.is_running = True
            
            logger.info(f"Scheduler started with {interval_hours} hour interval")
            logger.info(f"Next pipeline run scheduled in {interval_hours} hours")
            
            return True
        
        except Exception as e:
            logger.error(f"Failed to start scheduler: {e}", exc_info=True)
            self.is_running = False
            return False
    
    def stop(self, wait: bool = True) -> bool:
        """
        Stop the scheduler gracefully.
        
        Args:
            wait: Whether to wait for running jobs to complete
        
        Returns:
            True if scheduler stopped successfully, False otherwise
        """
        if not self.is_running or not self.scheduler:
            logger.warning("Scheduler is not running")
            return False
        
        try:
            logger.info("Stopping scheduler...")
            
            # Shutdown scheduler
            self.scheduler.shutdown(wait=wait)
            
            self.is_running = False
            self.scheduler = None
            
            logger.info("Scheduler stopped successfully")
            return True
        
        except Exception as e:
            logger.error(f"Error stopping scheduler: {e}", exc_info=True)
            return False
    
    def _safe_execute_pipeline(self) -> None:
        """
        Safely execute the pipeline function with overlap prevention.
        
        This method wraps the pipeline execution with error handling,
        logging, and overlap prevention using a lock.
        """
        # Check if already running (double-check with lock)
        if not self._execution_lock.acquire(blocking=False):
            logger.warning("Pipeline execution skipped: previous run still in progress")
            return
        
        start_time = datetime.utcnow()
        
        try:
            logger.info("=" * 80)
            logger.info("Scheduled pipeline execution started")
            logger.info(f"Start time: {start_time.isoformat()}")
            logger.info("=" * 80)
            
            if not self.pipeline_function:
                logger.error("Pipeline function not set")
                return
            
            # Execute pipeline
            result = self.pipeline_function()
            
            end_time = datetime.utcnow()
            duration = (end_time - start_time).total_seconds()
            
            if result is not None:
                logger.info(f"Pipeline execution completed successfully")
                logger.info(f"Found {len(result)} opportunities")
            else:
                logger.warning("Pipeline execution completed with no opportunities")
            
            logger.info(f"Duration: {duration:.2f} seconds")
            logger.info("=" * 80)
        
        except KeyboardInterrupt:
            end_time = datetime.utcnow()
            duration = (end_time - start_time).total_seconds()
            logger.warning(f"Pipeline execution interrupted by user after {duration:.2f} seconds")
            raise  # Re-raise to allow scheduler to handle it
        
        except Exception as e:
            end_time = datetime.utcnow()
            duration = (end_time - start_time).total_seconds()
            
            logger.error(f"Pipeline execution failed after {duration:.2f} seconds")
            logger.error(f"Error: {e}", exc_info=True)
            logger.info("=" * 80)
        
        finally:
            # Always release the lock
            self._execution_lock.release()
    
    def _on_job_executed(self, event) -> None:
        """
        Event listener for job execution events.
        
        Logs job execution status for monitoring.
        
        Args:
            event: APScheduler event object
        """
        if event.exception:
            logger.error(f"Job {event.job_id} raised an exception: {event.exception}")
        else:
            logger.debug(f"Job {event.job_id} executed successfully")
    
    def get_next_run_time(self) -> Optional[datetime]:
        """
        Get the next scheduled run time.
        
        Returns:
            Next run time as datetime, or None if scheduler is not running
        """
        if not self.is_running or not self.scheduler:
            return None
        
        try:
            job = self.scheduler.get_job(self._job_id)
            if job:
                return job.next_run_time
            return None
        except Exception as e:
            logger.error(f"Error getting next run time: {e}")
            return None
    
    def is_job_running(self) -> bool:
        """
        Check if a pipeline job is currently running.
        
        Returns:
            True if job is running, False otherwise
        """
        return not self._execution_lock.acquire(blocking=False)
    
    def get_status(self) -> dict:
        """
        Get current scheduler status.
        
        Returns:
            Dictionary with scheduler status information
        """
        status = {
            "is_running": self.is_running,
            "has_pipeline_function": self.pipeline_function is not None,
            "job_running": self.is_job_running(),
            "next_run_time": None,
            "interval_hours": Config.SCAN_INTERVAL_HOURS if self.is_running else None
        }
        
        if self.is_running:
            next_run = self.get_next_run_time()
            if next_run:
                status["next_run_time"] = next_run.isoformat()
        
        return status


# Global scheduler instance
_scheduler_instance: Optional[Scheduler] = None


def start_scheduler(
    run_pipeline_callable: Callable,
    interval_hours: Optional[int] = None
) -> bool:
    """
    Start the global scheduler instance.
    
    Convenience function to start the scheduler with a pipeline function.
    
    Args:
        run_pipeline_callable: Callable that executes the research pipeline
        interval_hours: Hours between pipeline runs. If None, uses Config.SCAN_INTERVAL_HOURS
    
    Returns:
        True if scheduler started successfully, False otherwise
    """
    global _scheduler_instance
    
    if _scheduler_instance is None:
        _scheduler_instance = Scheduler()
    
    return _scheduler_instance.start(run_pipeline_callable, interval_hours)


def stop_scheduler(wait: bool = True) -> bool:
    """
    Stop the global scheduler instance.
    
    Convenience function to stop the scheduler gracefully.
    
    Args:
        wait: Whether to wait for running jobs to complete
    
    Returns:
        True if scheduler stopped successfully, False otherwise
    """
    global _scheduler_instance
    
    if _scheduler_instance is None:
        logger.warning("Scheduler instance does not exist")
        return False
    
    return _scheduler_instance.stop(wait)


def get_scheduler() -> Optional[Scheduler]:
    """
    Get the global scheduler instance.
    
    Returns:
        Scheduler instance, or None if not initialized
    """
    return _scheduler_instance


def get_scheduler_status() -> dict:
    """
    Get status of the global scheduler instance.
    
    Returns:
        Dictionary with scheduler status information
    """
    if _scheduler_instance is None:
        return {
            "is_running": False,
            "has_pipeline_function": False,
            "job_running": False,
            "next_run_time": None,
            "interval_hours": None
        }
    
    return _scheduler_instance.get_status()

