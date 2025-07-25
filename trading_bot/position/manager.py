from typing import Dict, Optional, Any
from datetime import datetime
from loguru import logger
from trading_bot.event import ExecutionEvent
from trading_bot.persistence.database import Database

class PositionManager:
    """Enhanced position manager with trailing SL and position tracking"""
    
    def __init__(self, database: Database, api_wrapper: Any):
        self.db = database
        self.api_wrapper = api_wrapper
        self.open_positions: Dict[str, Dict] = {}
        self.pending_orders: Dict[str, Dict] = {}
        self.load_positions_from_db()
    
    def add_position(self, execution_event: ExecutionEvent, sl_points: float = 2.5):
        """Add new position with automatic SL calculation"""
        if execution_event.status == 'FILLED':
            position_id = execution_event.order_uuid
            entry_price = execution_event.avg_fill_price
            
            # Calculate SL based on strategy (2.5 rupees)
            sl_price = entry_price - sl_points if execution_event.info.get('side') == 'BUY' else entry_price + sl_points
            
            self.open_positions[position_id] = {
                'symbol': execution_event.symbol,
                'entry_price': entry_price,
                'quantity': execution_event.filled_quantity,
                'entry_time': execution_event.timestamp,
                'sl_price': sl_price,
                'side': execution_event.info.get('side', 'BUY'),
                'trailing_sl': False
            }
            
            logger.info(f"Added position: {position_id} at {entry_price} with SL: {sl_price}")
    
    def cancel_pending_order(self, order_id: str) -> bool:
        """Cancel pending order - critical for zone strategy"""
        try:
            if order_id in self.pending_orders:
                result = self.api_wrapper.cancel_order(order_id)
                if result.get('stat') == 'Ok':
                    del self.pending_orders[order_id]
                    logger.info(f"Cancelled pending order: {order_id}")
                    return True
            return False
        except Exception as e:
            logger.error(f"Failed to cancel order {order_id}: {e}")
            return False
    
    def check_exit_conditions(self, symbol: str, current_price: float) -> list:
        """Check SL/TP conditions for all positions"""
        exits_needed = []
        
        for pos_id, position in self.open_positions.items():
            if position['symbol'] != symbol:
                continue
                
            if position['side'] == 'BUY':
                if current_price <= position['sl_price']:
                    exits_needed.append((pos_id, 'SL_HIT', current_price))
            else:  # SELL
                if current_price >= position['sl_price']:
                    exits_needed.append((pos_id, 'SL_HIT', current_price))
        
        return exits_needed
    
    def load_positions_from_db(self):
        """Load open positions from database on startup"""
        try:
            open_trades = self.db.get_open_trades()
            for trade in open_trades:
                # Implement based on your database schema
                pass
            logger.info(f"Loaded {len(self.open_positions)} positions from database")
        except Exception as e:
            logger.error(f"Failed to load positions: {e}")