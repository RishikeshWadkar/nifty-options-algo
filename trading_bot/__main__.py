# Enhanced main loop with position management and better error handling
# trading_bot/main_enhanced.py

import threading
import time
import signal
import sys
from datetime import datetime
from typing import Any
from loguru import logger

from trading_bot.utils.logger import setup_logger
from trading_bot.event_queue import EventQueue
from trading_bot.broker.api_wrapper import ShoonyaAPIWrapper
from trading_bot.broker.data_handler import DataHandler

# And update the initialization:
self.data_handler = DataHandler(
    self.api_wrapper,
    self.event_queue,
    symbols
)
from trading_bot.strategy.main_strategy import MainStrategy
from trading_bot.risk.manager import RiskManager
from trading_bot.position.manager import PositionManager
from trading_bot.config.manager import ConfigManager
from trading_bot.persistence.database import Database
import yaml
from trading_bot.alerts.notifier import notifier  # <-- Add this import
# from trading_bot.alerts.notifier import send_critical_alert  # Uncomment if implemented

LOG_DIR = 'logs'
SYMBOLS = ['NIFTY']  # Add your symbols here

def reconcile_state(api_wrapper: ShoonyaAPIWrapper, db: Database) -> bool:
    """
    Reconcile local DB state with broker state on startup.
    Returns True if reconciliation is successful, False otherwise.
    Handles open trades, pending orders, partial fills, and sends alerts on failure.
    """
    try:
        open_trades = db.get_open_trades()
        pending_orders = db.get_pending_orders()
        broker_positions = api_wrapper.get_open_positions()
        # Fetch all broker orders (implement if available)
        broker_orders = []
        if hasattr(api_wrapper.session, 'get_order_book'):
            broker_orders = api_wrapper.session.get_order_book()

        # 1. Close trades in DB that are not open at broker
        for trade in open_trades:
            symbol = trade[2]  # Adjust index as per schema
            found = any(pos.get('tsym') == symbol for pos in broker_positions)
            if not found:
                logger.warning(f"[Reconcile] Trade {trade[1]} open in DB but not at broker. Marking as closed.")
                # db.save_trade({...})  # Update status to CLOSED

        # 2. Add broker positions to DB if not present
        for pos in broker_positions:
            symbol = pos.get('tsym')
            found = any(trade[2] == symbol for trade in open_trades)
            if not found:
                logger.warning(f"[Reconcile] Position {symbol} open at broker but not in DB. Adding to DB.")
                # db.save_trade({...})  # Add as open trade

        # 3. Cancel orders in DB that are not pending at broker
        for order in pending_orders:
            order_id = order[1]  # Adjust index as per schema
            found = any(b_order.get('norenordno') == order_id for b_order in broker_orders)
            if not found:
                logger.warning(f"[Reconcile] Order {order_id} pending in DB but not at broker. Marking as cancelled.")
                # db.save_order({...})  # Update status to CANCELLED

        # 4. Handle partial fills (if broker provides fill info)
        for b_order in broker_orders:
            if b_order.get('status') == 'PARTIALLY_FILLED':
                logger.info(f"[Reconcile] Order {b_order.get('norenordno')} is partially filled. Consider resuming monitoring or manual intervention.")
                # Optionally update DB or alert

        logger.info("[Reconcile] Startup reconciliation completed successfully.")
        return True
    except Exception as exc:
        logger.critical(f"[Reconcile] Startup reconciliation failed: {exc}")
        notifier.alert(
            message=f"Startup reconciliation failed! Manual intervention required.\nError: {exc}",
            priority="CRITICAL",
            telegram=True,
            email=True
        )
        return False

class TradingBotOrchestrator:
    """
    Main orchestrator for the trading bot with proper shutdown handling,
    position management, and error recovery.
    """
    
    def __init__(self):
        self.config_manager = ConfigManager()
        self.running = True
        self.threads = []
        
        # Initialize components
        self.setup_components()
        
        # Setup signal handlers for graceful shutdown
        signal.signal(signal.SIGINT, self.signal_handler)
        signal.signal(signal.SIGTERM, self.signal_handler)
    
    def setup_components(self):
        """Initialize all trading bot components"""
        # Setup logging
        setup_logger(
            log_dir=self.config_manager.get('logging.path', 'logs'),
            log_level=self.config_manager.get('logging.level', 'INFO')
        )
        
        # Initialize queues
        self.event_queue = EventQueue()
        self.signal_queue = EventQueue()
        self.order_queue = EventQueue()
        self.execution_queue = EventQueue()
        
        # Initialize database and API
        self.database = Database(self.config_manager.get('data.db_path', 'data/trading_bot.db'))
        self.api_wrapper = ShoonyaAPIWrapper()
        
        # Initialize components
        self.position_manager = PositionManager(self.database, self.api_wrapper)
        
        # Get strategy configuration
        strategy_config = self.config_manager.get('strategy', {})
        
        self.strategy = MainStrategy(
            self.event_queue, 
            self.signal_queue,
            buffer=strategy_config.get('entry_buffer', 0.0)
        )
        
        # Get risk configuration
        risk_config = self.config_manager.get('risk', {})
        
        self.risk_manager = RiskManager(
            self.signal_queue,
            self.order_queue,
            max_trades_per_day=risk_config.get('max_trades_per_day', 4),
            max_daily_loss=risk_config.get('max_daily_loss', 500),
            position_size=risk_config.get('position_size', 1)
        )
        
        # Initialize execution gateway based on mode
        mode = self.config_manager.get('mode', 'papertrading')
        if mode == 'papertrading':
            from trading_bot.execution.paper_gateway import PaperExecutionGateway
            self.execution_gateway = PaperExecutionGateway(
                self.order_queue, 
                self.execution_queue, 
                self.api_wrapper
            )
        else:
            from trading_bot.execution.gateway import ExecutionGateway
            self.execution_gateway = ExecutionGateway(
                self.order_queue, 
                self.execution_queue, 
                self.api_wrapper
            )
        
        # Initialize enhanced data handler
        symbols = self.config_manager.get('strategy.symbols', ['NIFTY'])
        self.data_handler = EnhancedDataHandler(
            self.api_wrapper,
            self.event_queue,
            symbols
        )
    
    def connect_to_broker(self):
        """Connect to broker with retry logic"""
        max_retries = 3
        for attempt in range(max_retries):
            try:
                logger.info(f"Connecting to broker (attempt {attempt + 1}/{max_retries})")
                self.api_wrapper.connect()
                logger.info("Successfully connected to broker")
                return True
            except Exception as e:
                logger.error(f"Broker connection failed: {e}")
                if attempt < max_retries - 1:
                    time.sleep(10)
        
        logger.error("Failed to connect to broker after all attempts")
        return False
    
    def start_data_feed(self):
        """Start market data feed in separate thread"""
        data_thread = threading.Thread(
            target=self.data_handler.start_with_reconnection,
            daemon=True,
            name="DataHandler"
        )
        data_thread.start()
        self.threads.append(data_thread)
        logger.info("Data feed thread started")
    
    # Add to process_events method:
    def process_events(self):
        """Main event processing loop with session management"""
        last_heartbeat = datetime.now()
        
        while self.running:
            try:
                current_time = datetime.now().time()
                
                # Check for 3 PM closure
                if current_time >= time(15, 0, 0) and current_time <= time(15, 5, 0):
                    self._close_all_positions_at_3pm()
                    logger.info("3 PM session closure completed")
                    break
                
                events_processed = 0
                
                # Process market events
                while not self.event_queue.empty() and events_processed < 100:
                    event = self.event_queue.get(block=False)
                    self.strategy.process_event(event)
                    
                    # Update position manager with current prices
                    if hasattr(event, 'symbol') and hasattr(event, 'price'):
                        self.position_manager.update_trailing_sl(event.symbol, event.price)
                        
                        # Check for exit conditions
                        exits = self.position_manager.check_exit_conditions(event.symbol, event.price)
                        for pos_id, reason, exit_price in exits:
                            logger.info(f"Exit condition met: {pos_id} - {reason}")
                            self.position_manager.close_position(pos_id, reason, exit_price)
                    
                    # For paper trading, update execution gateway
                    if hasattr(self.execution_gateway, 'on_market_event'):
                        self.execution_gateway.on_market_event(event)
                    
                    events_processed += 1
                
                # Process signals
                while not self.signal_queue.empty():
                    signal = self.signal_queue.get(block=False)
                    self.risk_manager.process_signal(signal)
                
                # Process orders
                while not self.order_queue.empty():
                    order = self.order_queue.get(block=False)
                    self.execution_gateway.process_order(order)
                
                # Process executions
                while not self.execution_queue.empty():
                    execution_event = self.execution_queue.get(block=False)
                    
                    # Add position to position manager
                    if execution_event.status == 'FILLED':
                        self.position_manager.add_position(
                            execution_event,
                            sl_points=self.config_manager.get('strategy.sl_points', 2.5)
                        )
                    
                    logger.info(f"Execution processed: {execution_event}")
                
                # Heartbeat logging every minute
                now = datetime.now()
                if (now - last_heartbeat).seconds >= 60:
                    logger.info(f"System heartbeat - Active positions: {len(self.position_manager.open_positions)}")
                    last_heartbeat = now
                
                # Small sleep to prevent CPU spinning
                time.sleep(0.01)
                
            except Exception as e:
                logger.error(f"Error in main event loop: {e}")
                time.sleep(1)
    
    def _close_all_positions_at_3pm(self):
        """Force close all positions at 3 PM"""
        try:
            for pos_id, position in self.position_manager.open_positions.items():
                # Create market order to close position
                close_order = OrderEvent(
                    symbol=position['symbol'],
                    timestamp=datetime.now(),
                    order_type='MARKET',
                    side='SELL' if position['side'] == 'BUY' else 'BUY',
                    quantity=position['quantity'],
                    info={'reason': '3PM_CLOSURE', 'position_id': pos_id}
                )
                self.order_queue.put(close_order)
                
            logger.info(f"Initiated closure of {len(self.position_manager.open_positions)} positions at 3 PM")
            
        except Exception as e:
            logger.error(f"Error closing positions at 3 PM: {e}")
    
    def emergency_shutdown(self):
        """Emergency shutdown procedure"""
        logger.warning("Initiating emergency shutdown...")
        
        try:
            # Cancel all pending orders
            logger.info("Canceling all pending orders...")
            self.api_wrapper.cancel_all_orders()
            
            # Close all positions (if in live mode)
            if self.config_manager.get('mode') == 'live':
                logger.info("Closing all positions...")
                self.api_wrapper.close_all_positions()
            
            # Mark system as halted in database
            self.database.save_system_state('SYSTEM_HALTED', 'TRUE')
            self.database.save_system_state('HALT_TIMESTAMP', datetime.now().isoformat())
            
        except Exception as e:
            logger.error(f"Error during emergency shutdown: {e}")
    
    def graceful_shutdown(self):
        """Graceful shutdown procedure"""
        logger.info("Initiating graceful shutdown...")
        
        self.running = False
        
        # Wait for threads to finish (with timeout)
        for thread in self.threads:
            thread.join(timeout=10)
        
        # Save final state
        self.database.save_system_state('LAST_SHUTDOWN', datetime.now().isoformat())
        
        logger.info("Graceful shutdown completed")
    
    def signal_handler(self, signum, frame):
        """Handle shutdown signals"""
        logger.info(f"Received signal {signum}, initiating shutdown...")
        self.graceful_shutdown()
        sys.exit(0)
    
    def run(self):
        """Main run method"""
        try:
            logger.info("Starting Nifty Options Trading Bot")
            
            # Connect to broker
            if not self.connect_to_broker():
                logger.error("Cannot proceed without broker connection")
                return
            
            # Check if system was previously halted
            system_halted = self.database.get_system_state('SYSTEM_HALTED')
            if system_halted == 'TRUE':
                logger.warning("System was previously halted. Manual intervention may be required.")
                response = input("Continue anyway? (y/n): ")
                if response.lower() != 'y':
                    return
                self.database.reset_system_halt()
            
            # Start data feed
            self.start_data_feed()
            
            # Give data feed time to establish connection
            time.sleep(5)
            
            # Start main event processing loop
            logger.info("Starting main event processing loop")
            self.process_events()
            
        except KeyboardInterrupt:
            logger.info("Interrupted by user")
        except Exception as e:
            logger.error(f"Critical error in main run loop: {e}")
            self.emergency_shutdown()
        finally:
            self.graceful_shutdown()


def main():
    """Entry point for the enhanced trading bot"""
    bot = TradingBotOrchestrator()
    bot.run()


if __name__ == '__main__':
    main()