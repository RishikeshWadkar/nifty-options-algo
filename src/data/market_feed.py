import logging
from datetime import datetime
from typing import Dict, Callable, List
from ..models.market_data import MarketTick

class MarketDataFeed:
    def __init__(self):
        self.subscribers: List[Callable[[MarketTick], None]] = []
        self.last_tick: Dict[str, MarketTick] = {}
        self.logger = logging.getLogger(__name__)
        
    def subscribe(self, callback: Callable[[MarketTick], None]) -> None:
        """Subscribe to market data updates"""
        self.subscribers.append(callback)
        
    def _handle_tick(self, tick_data: dict) -> None:
        """Process incoming tick data"""
        try:
            tick = MarketTick(
                symbol=tick_data['symbol'],
                ltp=float(tick_data['last_price']),
                timestamp=datetime.fromtimestamp(tick_data['timestamp']),
                volume=int(tick_data['volume']),
                oi=int(tick_data.get('oi', 0)),
                high=float(tick_data.get('high', 0)),
                low=float(tick_data.get('low', 0))
            )
            self.last_tick[tick.symbol] = tick
            
            # Notify all subscribers
            for subscriber in self.subscribers:
                subscriber(tick)
                
        except Exception as e:
            self.logger.error(f"Error processing tick: {e}")
            
    def get_last_tick(self, symbol: str) -> MarketTick:
        """Get the most recent tick for a symbol"""
        return self.last_tick.get(symbol)