import time
from typing import Any, Optional
from trading_bot.event import OrderEvent, ExecutionEvent
from loguru import logger
from datetime import datetime

class ExecutionGateway:
    """Enhanced execution gateway with retry logic and order management"""
    
    def __init__(self, order_queue: Any, execution_queue: Any, api_wrapper: Any, 
                 max_retries: int = 10, retry_gap: float = 1.0):
        self.order_queue = order_queue
        self.execution_queue = execution_queue
        self.api_wrapper = api_wrapper
        self.max_retries = max_retries
        self.retry_gap = retry_gap
    
    def process_order(self, order: OrderEvent) -> None:
        """Process order with retry logic"""
        try:
            # Cancel pending order if requested
            if order.info and order.info.get('cancel_pending'):
                pending_id = order.info.get('pending_order_id')
                if pending_id:
                    self._cancel_order(pending_id)
            
            # Place new order with retries
            self._place_order_with_retries(order)
            
        except Exception as e:
            logger.error(f"Error processing order: {e}")
    
    def _place_order_with_retries(self, order: OrderEvent):
        """Place order with retry mechanism"""
        for attempt in range(self.max_retries):
            try:
                # Get current option price
                current_price = self._get_option_price(order.symbol)
                if not current_price:
                    logger.error(f"Could not get price for {order.symbol}")
                    return
                
                # Calculate limit price (LTP + 1 rupee + retry gap)
                limit_price = current_price + 1.0 + (attempt * self.retry_gap)
                
                # Place order
                result = self.api_wrapper.place_order(
                    buy_or_sell='B' if order.side == 'BUY' else 'S',
                    product_type='M',  # NRML for options
                    exchange='NFO',
                    tradingsymbol=order.symbol,
                    quantity=order.quantity,
                    price_type='LMT',
                    price=limit_price,
                    retention='DAY'
                )
                
                if result.get('stat') == 'Ok':
                    # Order placed successfully
                    order_id = result.get('norenordno')
                    logger.info(f"Order placed successfully: {order_id} at {limit_price}")
                    
                    # Wait for fill (1 second)
                    time.sleep(1)
                    
                    # Check order status
                    if self._check_order_filled(order_id):
                        self._create_execution_event(order, result, 'FILLED')
                        return
                    else:
                        # Not filled, cancel and retry
                        self._cancel_order(order_id)
                        logger.info(f"Order not filled, retrying... (attempt {attempt + 1}/{self.max_retries})")
                        continue
                else:
                    logger.error(f"Order placement failed: {result}")
                    
            except Exception as e:
                logger.error(f"Retry {attempt + 1} failed: {e}")
        
        # All retries exhausted
        logger.error(f"All {self.max_retries} retries exhausted for order {order.symbol}")
    
    def _get_option_price(self, symbol: str) -> Optional[float]:
        """Get current option price"""
        try:
            quotes = self.api_wrapper.get_quotes(exchange='NFO', token=symbol)
            if quotes and quotes.get('stat') == 'Ok':
                return float(quotes.get('lp', 0))
        except Exception as e:
            logger.error(f"Error getting option price: {e}")
        return None
    
    def _check_order_filled(self, order_id: str) -> bool:
        """Check if order is filled"""
        try:
            order_status = self.api_wrapper.get_order_status(order_id)
            return order_status.get('status') == 'COMPLETE'
        except Exception as e:
            logger.error(f"Error checking order status: {e}")
            return False
    
    def _cancel_order(self, order_id: str) -> bool:
        """Cancel order"""
        try:
            result = self.api_wrapper.cancel_order(order_id)
            return result.get('stat') == 'Ok'
        except Exception as e:
            logger.error(f"Error cancelling order: {e}")
            return False
    
    def _create_execution_event(self, order: OrderEvent, result: dict, status: str):
        """Create execution event"""
        exec_event = ExecutionEvent(
            symbol=order.symbol,
            timestamp=datetime.now(),
            order_uuid=result.get('norenordno'),
            status=status,
            filled_quantity=order.quantity if status == 'FILLED' else 0,
            avg_fill_price=float(result.get('avgprc', 0)) if result.get('avgprc') else None,
            broker_order_id=result.get('norenordno'),
            info={'order_response': result, 'side': order.side}
        )
        self.execution_queue.put(exec_event)