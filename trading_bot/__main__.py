import threading
import time
from typing import Any
from trading_bot.utils.logger import setup_logger
from trading_bot.event_queue import EventQueue
from trading_bot.broker.api_wrapper import ShoonyaAPIWrapper
from trading_bot.broker.data_handler import DataHandler
from trading_bot.strategy.main_strategy import MainStrategy
from trading_bot.risk.manager import RiskManager
import yaml
from loguru import logger

LOG_DIR = 'logs'
SYMBOLS = ['NIFTY']  # Add your symbols here

def main() -> None:
    """
    Main entry point for the trading bot. Initializes all components, loads configuration,
    and starts the event-driven trading loop.
    """
    setup_logger(log_dir=LOG_DIR)
    logger.info('Starting trading bot main loop (live mode).')

    with open('config/config.yaml', 'r') as f:
        config = yaml.safe_load(f)
    mode = config.get('mode', 'live')

    if mode == 'papertrading':
        from trading_bot.execution.paper_gateway import PaperExecutionGateway as ExecutionGateway
    elif mode == 'live':
        from trading_bot.execution.gateway import ExecutionGateway

    event_queue: EventQueue = EventQueue()
    signal_queue: EventQueue = EventQueue()
    order_queue: EventQueue = EventQueue()
    execution_queue: EventQueue = EventQueue()

    api_wrapper: ShoonyaAPIWrapper = ShoonyaAPIWrapper()
    api_wrapper.connect()

    data_handler: DataHandler = DataHandler(api_wrapper, event_queue, SYMBOLS)
    data_thread: threading.Thread = threading.Thread(target=data_handler.start, daemon=True)
    data_thread.start()

    strategy: MainStrategy = MainStrategy(event_queue, signal_queue)
    risk_manager: RiskManager = RiskManager(signal_queue, order_queue)
    execution_gateway: Any = ExecutionGateway(order_queue, execution_queue, api_wrapper)

    # Startup reconciliation placeholder (implement as needed)
    # TODO: Load open trades/orders from DB, reconcile with broker state

    try:
        while True:
            if not event_queue.empty():
                event = event_queue.get()
                strategy.process_event(event)
                if mode == 'papertrading':
                    execution_gateway.on_market_event(event)
            if not signal_queue.empty():
                signal = signal_queue.get()
                risk_manager.process_signal(signal)
            if not order_queue.empty():
                order = order_queue.get()
                execution_gateway.process_order(order)
            if not execution_queue.empty():
                exec_event = execution_queue.get()
                logger.info(f"[MainLoop] ExecutionEvent processed: {exec_event}")
            time.sleep(0.01)
    except KeyboardInterrupt:
        logger.info('Trading bot interrupted by user.')
    except Exception as exc:
        logger.exception(f'Critical error in main event loop: {exc}')
    finally:
        logger.info('Trading bot main loop finished.')

if __name__ == '__main__':
    main()
