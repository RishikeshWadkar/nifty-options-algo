
# Missing Component: System Health Monitor
# trading_bot/monitor/health_check.py

import psutil
import time
from datetime import datetime, timedelta
from typing import Dict, Any
from loguru import logger
from trading_bot.alerts.notifier import notifier

class SystemHealthMonitor:
    """
    Monitor system health, performance, and trading metrics.
    """
    
    def __init__(self, config: Dict[str, Any]):
        self.config = config
        self.start_time = datetime.now()
        self.last_check = datetime.now()
        self.alerts_sent = {}  # To prevent spam
        
        # Thresholds
        self.cpu_threshold = 80  # %
        self.memory_threshold = 80  # %
        self.disk_threshold = 90  # %
        self.connection_timeout = 30  # seconds
    
    def check_system_resources(self) -> Dict[str, float]:
        """Check CPU, memory, and disk usage"""
        try:
            cpu_percent = psutil.cpu_percent(interval=1)
            memory = psutil.virtual_memory()
            disk = psutil.disk_usage('/')
            
            metrics = {
                'cpu_percent': cpu_percent,
                'memory_percent': memory.percent,
                'disk_percent': disk.percent,
                'memory_available_gb': memory.available / (1024**3)
            }
            
            # Check thresholds
            if cpu_percent > self.cpu_threshold:
                self.send_alert(f"High CPU usage: {cpu_percent:.1f}%", "WARNING")
            
            if memory.percent > self.memory_threshold:
                self.send_alert(f"High memory usage: {memory.percent:.1f}%", "WARNING")
            
            if disk.percent > self.disk_threshold:
                self.send_alert(f"High disk usage: {disk.percent:.1f}%", "WARNING")
            
            return metrics
            
        except Exception as e:
            logger.error(f"Error checking system resources: {e}")
            return {}
    
    def check_trading_metrics(self, position_manager, database) -> Dict[str, Any]:
        """Check trading-related health metrics"""
        try:
            # Get current trading status
            open_positions = len(position_manager.open_positions)
            
            # Get today's trades from database
            today = datetime.now().date()
            # This would require a method in database to get today's trades
            # trades_today = database.get_trades_for_date(today)
            
            metrics = {
                'open_positions': open_positions,
                'uptime_hours': (datetime.now() - self.start_time).total_seconds() / 3600,
                'last_check': self.last_check.isoformat()
            }
            
            return metrics
            
        except Exception as e:
            logger.error(f"Error checking trading metrics: {e}")
            return {}
    
    def send_alert(self, message: str, priority: str = "INFO"):
        """Send alert with rate limiting to prevent spam"""
        alert_key = f"{message}_{priority}"
        now = datetime.now()
        
        # Rate limiting: don't send same alert more than once per hour
        if alert_key in self.alerts_sent:
            if now - self.alerts_sent[alert_key] < timedelta(hours=1):
                return
        
        self.alerts_sent[alert_key] = now
        notifier.alert(message, priority, telegram=True, email=True)
    
    def run_health_check(self, position_manager=None, database=None):
        """Run complete health check"""
        try:
            self.last_check = datetime.now()
            
            # System resources
            system_metrics = self.check_system_resources()
            
            # Trading metrics
            trading_metrics = {}
            if position_manager and database:
                trading_metrics = self.check_trading_metrics(position_manager, database)
            
            # Log health status
            logger.info(f"Health Check - CPU: {system_metrics.get('cpu_percent', 0):.1f}%, "
                       f"Memory: {system_metrics.get('memory_percent', 0):.1f}%, "
                       f"Positions: {trading_metrics.get('open_positions', 0)}")
            
            return {**system_metrics, **trading_metrics}
            
        except Exception as e:
            logger.error(f"Health check failed: {e}")
            self.send_alert(f"Health check failed: {e}", "ERROR")
            return {}

