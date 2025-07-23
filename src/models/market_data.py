from dataclasses import dataclass
from datetime import datetime
from typing import Optional

@dataclass
class MarketTick:
    """Represents a single market data tick"""
    symbol: str
    ltp: float
    timestamp: datetime
    volume: int
    oi: Optional[int] = None
    high: Optional[float] = None
    low: Optional[float] = None