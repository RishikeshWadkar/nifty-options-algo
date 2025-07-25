from typing import List, Dict, Optional
from datetime import datetime, time as dt_time
from loguru import logger
from trading_bot.event import MarketEvent

class ZoneCalculator:
    """Enhanced zone calculator for Nifty Small SL Algo strategy"""
    
    def __init__(self, buffer: float = 2.5):
        self.buffer = buffer  # ±2.5 points for zone calculation
        self.zones_calculated = False
        self.setup_complete = False
        self.atm_strike = None
        self.index_ltp = None
        self.zones = {
            'upper': None,
            'middle': None, 
            'lower': None
        }
        self.setup_events: List[MarketEvent] = []
        
    def add_setup_event(self, event: MarketEvent) -> bool:
        """Add market event during setup phase (9:15:50 - 9:16:00)"""
        current_time = datetime.now().time()
        
        # Setup phase: 9:15:50 - 9:16:00
        setup_start = dt_time(9, 15, 50)
        setup_end = dt_time(9, 16, 0)
        
        if setup_start <= current_time <= setup_end:
            self.setup_events.append(event)
            
            # Update index LTP during setup
            if event.symbol == 'NIFTY' or 'NIFTY' in event.symbol:
                self.index_ltp = event.price
                
            return True
        
        # Calculate zones at 9:16:00
        elif current_time > setup_end and not self.zones_calculated:
            self._calculate_zones()
            return False
            
        return False
    
    def _calculate_zones(self):
        """Calculate trading zones based on setup phase data"""
        if not self.setup_events or self.index_ltp is None:
            logger.error("Insufficient data for zone calculation")
            return
        
        try:
            # Find ATM strike (nearest 50 multiple)
            self.atm_strike = round(self.index_ltp / 50) * 50
            
            # Calculate zones based on INDEX LTP ± 2.5 points
            self.zones = {
                'upper': self.index_ltp + self.buffer,    # INDEX LTP + 2.5
                'middle': self.index_ltp,                 # INDEX LTP
                'lower': self.index_ltp - self.buffer     # INDEX LTP - 2.5
            }
            
            self.zones_calculated = True
            self.setup_complete = True
            
            logger.info(f"Zones calculated - ATM Strike: {self.atm_strike}")
            logger.info(f"Upper Zone: {self.zones['upper']:.2f}")
            logger.info(f"Middle Zone: {self.zones['middle']:.2f}")
            logger.info(f"Lower Zone: {self.zones['lower']:.2f}")
            
        except Exception as e:
            logger.error(f"Failed to calculate zones: {e}")
    
    def get_zone_signal(self, current_price: float) -> Optional[str]:
        """Get trading signal based on zone crossing"""
        if not self.zones_calculated:
            return None
        
        # Zone crossing logic
        if current_price > self.zones['upper']:
            return 'CE_ENTRY'  # Call entry signal
        elif current_price < self.zones['lower']:
            return 'PE_ENTRY'  # Put entry signal
        else:
            return None  # No signal in middle zone
    
    def get_option_symbol(self, signal_type: str) -> Optional[str]:
        """Get option symbol based on signal type"""
        if not self.atm_strike:
            return None
        
        # Get current week expiry (simplified - you may need to enhance this)
        current_date = datetime.now()
        
        # For now, using a simplified symbol format
        # You'll need to implement proper symbol generation based on your broker's format
        if signal_type == 'CE_ENTRY':
            return f"NIFTY{current_date.strftime('%y%m%d')}{self.atm_strike}CE"
        elif signal_type == 'PE_ENTRY':
            return f"NIFTY{current_date.strftime('%y%m%d')}{self.atm_strike}PE"
        
        return None
    
    def is_setup_complete(self) -> bool:
        """Check if zone setup is complete"""
        return self.setup_complete
    
    def reset_daily(self):
        """Reset zones for new trading day"""
        self.zones_calculated = False
        self.setup_complete = False
        self.atm_strike = None
        self.index_ltp = None
        self.zones = {'upper': None, 'middle': None, 'lower': None}
        self.setup_events = []
        logger.info("Zone calculator reset for new trading day")
    
    def get_zones(self) -> Dict[str, Optional[float]]:
        """Get current zone levels"""
        return self.zones.copy()