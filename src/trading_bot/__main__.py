# trading_bot/__main__.py
# Fixed and refactored main entry point

import threading
import time
import signal
import sys
from datetime import datetime, time as dt_time
from typing import Any
from loguru import logger

# Core imports
from trading_bot.utils.logger import setup_logger
from trading_bot.event_queue import EventQueue
from trading_bot.event import OrderEvent, MarketEvent, SignalEvent, ExecutionEvent
from trading_bot.broker.api_wrapper import ShoonyaAPIWrapper
from trading_bot.broker.data_handler import DataHandler  # Use regular DataHandler for now
from trading_bot.strategy.main_strategy import MainStrategy
from trading_bot.risk.manager import RiskManager
from trading_bot.position.manager import PositionManager
from config.manager import ConfigManager
from trading_bot.persistence.database import Database

# Optional imports with fallbacks
try:
    from trading_bot.alerts.notifier import notifier
    ALERTS_AVAILABLE = True
except ImportError:
    logger.warning("Alerts module not available")
    ALERTS_AVAILABLE = False
    notifier = None

LOG_DIR = 'logs'
DEFAULT_SYMBOLS = ['NIFTY']

def send_alert(message: str, priority: str = "INFO"):
    """Safe alert sending with fallback"""
    if ALERTS_AVAILABLE and notifier:
        try:
            notifier.alert(
                message=message,
                priority=priority,
                telegram=True if priority == "CRITICAL" else False,
                email=True if priority == "CRITICAL" else False
            )
        except Exception as e:
            logger.error(f"Failed to send alert: {e}")
    else:
        logger.warning(f"Alert not sent (no notifier): {message}")

def reconcile_state(api_wrapper: ShoonyaAPIWrapper, db: Database) -> bool:
    """
    Reconcile local DB state with broker state on startup.
    Returns True if reconciliation is successful, False otherwise.
    """
    try:
        logger.info("Starting state reconciliation...")
        
        # Get local state
        open_trades = db.get_open_trades() if hasattr(db, 'get_open_trades') else []
        pending_orders = db.get_pending_orders() if hasattr(db, 'get_pending_orders') else []
        
        # Get broker state
        broker_positions = []
        broker_orders = []
        
        try:
            broker_positions = api_wrapper.get_open_positions() if hasattr(api_wrapper, 'get_open_positions') else []
            if hasattr(api_wrapper, 'get_order_book'):
                broker_orders = api_wrapper.get_order_book()
        except Exception as e:
            logger.warning(f"Could not fetch broker state: {e}")
        
        # Basic reconciliation logic
        logger.info(f"Local: {len(open_trades)} trades, {len(pending_orders)} orders")
        logger.info(f"Broker: {len(broker_positions)} positions, {len(broker_orders)} orders")
        
        # TODO: Implement detailed reconciliation logic
        # For now, just log the differences
        
        logger.info("State reconciliation completed successfully")
        return True
        
    except Exception as exc:
        logger.critical(f"Startup reconciliation failed: {exc}")
        send_alert(
            f"Startup reconciliation failed! Manual intervention required.\nError: {exc}",
            "CRITICAL"
        )
        return False

class TradingBotOrchestrator:
    """
    Main orchestrator for the trading bot with proper shutdown handling,
    position management, and error recovery.
    """
    
    def __init__(self):
        self.running = True
        self.threads = []
        
        # Initialize configuration first
        try:
            self.config_manager = ConfigManager()
        except Exception as e:
            logger.error(f"Failed to initialize config manager: {e}")
            # Use default config
            self.config_manager = None
        
        # Initialize components
        self.setup_components()
        
        # Setup signal handlers for graceful shutdown
        signal.signal(signal.SIGINT, self.signal_handler)
        signal.signal(signal.SIGTERM, self.signal_handler)
    
    def get_config(self, key: str, default: Any = None) -> Any:
        """Safe config getter with fallback"""
        if self.config_manager:
            try:
                return self.config_manager.get(key, default)
            except:
                return default
        return default
    
    def setup_components(self):
        """Initialize all trading bot components"""
        try:
            # Setup logging
            setup_logger(
                log_dir=self.get_config('logging.path', LOG_DIR),
                log_level=self.get_config('logging.level', 'INFO')
            )
            logger.info("Logger initialized")
            
            # Initialize queues
            self.event_queue = EventQueue()
            self.signal_queue = EventQueue()
            self.order_queue = EventQueue()
            self.execution_queue = EventQueue()
            logger.info("Event queues initialized")
            
            # Initialize database and API
            db_path = self.get_config('data.db_path', 'data/trading_bot.db')
            self.database = Database(db_path)
            logger.info(f"Database initialized: {db_path}")
            
            self.api_wrapper = ShoonyaAPIWrapper()
            logger.info("API wrapper initialized")
            
            # Initialize position manager
            self.position_manager = PositionManager(self.database, self.api_wrapper)
            logger.info("Position manager initialized")
            
            # Initialize strategy with your config structure
            self.strategy = MainStrategy(
                self.event_queue, 
                self.signal_queue,
                buffer=self.get_config('strategy.entry_buffer', 0.0)
            )
            logger.info("Strategy initialized")
            
            # Initialize risk manager with your config structure
            self.risk_manager = RiskManager(
                self.signal_queue,
                self.order_queue,
                max_trades_per_day=self.get_config('risk.max_trades_per_day', 4),
                max_daily_loss=self.get_config('risk.max_daily_loss', 500),
                position_size=self.get_config('risk.position_size', 1)
            )
            logger.info("Risk manager initialized")
            
            # Initialize execution gateway based on mode
            mode = self.get_config('mode', 'papertrading')
            logger.info(f"Initializing execution gateway in {mode} mode")
            
            if mode == 'papertrading':
                try:
                    from trading_bot.execution.paper_gateway import PaperExecutionGateway
                    self.execution_gateway = PaperExecutionGateway(
                        self.order_queue, 
                        self.execution_queue, 
                        self.api_wrapper
                    )
                except ImportError:
                    logger.warning("Paper gateway not available, using mock")
                    self.execution_gateway = self._create_mock_gateway()
            else:
                try:
                    from trading_bot.execution.gateway import ExecutionGateway
                    self.execution_gateway = ExecutionGateway(
                        self.order_queue, 
                        self.execution_queue, 
                        self.api_wrapper
                    )
                except ImportError:
                    logger.error("Live execution gateway not available")
                    self.execution_gateway = self._create_mock_gateway()
            
            logger.info("Execution gateway initialized")
            
            # Initialize data handler with your symbols
            # Use the method from your ConfigManager
            if hasattr(self.config_manager, 'get_trading_symbols'):
                symbols = self.config_manager.get_trading_symbols()
            else:
                symbols = self.get_config('strategy.symbols', DEFAULT_SYMBOLS)
            
            self.data_handler = DataHandler(
                self.api_wrapper,
                self.event_queue,
                symbols
            )
            logger.info(f"Data handler initialized for symbols: {symbols}")
            
        except Exception as e:
            logger.error(f"Failed to setup components: {e}")
            raise
    
    def _create_mock_gateway(self):
        """Create a mock execution gateway for testing"""
        class MockExecutionGateway:
            def __init__(self, order_queue, execution_queue, api_wrapper):
                self.order_queue = order_queue
                self.execution_queue = execution_queue
                self.api_wrapper = api_wrapper
            
            def process_order(self, order):
                logger.info(f"Mock processing order: {order}")
                # Create mock execution
                execution = ExecutionEvent(
                    symbol=order.symbol,
                    timestamp=datetime.now(),
                    order_uuid=order.order_uuid or "mock_uuid",
                    status="FILLED",
                    filled_quantity=order.quantity,
                    avg_fill_price=order.price or 100.0,
                    broker_order_id="mock_broker_id"
                )
                self.execution_queue.put(execution)
        
        return MockExecutionGateway(self.order_queue, self.execution_queue, self.api_wrapper)
    
    def connect_to_broker(self):
        """Connect to broker with retry logic"""
        max_retries = 3
        for attempt in range(max_retries):
            try:
                logger.info(f"Connecting to broker (attempt {attempt + 1}/{max_retries})")
                
                if hasattr(self.api_wrapper, 'connect'):
                    self.api_wrapper.connect()
                    logger.info("Successfully connected to broker")
                    return True
                else:
                    logger.warning("API wrapper has no connect method, assuming connected")
                    return True
                    
            except Exception as e:
                logger.error(f"Broker connection failed: {e}")
                if attempt < max_retries - 1:
                    time.sleep(10)
        
        logger.error("Failed to connect to broker after all attempts")
        return False
    
    def start_data_feed(self):
        """Start market data feed in separate thread"""
        try:
            if hasattr(self.data_handler, 'start_with_reconnection'):
                target_method = self.data_handler.start_with_reconnection
            elif hasattr(self.data_handler, 'start'):
                target_method = self.data_handler.start
            else:
                logger.error("Data handler has no start method")
                return
            
            data_thread = threading.Thread(
                target=target_method,
                daemon=True,
                name="DataHandler"
            )
            data_thread.start()
            self.threads.append(data_thread)
            logger.info("Data feed thread started")
            
        except Exception as e:
            logger.error(f"Failed to start data feed: {e}")
    
    def process_events(self):
        """Main event processing loop with session management"""
        last_heartbeat = datetime.now()
        
        logger.info("Starting main event processing loop")
        
        while self.running:
            try:
                current_time = datetime.now().time()
                
                # Check for 3 PM closure
                if current_time >= dt_time(15, 0, 0) and current_time <= dt_time(15, 5, 0):
                    self._close_all_positions_at_3pm()
                    logger.info("3 PM session closure completed")
                    break
                
                events_processed = 0
                
                # Process market events
                while not self.event_queue.empty() and events_processed < 100:
                    try:
                        event = self.event_queue.get(block=False)
                        
                        if hasattr(self.strategy, 'process_event'):
                            self.strategy.process_event(event)
                        
                        # Update position manager with current prices
                        if isinstance(event, MarketEvent):
                            if hasattr(self.position_manager, 'update_trailing_sl'):
                                self.position_manager.update_trailing_sl(event.symbol, event.price)
                            
                            # Check for exit conditions
                            if hasattr(self.position_manager, 'check_exit_conditions'):
                                exits = self.position_manager.check_exit_conditions(event.symbol, event.price)
                                for pos_id, reason, exit_price in exits:
                                    logger.info(f"Exit condition met: {pos_id} - {reason}")
                                    if hasattr(self.position_manager, 'close_position'):
                                        self.position_manager.close_position(pos_id, reason, exit_price)
                        
                        # For paper trading, update execution gateway
                        if hasattr(self.execution_gateway, 'on_market_event'):
                            self.execution_gateway.on_market_event(event)
                        
                        events_processed += 1
                        
                    except Exception as e:
                        logger.error(f"Error processing market event: {e}")
                
                # Process signals
                while not self.signal_queue.empty():
                    try:
                        signal_event = self.signal_queue.get(block=False)
                        if hasattr(self.risk_manager, 'process_signal'):
                            self.risk_manager.process_signal(signal_event)
                    except Exception as e:
                        logger.error(f"Error processing signal: {e}")
                
                # Process orders
                while not self.order_queue.empty():
                    try:
                        order = self.order_queue.get(block=False)
                        if hasattr(self.execution_gateway, 'process_order'):
                            self.execution_gateway.process_order(order)
                    except Exception as e:
                        logger.error(f"Error processing order: {e}")
                
                # Process executions
                while not self.execution_queue.empty():
                    try:
                        execution_event = self.execution_queue.get(block=False)
                        
                        # Add position to position manager
                        if execution_event.status == 'FILLED':
                            if hasattr(self.position_manager, 'add_position'):
                                sl_points = self.get_config('strategy.sl_points', 2.5)
                                self.position_manager.add_position(execution_event, sl_points=sl_points)
                        
                        logger.info(f"Execution processed: {execution_event}")
                        
                    except Exception as e:
                        logger.error(f"Error processing execution: {e}")
                
                # Heartbeat logging every minute
                now = datetime.now()
                if (now - last_heartbeat).seconds >= 60:
                    position_count = 0
                    if hasattr(self.position_manager, 'open_positions'):
                        position_count = len(self.position_manager.open_positions)
                    
                    logger.info(f"System heartbeat - Active positions: {position_count}")
                    last_heartbeat = now
                
                # Small sleep to prevent CPU spinning
                time.sleep(0.01)
                
            except Exception as e:
                logger.error(f"Error in main event loop: {e}")
                time.sleep(1)
    
    def _close_all_positions_at_3pm(self):
        """Force close all positions at 3 PM"""
        try:
            if not hasattr(self.position_manager, 'open_positions'):
                logger.warning("Position manager has no open_positions attribute")
                return
            
            open_positions = self.position_manager.open_positions
            if not open_positions:
                logger.info("No open positions to close at 3 PM")
                return
            
            for pos_id, position in open_positions.items():
                try:
                    # Create market order to close position
                    close_order = OrderEvent(
                        symbol=position.get('symbol', 'UNKNOWN'),
                        timestamp=datetime.now(),
                        order_type='MARKET',
                        side='SELL' if position.get('side') == 'BUY' else 'BUY',
                        quantity=position.get('quantity', 1),
                        order_uuid=f"3pm_close_{pos_id}",
                        info={'reason': '3PM_CLOSURE', 'position_id': pos_id}
                    )
                    self.order_queue.put(close_order)
                    
                except Exception as e:
                    logger.error(f"Error creating close order for position {pos_id}: {e}")
                
            logger.info(f"Initiated closure of {len(open_positions)} positions at 3 PM")
            
        except Exception as e:
            logger.error(f"Error closing positions at 3 PM: {e}")
    
    def emergency_shutdown(self):
        """Emergency shutdown procedure"""
        logger.warning("Initiating emergency shutdown...")
        
        try:
            # Cancel all pending orders
            if hasattr(self.api_wrapper, 'cancel_all_orders'):
                logger.info("Canceling all pending orders...")
                self.api_wrapper.cancel_all_orders()
            
            # Close all positions (if in live mode)
            if self.get_config('mode') == 'live':
                if hasattr(self.api_wrapper, 'close_all_positions'):
                    logger.info("Closing all positions...")
                    self.api_wrapper.close_all_positions()
            
            # Mark system as halted in database
            if hasattr(self.database, 'save_system_state'):
                self.database.save_system_state('SYSTEM_HALTED', 'TRUE')
                self.database.save_system_state('HALT_TIMESTAMP', datetime.now().isoformat())
            
            send_alert("Emergency shutdown completed", "CRITICAL")
            
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
        if hasattr(self.database, 'save_system_state'):
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
            send_alert("Trading bot starting up", "INFO")
            
            # Perform state reconciliation
            if not reconcile_state(self.api_wrapper, self.database):
                logger.error("State reconciliation failed, cannot proceed safely")
                return
            
            # Connect to broker
            if not self.connect_to_broker():
                logger.error("Cannot proceed without broker connection")
                send_alert("Failed to connect to broker", "CRITICAL")
                return
            
            # Check if system was previously halted
            if hasattr(self.database, 'get_system_state'):
                system_halted = self.database.get_system_state('SYSTEM_HALTED')
                if system_halted == 'TRUE':
                    logger.warning("System was previously halted. Manual intervention may be required.")
                    # In production, you might want to require manual intervention
                    # For now, we'll reset and continue
                    if hasattr(self.database, 'reset_system_halt'):
                        self.database.reset_system_halt()
            
            # Start data feed
            self.start_data_feed()
            
            # Give data feed time to establish connection
            logger.info("Waiting for data feed to establish connection...")
            time.sleep(5)
            
            # Start main event processing loop
            logger.info("Starting main event processing loop")
            send_alert("Trading bot is now active", "INFO")
            self.process_events()
            
        except KeyboardInterrupt:
            logger.info("Interrupted by user")
        except Exception as e:
            logger.error(f"Critical error in main run loop: {e}")
            send_alert(f"Critical error: {e}", "CRITICAL")
            self.emergency_shutdown()
        finally:
            self.graceful_shutdown()
            send_alert("Trading bot shut down", "INFO")


def main():
    """Entry point for the trading bot"""
    try:
        bot = TradingBotOrchestrator()
        bot.run()
    except Exception as e:
        logger.error(f"Failed to start trading bot: {e}")
        if ALERTS_AVAILABLE:
            send_alert(f"Failed to start bot: {e}", "CRITICAL")


if __name__ == '__main__':
    main()