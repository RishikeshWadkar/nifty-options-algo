from typing import Any
from trading_bot.event import OrderEvent, ExecutionEvent
from loguru import logger
from datetime import datetime

class ExecutionGateway:
    """
    Consumes OrderEvents, places trades via broker, and produces ExecutionEvents.

    Args:
        order_queue: Queue for incoming OrderEvents.
        execution_queue: Queue for outgoing ExecutionEvents.
        api_wrapper: Broker API wrapper instance.
    """
    def __init__(self, order_queue: Any, execution_queue: Any, api_wrapper: Any) -> None:
        """
        Initialize the ExecutionGateway.

        Args:
            order_queue: Queue for incoming OrderEvents.
            execution_queue: Queue for outgoing ExecutionEvents.
            api_wrapper: Broker API wrapper instance.
        """
        self.order_queue = order_queue
        self.execution_queue = execution_queue
        self.api_wrapper = api_wrapper

    def process_order(self, order: OrderEvent) -> None:
        """
        Process an OrderEvent, place the order via broker, and enqueue an ExecutionEvent.

        Args:
            order (OrderEvent): The incoming order event.
        """
        try:
            ret = self.api_wrapper.place_order(order.__dict__)
            status = ret.get('stat', 'UNKNOWN')
            broker_order_id = ret.get('norenordno')
            exec_event = ExecutionEvent(
                symbol=order.symbol,
                timestamp=datetime.now(),
                order_uuid=order.order_uuid or broker_order_id,
                status=status,
                filled_quantity=order.quantity if status == 'Ok' else 0,
                avg_fill_price=ret.get('avgprc'),
                broker_order_id=broker_order_id,
                info={'order_response': ret}
            )
            self.execution_queue.put(exec_event)
            logger.info(f"[ExecutionGateway] ExecutionEvent created and enqueued: {exec_event}")
        except Exception as exc:
            logger.error(f"[ExecutionGateway] Error placing order: {exc}") 