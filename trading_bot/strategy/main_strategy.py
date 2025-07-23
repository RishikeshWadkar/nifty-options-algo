from typing import Optional
from trading_bot.event import MarketEvent, SignalEvent
from trading_bot.strategy.zone_calculator import ZoneCalculator
from loguru import logger
from datetime import datetime, time

class MainStrategy:
    """
    Core strategy class that consumes MarketEvents, utilizes the zone_calculator,
    and produces SignalEvents based on the defined rules (e.g., Nifty Small SL Algo).

    Args:
        event_queue (EventQueue): Queue for incoming MarketEvents.
        signal_queue (EventQueue): Queue for outgoing SignalEvents.
        buffer (float): Buffer to add/subtract from entry zones.
    """
    def __init__(self, event_queue, signal_queue, buffer: float = 0.0) -> None:
        """
        Initialize the MainStrategy.

        Args:
            event_queue: Queue for incoming MarketEvents.
            signal_queue: Queue for outgoing SignalEvents.
            buffer (float): Buffer to add/subtract from entry zones.
        """
        self.event_queue = event_queue
        self.signal_queue = signal_queue
        self.zone_calculator = ZoneCalculator(buffer=buffer)
        self.first_15min_events: list[MarketEvent] = []
        self.zones: Optional[dict] = None
        self.in_position: bool = False
        self.entry_time: time = time(9, 16)
        self.zone_calculated: bool = False

    def process_event(self, event: MarketEvent) -> None:
        """
        Process a MarketEvent, update zone calculation, and generate SignalEvents as needed.

        Args:
            event (MarketEvent): The incoming market event.
        """
        try:
            event_time: time = event.timestamp.time() if hasattr(event.timestamp, 'time') else datetime.strptime(str(event.timestamp), '%Y-%m-%d %H:%M:%S').time()
            if not self.zone_calculated:
                if event_time <= self.entry_time:
                    self.first_15min_events.append(event)
                    logger.info(f"[MainStrategy] Collecting event for zone: {event}")
                else:
                    self.zones = self.zone_calculator.calculate_zones(self.first_15min_events)
                    self.zone_calculated = True
                    logger.info(f"[MainStrategy] Zones calculated: {self.zones}")
            else:
                if not self.in_position:
                    # Entry logic
                    if event.price >= self.zones['long_entry']:
                        signal = SignalEvent(
                            symbol=event.symbol,
                            timestamp=event.timestamp,
                            signal_type='LONG',
                            strength=1.0,
                            info={'entry_price': event.price}
                        )
                        self.signal_queue.put(signal)
                        self.in_position = True
                        logger.info(f"[MainStrategy] LONG entry signal generated: {signal}")
                    elif event.price <= self.zones['short_entry']:
                        signal = SignalEvent(
                            symbol=event.symbol,
                            timestamp=event.timestamp,
                            signal_type='SHORT',
                            strength=1.0,
                            info={'entry_price': event.price}
                        )
                        self.signal_queue.put(signal)
                        self.in_position = True
                        logger.info(f"[MainStrategy] SHORT entry signal generated: {signal}")
                # Add exit/SL/TSL logic as needed
        except Exception as exc:
            logger.error(f"[MainStrategy] Error processing event: {exc}")
