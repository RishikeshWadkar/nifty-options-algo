from typing import Optional, Dict
from trading_bot.event import MarketEvent, SignalEvent
from trading_bot.strategy.zone_calculator import ZoneCalculator
from loguru import logger
from datetime import datetime, time

class MainStrategy:
    """Nifty Small SL Algo - Zone-based options trading strategy"""
    
    def __init__(self, event_queue, signal_queue, zone_offset: float = 2.5):
        self.event_queue = event_queue
        self.signal_queue = signal_queue
        self.zone_calculator = ZoneCalculator(zone_offset)
        self.zones: Optional[Dict] = None
        self.current_position_type: Optional[str] = None  # 'CE', 'PE', or None
        self.pending_order_id: Optional[str] = None
        self.gates_status = {'ce_gate': True, 'pe_gate': True}  # Both gates open initially
        
    def process_event(self, event: MarketEvent) -> None:
        """Process market events for zone-based trading"""
        try:
            current_time = event.timestamp.time()
            
            # Calculate zones at 9:16 AM
            if self.zone_calculator.should_calculate_zones(current_time):
                self.zones = self.zone_calculator.calculate_zones_at_916(event.price)
                return
            
            # Skip if zones not calculated yet
            if not self.zones:
                return
            
            # Check for zone crossings
            self._check_zone_crossings(event)
            
        except Exception as e:
            logger.error(f"Error processing event in strategy: {e}")
    
    def _check_zone_crossings(self, event: MarketEvent):
        """Check for zone crossings and generate signals"""
        current_price = event.price
        
        # Upper zone crossing (CE entry)
        if (current_price >= self.zones['upper_zone'] and 
            self.gates_status['ce_gate']):
            
            self._generate_signal(event, 'CE', 'UPPER_ZONE_CROSS')
            self.gates_status['pe_gate'] = False  # Close PE gate
            
        # Lower zone crossing (PE entry)
        elif (current_price <= self.zones['lower_zone'] and 
              self.gates_status['pe_gate']):
            
            self._generate_signal(event, 'PE', 'LOWER_ZONE_CROSS')
            self.gates_status['ce_gate'] = False  # Close CE gate
            
        # Middle zone touch (reopen gates)
        elif (abs(current_price - self.zones['middle_zone']) <= 0.5):
            self.gates_status = {'ce_gate': True, 'pe_gate': True}
            logger.info("Middle zone touched - Both gates reopened")
    
    def _generate_signal(self, event: MarketEvent, option_type: str, reason: str):
        """Generate trading signal with cancel-and-replace logic"""
        signal = SignalEvent(
            symbol=event.symbol,
            timestamp=event.timestamp,
            signal_type=option_type,  # 'CE' or 'PE'
            strength=1.0,
            info={
                'reason': reason,
                'index_price': event.price,
                'zones': self.zones,
                'cancel_pending': self.pending_order_id is not None,
                'pending_order_id': self.pending_order_id
            }
        )
        
        self.signal_queue.put(signal)
        logger.info(f"Generated {option_type} signal: {reason} at price {event.price}")
