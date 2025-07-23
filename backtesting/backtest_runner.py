import csv
from datetime import datetime
from trading_bot.event import MarketEvent
from trading_bot.event_queue import EventQueue
from trading_bot.strategy.main_strategy import MainStrategy
from trading_bot.risk.manager import RiskManager
from trading_bot.execution.paper_gateway import PaperExecutionGateway
from trading_bot.broker.api_wrapper import ShoonyaAPIWrapper
from loguru import logger
from typing import Generator, List, Dict

def resolve_token(symbol: str, scrip_master_path: str, exchange: str = 'NSE') -> str:
    """
    Resolve the Shoonya token for a given symbol from the scrip master file.

    Args:
        symbol (str): Trading symbol (e.g., 'NIFTY').
        scrip_master_path (str): Path to the scrip master CSV file.
        exchange (str): Exchange code (e.g., 'NSE').

    Returns:
        str: Token for the symbol.

    Raises:
        ValueError: If symbol is not found.
    """
    with open(scrip_master_path, 'r') as csvfile:
        reader = csv.DictReader(csvfile)
        for row in reader:
            if row['exch'] == exchange and row['tsym'] == symbol:
                return row['token']
    raise ValueError(f"Symbol {symbol} not found in scrip master.")

def fetch_historical_data_from_api(
    symbol: str,
    start: str,
    end: str,
    interval: str = '1m',
    scrip_master_path: str = 'data/NSE_symbols.txt',
    exchange: str = 'NSE'
) -> Generator[MarketEvent, None, None]:
    """
    Fetch historical data from Shoonya API and yield MarketEvent objects.

    Args:
        symbol (str): Instrument symbol.
        start (str): Start datetime (e.g., '2024-07-01 09:15:00').
        end (str): End datetime (e.g., '2024-07-01 15:30:00').
        interval (str): Data interval (e.g., '1m').
        scrip_master_path (str): Path to scrip master file.
        exchange (str): Exchange code.

    Yields:
        MarketEvent: Market event for each bar.
    """
    api = ShoonyaAPIWrapper()
    api.connect()
    token = resolve_token(symbol, scrip_master_path, exchange)
    bars: List[Dict] = api.session.get_time_price_series(
        exchange=exchange,
        token=token,
        starttime=int(datetime.strptime(start, '%Y-%m-%d %H:%M:%S').timestamp()),
        endtime=int(datetime.strptime(end, '%Y-%m-%d %H:%M:%S').timestamp()),
        interval=int(interval.replace('m', ''))
    )
    for bar in bars:
        yield MarketEvent(
            symbol=symbol,
            timestamp=datetime.strptime(bar['time'], '%d-%m-%Y %H:%M:%S'),
            price=float(bar['intc']),
            volume=float(bar['intv']),
            ohlcv={
                'open': float(bar['into']),
                'high': float(bar['inth']),
                'low': float(bar['intl']),
                'close': float(bar['intc']),
                'volume': float(bar['intv'])
            }
        )

def run_backtest():
    """
    Run the backtest using the event-driven system.
    """
    event_queue = EventQueue()
    signal_queue = EventQueue()
    order_queue = EventQueue()
    execution_queue = EventQueue()

    strategy = MainStrategy(event_queue, signal_queue)
    risk_manager = RiskManager(signal_queue, order_queue)
    execution_gateway = PaperExecutionGateway(order_queue, execution_queue)

    trades = []

    for event in fetch_historical_data_from_api(
        symbol='NIFTY',
        start='2024-07-01 09:15:00',
        end='2024-07-01 15:30:00',
        interval='1m',
        scrip_master_path='data/NSE_symbols.txt',
        exchange='NSE'
    ):
        event_queue.put(event)
        execution_gateway.on_market_event(event)

        if not event_queue.empty():
            strategy.process_event(event_queue.get())
        if not signal_queue.empty():
            risk_manager.process_signal(signal_queue.get())
        if not order_queue.empty():
            execution_gateway.process_order(order_queue.get())
        if not execution_queue.empty():
            exec_event = execution_queue.get()
            trades.append(exec_event)
            logger.info(f"[Backtest] ExecutionEvent: {exec_event}")

    print(f"Total trades: {len(trades)}")
    # TODO: Add more metrics and reporting as needed

if __name__ == '__main__':
    run_backtest() 