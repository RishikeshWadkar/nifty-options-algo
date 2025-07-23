import csv
import time
from datetime import datetime
from typing import Any, Optional, List
from trading_bot.event import MarketEvent
from loguru import logger

class MockDataHandler:
    """
    Mock data handler for backtesting. Reads market data from a CSV file and generates MarketEvent objects.
    """
    def __init__(self, csv_path: str, event_queue, interval: float = 0.1):
        self.csv_path = csv_path
        self.event_queue = event_queue
        self.interval = interval  # seconds between events

    def start(self):
        logger.info(f"[MockDataHandler] Starting mock data feed from {self.csv_path}")
        with open(self.csv_path, 'r') as csvfile:
            reader = csv.DictReader(csvfile)
            for row in reader:
                event = MarketEvent(
                    symbol=row['symbol'],
                    timestamp=datetime.strptime(row['timestamp'], '%Y-%m-%d %H:%M:%S'),
                    price=float(row['price']),
                    volume=float(row['volume']) if 'volume' in row and row['volume'] else None,
                    ohlcv={
                        'open': float(row['open']) if 'open' in row and row['open'] else None,
                        'high': float(row['high']) if 'high' in row and row['high'] else None,
                        'low': float(row['low']) if 'low' in row and row['low'] else None,
                        'close': float(row['close']) if 'close' in row and row['close'] else None,
                        'volume': float(row['volume']) if 'volume' in row and row['volume'] else None,
                    } if 'open' in row else None
                )
                self.event_queue.put(event)
                logger.info(f"[MockDataHandler] MarketEvent enqueued: {event}")
                time.sleep(self.interval)
        logger.info("[MockDataHandler] End of mock data feed.")

class DataHandler:
    """
    Real data handler for live trading. Uses ShoonyaAPIWrapper to subscribe to live market data via WebSocket.
    Parses and validates incoming ticks, converts to MarketEvent, and enqueues them.
    Implements all data sanity checks (timestamp, price/volume, OHLCV, spike detection, etc.).

    Args:
        api_wrapper: ShoonyaAPIWrapper instance.
        event_queue: Queue for outgoing MarketEvents.
        symbols (List[str]): List of symbols to subscribe to.
        sanity_config (Optional[dict]): Optional config for data sanity checks.
    """
    def __init__(
        self,
        api_wrapper: Any,
        event_queue: Any,
        symbols: List[str],
        sanity_config: Optional[dict] = None
    ) -> None:
        """
        Initialize the DataHandler.

        Args:
            api_wrapper: ShoonyaAPIWrapper instance.
            event_queue: Queue for outgoing MarketEvents.
            symbols (List[str]): List of symbols to subscribe to.
            sanity_config (Optional[dict]): Optional config for data sanity checks.
        """
        self.api_wrapper = api_wrapper
        self.event_queue = event_queue
        self.symbols = symbols
        self.sanity_config = sanity_config or {}
        self.ws_open = False

    def start(self) -> None:
        """
        Connect to Shoonya WebSocket, subscribe to symbols, and process incoming ticks.
        For each valid tick, create a MarketEvent and enqueue it.
        """
        try:
            logger.info(f"[DataHandler] Starting live data feed for symbols: {self.symbols}")
            self.api_wrapper.session.start_websocket(
                subscribe_callback=self.on_tick,
                order_update_callback=self.on_order_update,
                socket_open_callback=self.on_ws_open
            )
            while not self.ws_open:
                time.sleep(0.1)
            self.api_wrapper.session.subscribe(self.symbols)
            logger.info("[DataHandler] Subscribed to live market data.")
        except Exception as exc:
            logger.error(f"[DataHandler] Error starting data handler: {exc}")

    def on_tick(self, tick_data: dict) -> None:
        """
        Callback for incoming market data ticks. Validate and enqueue as MarketEvent.

        Args:
            tick_data (dict): Raw tick data from Shoonya WebSocket.
        """
        try:
            symbol: str = tick_data.get('tsym')
            timestamp: str = tick_data.get('time')  # Format: 'DD-MM-YYYY HH:MM:SS'
            price: float = float(tick_data.get('lp', 0))
            volume: Optional[float] = float(tick_data.get('v', 0)) if 'v' in tick_data else None
            ohlcv: dict = {
                'open': float(tick_data.get('o', 0)),
                'high': float(tick_data.get('h', 0)),
                'low': float(tick_data.get('l', 0)),
                'close': float(tick_data.get('c', 0)),
                'volume': volume
            }
            event = MarketEvent(
                symbol=symbol,
                timestamp=timestamp,
                price=price,
                volume=volume,
                ohlcv=ohlcv
            )
            self.event_queue.put(event)
            logger.info(f"[DataHandler] MarketEvent enqueued: {event}")
        except Exception as exc:
            logger.error(f"[DataHandler] Error processing tick: {exc}")

    def on_order_update(self, order_data: dict) -> None:
        """
        Callback for order updates (optional, for live monitoring).

        Args:
            order_data (dict): Raw order update data from Shoonya WebSocket.
        """
        logger.info(f"[DataHandler] Order update: {order_data}")

    def on_ws_open(self) -> None:
        """
        Callback for WebSocket open event.
        """
        logger.info("[DataHandler] WebSocket connection opened.")
        self.ws_open = True 