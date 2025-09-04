#!/usr/bin/env python3
"""
Scheduler Service for Checklist Creator
Handles scheduled tasks like VPN server updates
"""

import asyncio
import logging
from datetime import datetime, time
from typing import Dict, Any, Callable, Optional
import signal
import sys
from pathlib import Path

# Import our VyprVPN scraper
from .vyprvpn_scraper import VyprVPNServerScraper

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class TaskScheduler:
    """Manages scheduled tasks for the application"""
    
    def __init__(self):
        self.tasks: Dict[str, Dict[str, Any]] = {}
        self.running = False
        self.vyprvpn_scraper = VyprVPNServerScraper()
        
    def add_task(self, name: str, func: Callable, schedule: str, **kwargs):
        """Add a scheduled task
        
        Args:
            name: Unique name for the task
            func: Function to execute
            schedule: Schedule string (e.g., 'daily', 'hourly', 'custom')
            **kwargs: Additional arguments for the task
        """
        self.tasks[name] = {
            'func': func,
            'schedule': schedule,
            'kwargs': kwargs,
            'last_run': None,
            'next_run': None,
            'enabled': True
        }
        logger.info(f"Added scheduled task: {name} ({schedule})")
    
    def remove_task(self, name: str):
        """Remove a scheduled task"""
        if name in self.tasks:
            del self.tasks[name]
            logger.info(f"Removed scheduled task: {name}")
    
    def enable_task(self, name: str):
        """Enable a scheduled task"""
        if name in self.tasks:
            self.tasks[name]['enabled'] = True
            logger.info(f"Enabled scheduled task: {name}")
    
    def disable_task(self, name: str):
        """Disable a scheduled task"""
        if name in self.tasks:
            self.tasks[name]['enabled'] = False
            logger.info(f"Disabled scheduled task: {name}")
    
    async def run_task(self, name: str, task_info: Dict[str, Any]):
        """Execute a scheduled task"""
        try:
            logger.info(f"Running scheduled task: {name}")
            
            # Update last run time
            task_info['last_run'] = datetime.now()
            
            # Execute the task
            if asyncio.iscoroutinefunction(task_info['func']):
                result = await task_info['func'](**task_info['kwargs'])
            else:
                result = task_info['func'](**task_info['kwargs'])
            
            logger.info(f"Completed scheduled task: {name} - Result: {result}")
            
            # Calculate next run time
            self._calculate_next_run(name, task_info)
            
        except Exception as e:
            logger.error(f"Error running scheduled task {name}: {e}")
            # Calculate next run time even on failure
            self._calculate_next_run(name, task_info)
    
    def _calculate_next_run(self, name: str, task_info: Dict[str, Any]):
        """Calculate when the task should run next"""
        now = datetime.now()
        
        if task_info['schedule'] == 'daily':
            # Run at 2 AM next day
            next_run = now.replace(hour=2, minute=0, second=0, microsecond=0)
            if next_run <= now:
                next_run = next_run.replace(day=next_run.day + 1)
                
        elif task_info['schedule'] == 'hourly':
            # Run at the start of the next hour
            next_run = now.replace(minute=0, second=0, microsecond=0)
            if next_run <= now:
                next_run = next_run.replace(hour=next_run.hour + 1)
                
        elif task_info['schedule'] == 'custom':
            # Custom schedule logic can be implemented here
            next_run = now.replace(hour=now.hour + 1, minute=0, second=0, microsecond=0)
            
        else:
            # Default to daily
            next_run = now.replace(hour=2, minute=0, second=0, microsecond=0)
            if next_run <= now:
                next_run = next_run.replace(day=next_run.day + 1)
        
        task_info['next_run'] = next_run
        logger.debug(f"Task {name} next run scheduled for: {next_run}")
    
    async def check_and_run_tasks(self):
        """Check which tasks need to run and execute them"""
        now = datetime.now()
        tasks_to_run = []
        
        for name, task_info in self.tasks.items():
            if not task_info['enabled']:
                continue
                
            # Initialize next_run if not set
            if task_info['next_run'] is None:
                self._calculate_next_run(name, task_info)
            
            # Check if task should run now
            if task_info['next_run'] and now >= task_info['next_run']:
                tasks_to_run.append((name, task_info))
        
        # Run tasks concurrently
        if tasks_to_run:
            logger.info(f"Running {len(tasks_to_run)} scheduled tasks")
            await asyncio.gather(*[
                self.run_task(name, task_info) 
                for name, task_info in tasks_to_run
            ])
    
    async def start(self):
        """Start the scheduler"""
        logger.info("Starting task scheduler...")
        self.running = True
        
        # Add default tasks
        self._add_default_tasks()
        
        try:
            while self.running:
                # Check and run tasks
                await self.check_and_run_tasks()
                
                # Wait for 1 minute before next check
                await asyncio.sleep(60)
                
        except asyncio.CancelledError:
            logger.info("Scheduler cancelled")
        except Exception as e:
            logger.error(f"Scheduler error: {e}")
        finally:
            self.running = False
            logger.info("Task scheduler stopped")
    
    def stop(self):
        """Stop the scheduler"""
        logger.info("Stopping task scheduler...")
        self.running = False
    
    def _add_default_tasks(self):
        """Add default scheduled tasks"""
        # Add VyprVPN server update task (daily at 2 AM)
        self.add_task(
            name="vyprvpn_server_update",
            func=self._update_vyprvpn_servers,
            schedule="daily",
            description="Update VyprVPN server hostnames from their support page"
        )
        
        logger.info("Added default scheduled tasks")
    
    async def _update_vyprvpn_servers(self, **kwargs):
        """Update VyprVPN server list (called by scheduler)"""
        try:
            logger.info("Running scheduled VyprVPN server update...")
            changes = await self.vyprvpn_scraper.update_server_list()
            
            # Log the changes
            if changes.get('added'):
                logger.info(f"Added {len(changes['added'])} new VyprVPN servers")
            if changes.get('removed'):
                logger.info(f"Removed {len(changes['removed'])} VyprVPN servers")
            if changes.get('modified'):
                logger.info(f"Modified {len(changes['modified'])} VyprVPN servers")
            
            return {
                'status': 'success',
                'changes': changes,
                'timestamp': datetime.now().isoformat()
            }
            
        except Exception as e:
            logger.error(f"Failed to update VyprVPN servers: {e}")
            return {
                'status': 'error',
                'error': str(e),
                'timestamp': datetime.now().isoformat()
            }
    
    def get_task_status(self) -> Dict[str, Any]:
        """Get status of all scheduled tasks"""
        status = {
            'scheduler_running': self.running,
            'total_tasks': len(self.tasks),
            'enabled_tasks': len([t for t in self.tasks.values() if t['enabled']]),
            'tasks': {}
        }
        
        for name, task_info in self.tasks.items():
            status['tasks'][name] = {
                'enabled': task_info['enabled'],
                'schedule': task_info['schedule'],
                'last_run': task_info['last_run'].isoformat() if task_info['last_run'] else None,
                'next_run': task_info['next_run'].isoformat() if task_info['next_run'] else None
            }
        
        return status
    
    def get_vyprvpn_status(self) -> Dict[str, Any]:
        """Get VyprVPN scraper status"""
        try:
            servers = self.vyprvpn_scraper.get_all_servers()
            last_update = self.vyprvpn_scraper.get_last_update_time()
            
            return {
                'total_servers': len(servers),
                'last_update': last_update.isoformat() if last_update else None,
                'regions': list(set(server.region for server in servers)),
                'countries': list(set(server.country for server in servers))
            }
        except Exception as e:
            return {
                'error': str(e),
                'total_servers': 0
            }

# Global scheduler instance
scheduler = TaskScheduler()

# Signal handlers for graceful shutdown
def signal_handler(signum, frame):
    """Handle shutdown signals"""
    logger.info(f"Received signal {signum}, shutting down...")
    scheduler.stop()
    sys.exit(0)

# Register signal handlers
signal.signal(signal.SIGINT, signal_handler)
signal.signal(signal.SIGTERM, signal_handler)

async def start_scheduler():
    """Start the scheduler (for use in main application)"""
    await scheduler.start()

def get_scheduler():
    """Get the global scheduler instance"""
    return scheduler

# Example usage
if __name__ == "__main__":
    async def test_scheduler():
        """Test the scheduler"""
        print("Starting test scheduler...")
        
        # Add a test task
        scheduler.add_task(
            name="test_task",
            func=lambda: print("Test task executed!"),
            schedule="custom"
        )
        
        # Start the scheduler
        await scheduler.start()
    
    # Run the test
    asyncio.run(test_scheduler())
