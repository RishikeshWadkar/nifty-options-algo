from typing import List, Dict
from trading_bot.event import MarketEvent

class ZoneCalculator:
    """
    Utility for 9:16 AM price zone calculations for the strategy.
    Extracts the first 15-minute candle (from MarketEvents) and computes entry zones.

    Args:
        buffer (float): Optional buffer to add/subtract from zones.
    """
    def __init__(self, buffer: float = 0.0) -> None:
        """
        Initialize the ZoneCalculator.

        Args:
            buffer (float): Buffer to add/subtract from entry zones.
        """
        self.buffer: float = buffer

    def calculate_zones(self, events: List[MarketEvent]) -> Dict[str, float]:
        """
        Given a list of MarketEvents for the first 15 minutes, calculate the open, high, low, close, and entry zones.

        Args:
            events (List[MarketEvent]): List of market events for the first 15 minutes.

        Returns:
            Dict[str, float]: Dictionary with keys: 'open', 'high', 'low', 'close', 'long_entry', 'short_entry'.

        Raises:
            ValueError: If no market events are provided.
        """
        if not events:
            raise ValueError("No market events provided for zone calculation.")
        open_price: float = events[0].price
        high_price: float = max(e.price for e in events)
        low_price: float = min(e.price for e in events)
        close_price: float = events[-1].price
        long_entry: float = high_price + self.buffer
        short_entry: float = low_price - self.buffer
        return {
            'open': open_price,
            'high': high_price,
            'low': low_price,
            'close': close_price,
            'long_entry': long_entry,
            'short_entry': short_entry
        } 