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
