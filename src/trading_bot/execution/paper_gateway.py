from typing import Any
from trading_bot.event import OrderEvent, ExecutionEvent, MarketEvent
from loguru import logger
from datetime import datetime

class PaperExecutionGateway:
    """
    Simulates order execution for paper trading. Does not place real orders.
    Tracks open positions, simulates fills, and checks for SL/TP hits using live prices.

    Args:
        order_queue: Queue for incoming OrderEvents.
        execution_queue: Queue for outgoing ExecutionEvents.
        api_wrapper: (Optional) Broker API wrapper instance (not used in paper trading).
    """
    def __init__(self, order_queue: Any, execution_queue: Any, api_wrapper: Any = None) -> None:
        """
        Initialize the PaperExecutionGateway.

        Args:
            order_queue: Queue for incoming OrderEvents.
            execution_queue: Queue for outgoing ExecutionEvents.
            api_wrapper: (Optional) Broker API wrapper instance (not used in paper trading).
        """
        self.order_queue = order_queue
        self.execution_queue = execution_queue
        self.open_positions: dict[str, dict[str, Any]] = {}
        self.last_price: dict[str, float] = {}

    def process_order(self, order: OrderEvent) -> None:
        """
        Simulate instant entry fill for paper trading and track open position for SL/TP simulation.

        Args:
            order (OrderEvent): The incoming order event.
        """
        try:
            exec_event = ExecutionEvent(
                symbol=order.symbol,
                timestamp=datetime.now(),
                order_uuid=order.order_uuid,
                status='FILLED',
                filled_quantity=order.quantity,
                avg_fill_price=order.price or self.last_price.get(order.symbol, 0.0),
                broker_order_id='PAPER_ORDER',
                info={'paper': True, 'entry': True}
            )
            self.execution_queue.put(exec_event)
            logger.info(f"[PaperExecutionGateway] Simulated entry ExecutionEvent: {exec_event}")
            self.open_positions[order.order_uuid] = {
                'symbol': order.symbol,
                'side': order.side,
                'entry_price': order.price or self.last_price.get(order.symbol, 0.0),
                'quantity': order.quantity,
                'sl': order.info.get('sl') if order.info else None,
                'tp': order.info.get('tp') if order.info else None,
                'open': True
            }
        except Exception as exc:
            logger.error(f"[PaperExecutionGateway] Error processing order: {exc}")

    def on_market_event(self, event: MarketEvent) -> None:
        """
        Update last seen price and check all open positions for SL/TP hit.
        Generate exit ExecutionEvents if SL/TP is triggered.

        Args:
            event (MarketEvent): The incoming market event.
        """
        try:
            self.last_price[event.symbol] = event.price
            to_close: list[tuple[str, str]] = []
            for order_uuid, pos in self.open_positions.items():
                if not pos['open']:
                    continue
                if pos['side'] == 'BUY':
                    if pos['sl'] is not None and event.price <= pos['sl']:
                        to_close.append((order_uuid, 'SL'))
                    elif pos['tp'] is not None and event.price >= pos['tp']:
                        to_close.append((order_uuid, 'TP'))
                elif pos['side'] == 'SELL':
                    if pos['sl'] is not None and event.price >= pos['sl']:
                        to_close.append((order_uuid, 'SL'))
                    elif pos['tp'] is not None and event.price <= pos['tp']:
                        to_close.append((order_uuid, 'TP'))
            for order_uuid, reason in to_close:
                pos = self.open_positions[order_uuid]
                exec_event = ExecutionEvent(
                    symbol=pos['symbol'],
                    timestamp=datetime.now(),
                    order_uuid=order_uuid,
                    status='FILLED',
                    filled_quantity=pos['quantity'],
                    avg_fill_price=event.price,
                    broker_order_id='PAPER_ORDER_EXIT',
                    info={'paper': True, 'exit_reason': reason}
                )
                self.execution_queue.put(exec_event)
                logger.info(f"[PaperExecutionGateway] Simulated exit ExecutionEvent: {exec_event}")
                pos['open'] = False
        except Exception as exc:
            logger.error(f"[PaperExecutionGateway] Error processing market event: {exc}") 