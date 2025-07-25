import csv
import json
from datetime import datetime, timedelta
from dotenv import load_dotenv
import os
import random
from pathlib import Path

# Load environment variables from .env file
load_dotenv()

# Create results directory if it doesn't exist
RESULTS_DIR = Path("backtesting/results")
RESULTS_DIR.mkdir(parents=True, exist_ok=True)

# Debug: Print environment variables
print("Environment variables:")
for key in ['SHOONYA_API_KEY', 'SHOONYA_API_SECRET', 'SHOONYA_USER_ID', 
           'SHOONYA_PASSWORD', 'SHOONYA_VENDOR_CODE', 'SHOONYA_IMEI', 
           'SHOONYA_TOTP_SECRET']:
    print(f"{key}: {'✓' if os.getenv(key) else '✗'}")

from trading_bot.event import MarketEvent
from trading_bot.event_queue import EventQueue
from trading_bot.strategy.main_strategy import MainStrategy
from trading_bot.risk.manager import RiskManager
from trading_bot.execution.paper_gateway import PaperExecutionGateway
from trading_bot.broker.api_wrapper import ShoonyaAPIWrapper
from loguru import logger
from typing import Generator, List, Dict

# Symbol mapping for indices
SYMBOL_MAP = {
    'NIFTY': 'Nifty 50',
    'BANKNIFTY': 'Nifty Bank',
    'FINNIFTY': 'Nifty Fin Services'
}

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
    # Map symbol if it exists in SYMBOL_MAP
    search_symbol = SYMBOL_MAP.get(symbol, symbol)
    
    with open(scrip_master_path, 'r') as csvfile:
        reader = csv.DictReader(csvfile)
        for row in reader:
            if row['Exchange'] == exchange and row['Symbol'] == search_symbol:
                return row['Token']
    raise ValueError(f"Symbol {symbol} ({search_symbol}) not found in scrip master.")

def generate_mock_data(
    symbol: str,
    start: str,
    end: str,
    interval: str = '1m'
) -> Generator[MarketEvent, None, None]:
    """
    Generate mock market data for backtesting.
    
    Args:
        symbol (str): Instrument symbol.
        start (str): Start datetime (e.g., '2024-07-01 09:15:00').
        end (str): End datetime (e.g., '2024-07-01 15:30:00').
        interval (str): Data interval (e.g., '1m').
        
    Yields:
        MarketEvent: Market event for each bar.
    """
    start_dt = datetime.strptime(start, '%Y-%m-%d %H:%M:%S')
    end_dt = datetime.strptime(end, '%Y-%m-%d %H:%M:%S')
    interval_minutes = int(interval.replace('m', ''))
    
    # Initial price around 19000 for NIFTY
    current_price = 19000.0
    
    current_dt = start_dt
    while current_dt <= end_dt:
        # Random walk with 0.1% standard deviation
        price_change = random.gauss(0, current_price * 0.001)
        current_price += price_change
        
        # Generate random volume between 1000-5000
        volume = random.randint(1000, 5000)
        
        # Create market event
        yield MarketEvent(
            symbol=symbol,
            timestamp=current_dt,
            price=current_price,
            volume=volume,
            ohlcv={
                'open': current_price - price_change,
                'high': max(current_price, current_price - price_change),
                'low': min(current_price, current_price - price_change),
                'close': current_price,
                'volume': volume
            }
        )
        
        current_dt += timedelta(minutes=interval_minutes)

def save_results(trades: List[Dict], start_time: str, end_time: str):
    """
    Save backtest results to files.
    
    Args:
        trades (List[Dict]): List of execution events
        start_time (str): Backtest start time
        end_time (str): Backtest end time
    """
    # Create timestamp for unique filenames
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    
    # Save detailed trade data to CSV
    csv_path = RESULTS_DIR / f"trades_{timestamp}.csv"
    with open(csv_path, 'w', newline='') as csvfile:
        fieldnames = ['timestamp', 'symbol', 'status', 'filled_quantity', 'avg_fill_price', 'broker_order_id']
        writer = csv.DictWriter(csvfile, fieldnames=fieldnames)
        writer.writeheader()
        for trade in trades:
            writer.writerow({
                'timestamp': trade.timestamp,
                'symbol': trade.symbol,
                'status': trade.status,
                'filled_quantity': trade.filled_quantity,
                'avg_fill_price': trade.avg_fill_price,
                'broker_order_id': trade.broker_order_id
            })
    
    # Calculate and save metrics to JSON
    metrics = calculate_metrics(trades)
    metrics.update({
        'start_time': start_time,
        'end_time': end_time,
        'run_timestamp': timestamp
    })
    
    json_path = RESULTS_DIR / f"metrics_{timestamp}.json"
    with open(json_path, 'w') as jsonfile:
        json.dump(metrics, jsonfile, indent=4)
    
    logger.info(f"Results saved to:")
    logger.info(f"  - Trade details: {csv_path}")
    logger.info(f"  - Metrics summary: {json_path}")
    
    # Print summary to console
    print("\nBacktest Results Summary:")
    print(f"Total trades: {metrics['total_trades']}")
    print(f"Total P&L: {metrics['total_pnl']:.2f}")
    print(f"Win rate: {metrics['win_rate']:.2f}%")
    print(f"Average profit per trade: {metrics['avg_profit_per_trade']:.2f}")

def calculate_metrics(trades: List[Dict]) -> Dict:
    """
    Calculate performance metrics from trades.
    
    Args:
        trades (List[Dict]): List of execution events
        
    Returns:
        Dict: Dictionary containing performance metrics
    """
    if not trades:
        return {
            "total_trades": 0,
            "total_pnl": 0,
            "win_rate": 0,
            "avg_profit_per_trade": 0,
            "max_drawdown": 0
        }
    
    # For now, we'll calculate basic metrics
    # TODO: Add more sophisticated calculations like drawdown, Sharpe ratio, etc.
    total_trades = len(trades)
    
    # Calculate P&L based on entry and exit pairs
    pnl = 0
    winning_trades = 0
    current_position = 0
    entry_price = 0
    
    for trade in trades:
        if trade.filled_quantity > 0:  # Entry
            current_position = trade.filled_quantity
            entry_price = trade.avg_fill_price
        elif trade.filled_quantity < 0:  # Exit
            trade_pnl = (entry_price - trade.avg_fill_price) * abs(trade.filled_quantity)
            pnl += trade_pnl
            if trade_pnl > 0:
                winning_trades += 1
            current_position = 0
            entry_price = 0
    
    metrics = {
        "total_trades": total_trades,
        "total_pnl": pnl,
        "win_rate": (winning_trades / (total_trades/2)) * 100 if trades else 0,  # Divide by 2 since each trade is entry+exit
        "avg_profit_per_trade": pnl / (total_trades/2) if trades else 0,
        # TODO: Add more sophisticated metrics like Sharpe ratio, max drawdown, etc.
    }
    
    return metrics

def run_backtest():
    """
    Run the backtest using the event-driven system with mock data.
    """
    start_time = '2024-07-01 09:15:00'
    end_time = '2024-07-01 15:30:00'
    
    event_queue = EventQueue()
    signal_queue = EventQueue()
    order_queue = EventQueue()
    execution_queue = EventQueue()

    strategy = MainStrategy(event_queue, signal_queue)
    risk_manager = RiskManager(signal_queue, order_queue)
    execution_gateway = PaperExecutionGateway(order_queue, execution_queue)

    trades = []

    for event in generate_mock_data(
        symbol='NIFTY',
        start=start_time,
        end=end_time,
        interval='1m'
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

    # Save and display results
    save_results(trades, start_time, end_time)

if __name__ == '__main__':
    run_backtest() 