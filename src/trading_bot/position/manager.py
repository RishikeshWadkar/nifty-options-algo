from typing import Dict, Optional, Any, List, Tuple
from datetime import datetime
from loguru import logger
from trading_bot.event import ExecutionEvent, OrderEvent
from trading_bot.persistence.database import Database

class PositionManager:
    """Enhanced position manager with trailing SL and position tracking for zone-based strategy"""
    
    def __init__(self, database: Database, api_wrapper: Any):
        self.db = database
        self.api_wrapper = api_wrapper
        self.open_positions: Dict[str, Dict] = {}
        self.pending_orders: Dict[str, Dict] = {}
        self.daily_trades_count = 0
        self.daily_pnl = 0.0
        self.load_positions_from_db()
    
    def add_position(self, execution_event: ExecutionEvent, sl_points: float = 2.5):
        """Add new position with automatic SL calculation"""
        if execution_event.status == 'FILLED':
            position_id = execution_event.order_uuid
            entry_price = execution_event.avg_fill_price
            side = execution_event.info.get('side', 'BUY')
            
            # Calculate SL based on strategy (2.5 rupees)
            if side == 'BUY':
                sl_price = entry_price - sl_points
            else:  # SELL
                sl_price = entry_price + sl_points
            
            self.open_positions[position_id] = {
                'symbol': execution_event.symbol,
                'entry_price': entry_price,
                'quantity': execution_event.filled_quantity,
                'entry_time': execution_event.timestamp,
                'sl_price': sl_price,
                'side': side,
                'trailing_sl': False,
                'highest_profit': 0.0,
                'current_price': entry_price,
                'profit_milestones': [5.0, 10.0, 15.0, 20.0]  # For trailing SL
            }
            
            # Place immediate SL order
            self._place_sl_order(position_id)
            
            logger.info(f"Added position: {position_id} at {entry_price} with SL: {sl_price}")
    
    def _place_sl_order(self, position_id: str):
        """Place stop-loss order for position"""
        try:
            position = self.open_positions[position_id]
            
            # Create SL order
            sl_order_data = {
                'symbol': position['symbol'],
                'quantity': position['quantity'],
                'price': position['sl_price'],
                'side': 'SELL' if position['side'] == 'BUY' else 'BUY',
                'order_type': 'SL',
                'trigger_price': position['sl_price']
            }
            
            # Place SL order through API
            if hasattr(self.api_wrapper, 'place_order'):
                result = self.api_wrapper.place_order(**sl_order_data)
                if result.get('stat') == 'Ok':
                    position['sl_order_id'] = result.get('norenordno')
                    logger.info(f"SL order placed for position {position_id}: {result.get('norenordno')}")
                    
        except Exception as e:
            logger.error(f"Failed to place SL order for position {position_id}: {e}")
    
    def update_trailing_sl(self, symbol: str, current_price: float):
        """Update trailing stop-loss based on profit milestones"""
        for pos_id, position in self.open_positions.items():
            if position['symbol'] != symbol:
                continue
                
            position['current_price'] = current_price
            
            # Calculate current profit
            if position['side'] == 'BUY':
                profit = current_price - position['entry_price']
            else:
                profit = position['entry_price'] - current_price
            
            # Update highest profit
            if profit > position['highest_profit']:
                position['highest_profit'] = profit
                
                # Check for trailing SL activation
                self._check_trailing_sl_activation(pos_id, profit)
    
    def _check_trailing_sl_activation(self, position_id: str, current_profit: float):
        """Check and activate trailing SL based on profit milestones"""
        position = self.open_positions[position_id]
        
        # Trailing SL logic based on profit milestones
        if current_profit >= 20.0 and not position['trailing_sl']:
            # Activate trailing SL at 15 rupees profit
            new_sl = position['entry_price'] + 15.0 if position['side'] == 'BUY' else position['entry_price'] - 15.0
            self._update_sl_order(position_id, new_sl)
            position['trailing_sl'] = True
            logger.info(f"Trailing SL activated for {position_id} at {new_sl}")
            
        elif current_profit >= 15.0 and position['trailing_sl']:
            # Trail SL to maintain 5 rupee buffer from highest profit
            if position['side'] == 'BUY':
                new_sl = position['entry_price'] + position['highest_profit'] - 5.0
            else:
                new_sl = position['entry_price'] - position['highest_profit'] + 5.0
            
            if ((position['side'] == 'BUY' and new_sl > position['sl_price']) or 
                (position['side'] == 'SELL' and new_sl < position['sl_price'])):
                self._update_sl_order(position_id, new_sl)
                position['sl_price'] = new_sl
                logger.info(f"Trailing SL updated for {position_id} to {new_sl}")
    
    def _update_sl_order(self, position_id: str, new_sl_price: float):
        """Update existing SL order"""
        try:
            position = self.open_positions[position_id]
            
            # Cancel existing SL order
            if 'sl_order_id' in position:
                self.api_wrapper.cancel_order(position['sl_order_id'])
            
            # Place new SL order
            sl_order_data = {
                'symbol': position['symbol'],
                'quantity': position['quantity'],
                'price': new_sl_price,
                'side': 'SELL' if position['side'] == 'BUY' else 'BUY',
                'order_type': 'SL',
                'trigger_price': new_sl_price
            }
            
            result = self.api_wrapper.place_order(**sl_order_data)
            if result.get('stat') == 'Ok':
                position['sl_order_id'] = result.get('norenordno')
                
        except Exception as e:
            logger.error(f"Failed to update SL order for position {position_id}: {e}")
    
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
    
    def cancel_all_pending_orders(self) -> int:
        """Cancel all pending orders - required for zone strategy"""
        cancelled_count = 0
        pending_order_ids = list(self.pending_orders.keys())
        
        for order_id in pending_order_ids:
            if self.cancel_pending_order(order_id):
                cancelled_count += 1
        
        logger.info(f"Cancelled {cancelled_count} pending orders")
        return cancelled_count
    
    def check_exit_conditions(self, symbol: str, current_price: float) -> List[Tuple[str, str, float]]:
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
    
    def close_position(self, position_id: str, reason: str, exit_price: float):
        """Close position and calculate P&L"""
        if position_id not in self.open_positions:
            logger.warning(f"Position {position_id} not found for closing")
            return
        
        position = self.open_positions[position_id]
        
        try:
            # Place market order to close position
            close_order_data = {
                'symbol': position['symbol'],
                'quantity': position['quantity'],
                'side': 'SELL' if position['side'] == 'BUY' else 'BUY',
                'order_type': 'MKT'
            }
            
            result = self.api_wrapper.place_order(**close_order_data)
            
            if result.get('stat') == 'Ok':
                # Calculate P&L
                if position['side'] == 'BUY':
                    pnl = (exit_price - position['entry_price']) * position['quantity']
                else:
                    pnl = (position['entry_price'] - exit_price) * position['quantity']
                
                # Update daily P&L
                self.daily_pnl += pnl
                
                # Cancel SL order if exists
                if 'sl_order_id' in position:
                    try:
                        self.api_wrapper.cancel_order(position['sl_order_id'])
                    except:
                        pass
                
                # Save to database
                self._save_closed_position(position_id, position, exit_price, pnl, reason)
                
                # Remove from open positions
                del self.open_positions[position_id]
                
                logger.info(f"Position {position_id} closed. Reason: {reason}, P&L: {pnl:.2f}")
                
        except Exception as e:
            logger.error(f"Failed to close position {position_id}: {e}")
    
    def close_all_positions(self, reason: str = "SESSION_END"):
        """Close all open positions - for 3 PM closure"""
        position_ids = list(self.open_positions.keys())
        
        for pos_id in position_ids:
            position = self.open_positions[pos_id]
            current_price = position.get('current_price', position['entry_price'])
            self.close_position(pos_id, reason, current_price)
        
        logger.info(f"Closed all positions. Reason: {reason}")
    
    def _save_closed_position(self, position_id: str, position: Dict, exit_price: float, pnl: float, reason: str):
        """Save closed position to database"""
        try:
            trade_data = {
                'position_id': position_id,
                'symbol': position['symbol'],
                'entry_price': position['entry_price'],
                'exit_price': exit_price,
                'quantity': position['quantity'],
                'side': position['side'],
                'entry_time': position['entry_time'],
                'exit_time': datetime.now(),
                'pnl': pnl,
                'exit_reason': reason
            }
            
            if hasattr(self.db, 'save_trade'):
                self.db.save_trade(trade_data)
                
        except Exception as e:
            logger.error(f"Failed to save closed position to database: {e}")
    
    def get_daily_stats(self) -> Dict[str, Any]:
        """Get daily trading statistics"""
        return {
            'daily_trades': self.daily_trades_count,
            'daily_pnl': self.daily_pnl,
            'open_positions': len(self.open_positions),
            'pending_orders': len(self.pending_orders)
        }
    
    def reset_daily_counters(self):
        """Reset daily counters - called at start of new trading day"""
        self.daily_trades_count = 0
        self.daily_pnl = 0.0
        logger.info("Daily counters reset")
    
    def load_positions_from_db(self):
        """Load open positions from database on startup"""
        try:
            if hasattr(self.db, 'get_open_trades'):
                open_trades = self.db.get_open_trades()
                for trade in open_trades:
                    # Reconstruct position from database
                    position_id = trade.get('position_id')
                    if position_id:
                        self.open_positions[position_id] = {
                            'symbol': trade.get('symbol'),
                            'entry_price': trade.get('entry_price'),
                            'quantity': trade.get('quantity'),
                            'entry_time': trade.get('entry_time'),
                            'sl_price': trade.get('sl_price'),
                            'side': trade.get('side'),
                            'trailing_sl': trade.get('trailing_sl', False),
                            'highest_profit': trade.get('highest_profit', 0.0),
                            'current_price': trade.get('entry_price')
                        }
                        
            logger.info(f"Loaded {len(self.open_positions)} positions from database")
        except Exception as e:
            logger.error(f"Failed to load positions: {e}")