from typing import Optional
from trading_bot.event import SignalEvent, OrderEvent
from trading_bot.persistence.database import Database
from loguru import logger
from datetime import datetime

class RiskManager:
    """
    Consumes SignalEvents, evaluates them against the configured risk rules, and produces OrderEvents if they are valid.
    Enforces max trades per day, max daily loss, and position sizing.

    Args:
        signal_queue: Queue for incoming SignalEvents.
        order_queue: Queue for outgoing OrderEvents.
        db_path (str): Path to the SQLite database.
        max_trades_per_day (int): Maximum trades allowed per day.
        max_daily_loss (float): Maximum daily loss allowed.
        position_size (int): Position size for each trade.
    """
    def __init__(
        self,
        signal_queue,
        order_queue,
        db_path: str = 'data/trading_bot.db',
        max_trades_per_day: int = 4,
        max_daily_loss: float = 500.0,
        position_size: int = 1
    ) -> None:
        """
        Initialize the RiskManager.

        Args:
            signal_queue: Queue for incoming SignalEvents.
            order_queue: Queue for outgoing OrderEvents.
            db_path (str): Path to the SQLite database.
            max_trades_per_day (int): Maximum trades allowed per day.
            max_daily_loss (float): Maximum daily loss allowed.
            position_size (int): Position size for each trade.
        """
        self.signal_queue = signal_queue
        self.order_queue = order_queue
        self.db = Database(db_path)
        self.max_trades_per_day: int = max_trades_per_day
        self.max_daily_loss: float = max_daily_loss
        self.position_size: int = position_size
        self.trades_today: int = 0
        self.daily_loss: float = 0.0
        self.today: datetime.date = datetime.now().date()

    def process_signal(self, signal: SignalEvent) -> None:
        """
        Process a SignalEvent, enforce risk checks, and generate OrderEvents if valid.

        Args:
            signal (SignalEvent): The incoming signal event.
        """
        try:
            now = datetime.now().date()
            if now != self.today:
                self.trades_today = 0
                self.daily_loss = 0.0
                self.today = now
            if self.trades_today >= self.max_trades_per_day:
                logger.warning(f"[RiskManager] Max trades per day reached. Signal blocked: {signal}")
                return
            if self.daily_loss <= -abs(self.max_daily_loss):
                logger.warning(f"[RiskManager] Max daily loss reached. Signal blocked: {signal}")
                return
            order = OrderEvent(
                symbol=signal.symbol,
                timestamp=signal.timestamp,
                order_type='MARKET',
                side='BUY' if signal.signal_type == 'LONG' else 'SELL',
                quantity=self.position_size,
                price=None,
                stop_price=None,
                order_uuid=None,
                info={'from_signal': signal}
            )
            self.order_queue.put(order)
            self.trades_today += 1
            logger.info(f"[RiskManager] OrderEvent created and enqueued: {order}")
        except Exception as exc:
            logger.error(f"[RiskManager] Error processing signal: {exc}")
from typing import Dict, Optional, Any
from datetime import datetime
from loguru import logger
from trading_bot.event import ExecutionEvent, OrderEvent
from trading_bot.persistence.database import Database

class PositionManager:
    """
    Enhanced position manager with trailing stop loss, take profit,
    and comprehensive position tracking for live trading.
    """
    
    def __init__(self, database: Database, api_wrapper: Any):
        self.db = database
        self.api_wrapper = api_wrapper
        self.open_positions: Dict[str, Dict] = {}
        self.load_positions_from_db()
    
    def load_positions_from_db(self):
        """Load open positions from database on startup"""
        open_trades = self.db.get_open_trades()
        for trade in open_trades:
            self.open_positions[trade[1]] = {  # trade_uuid
                'symbol': trade[2],
                'entry_price': trade[5],
                'quantity': trade[8],
                'side': 'BUY',  # Determine from quantity sign
                'entry_time': trade[4],
                'sl_price': None,
                'tp_price': None,
                'trailing_sl': False
            }
        logger.info(f"Loaded {len(self.open_positions)} positions from database")
    
    def add_position(self, execution_event: ExecutionEvent, sl_points: float = 2.5):
        """Add new position with automatic SL/TP calculation"""
        if execution_event.status == 'FILLED':
            position_id = execution_event.order_uuid
            entry_price = execution_event.avg_fill_price
            
            # Calculate SL and TP based on your strategy
            if execution_event.info.get('entry'):  # Long position
                sl_price = entry_price - sl_points
                tp_price = entry_price + (sl_points * 2)  # 1:2 RR
            else:  # Short position  
                sl_price = entry_price + sl_points
                tp_price = entry_price - (sl_points * 2)
            
            self.open_positions[position_id] = {
                'symbol': execution_event.symbol,
                'entry_price': entry_price,
                'quantity': execution_event.filled_quantity,
                'entry_time': execution_event.timestamp,
                'sl_price': sl_price,
                'tp_price': tp_price,
                'trailing_sl': False,
                'side': 'LONG' if execution_event.info.get('entry') else 'SHORT'
            }
            
            logger.info(f"Added position: {position_id} at {entry_price} with SL: {sl_price}")
    
    def update_trailing_sl(self, symbol: str, current_price: float):
        """Update trailing stop loss for all positions of given symbol"""
        for pos_id, position in self.open_positions.items():
            if position['symbol'] == symbol and position['trailing_sl']:
                if position['side'] == 'LONG':
                    # Trail SL up for long positions
                    new_sl = current_price - 2.5
                    if new_sl > position['sl_price']:
                        position['sl_price'] = new_sl
                        logger.info(f"Updated trailing SL for {pos_id}: {new_sl}")
                else:
                    # Trail SL down for short positions
                    new_sl = current_price + 2.5
                    if new_sl < position['sl_price']:
                        position['sl_price'] = new_sl
                        logger.info(f"Updated trailing SL for {pos_id}: {new_sl}")
    
    def check_exit_conditions(self, symbol: str, current_price: float) -> list:
        """Check if any positions need to be exited"""
        exits_needed = []
        
        for pos_id, position in self.open_positions.items():
            if position['symbol'] != symbol:
                continue
                
            if position['side'] == 'LONG':
                if current_price <= position['sl_price']:
                    exits_needed.append((pos_id, 'SL_HIT', current_price))
                elif current_price >= position['tp_price']:
                    exits_needed.append((pos_id, 'TP_HIT', current_price))
            else:  # SHORT
                if current_price >= position['sl_price']:
                    exits_needed.append((pos_id, 'SL_HIT', current_price))
                elif current_price <= position['tp_price']:
                    exits_needed.append((pos_id, 'TP_HIT', current_price))
        
        return exits_needed
    
    def close_position(self, position_id: str, reason: str, exit_price: float):
        """Close position and update database"""
        if position_id in self.open_positions:
            position = self.open_positions[position_id]
            
            # Calculate P&L
            if position['side'] == 'LONG':
                pnl = (exit_price - position['entry_price']) * position['quantity']
            else:
                pnl = (position['entry_price'] - exit_price) * position['quantity']
            
            # Update database
            trade_data = {
                'trade_uuid': position_id,
                'symbol': position['symbol'],
                'strategy_id': 'zone_strategy',
                'entry_timestamp': position['entry_time'],
                'entry_price': position['entry_price'],
                'exit_timestamp': datetime.now(),
                'exit_price': exit_price,
                'quantity': position['quantity'],
                'pnl': pnl,
                'status': 'CLOSED'
            }
            self.db.save_trade(trade_data)
            
            # Remove from active positions
            del self.open_positions[position_id]
            
            logger.info(f"Closed position {position_id}: P&L = {pnl}, Reason: {reason}")
            return pnl
        
        return 0

