import sqlite3
import pandas as pd
from datetime import datetime, timedelta
from contextlib import contextmanager
from typing import Generator, Optional
from ..models.market_data import MarketTick

class MarketDataStore:
    def __init__(self, db_path: str = "market_data.db"):
        self.db_path = db_path
        self._init_db()
    
    @contextmanager
    def _get_connection(self) -> Generator[sqlite3.Connection, None, None]:
        """Context manager for database connections"""
        conn = sqlite3.connect(self.db_path)
        try:
            yield conn
        finally:
            conn.close()

    def _init_db(self) -> None:
        """Initialize the database with required tables"""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS market_ticks (
                    symbol TEXT,
                    timestamp DATETIME,
                    ltp REAL,
                    volume INTEGER,
                    oi INTEGER,
                    high REAL,
                    low REAL,
                    PRIMARY KEY (symbol, timestamp)
                )
            ''')
            conn.commit()

    def store_tick(self, tick: MarketTick) -> None:
        """Store a market tick in the database"""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('''
                INSERT OR REPLACE INTO market_ticks 
                (symbol, timestamp, ltp, volume, oi, high, low)
                VALUES (?, ?, ?, ?, ?, ?, ?)
            ''', (
                tick.symbol,
                tick.timestamp,
                tick.ltp,
                tick.volume,
                tick.oi,
                tick.high,
                tick.low
            ))
            conn.commit()

    def get_ohlcv_data(self, 
                       symbol: str, 
                       start_time: datetime, 
                       end_time: datetime,
                       interval: str = '1min') -> pd.DataFrame:
        """
        Get OHLCV (Open, High, Low, Close, Volume) data for given timeframe
        Args:
            symbol: Trading symbol
            start_time: Start datetime
            end_time: End datetime
            interval: Time interval ('1min', '5min', '15min', etc.)
        """
        with self._get_connection() as conn:
            df = pd.read_sql_query('''
                SELECT * FROM market_ticks 
                WHERE symbol = ? 
                AND timestamp BETWEEN ? AND ?
                ORDER BY timestamp
            ''', conn, params=(symbol, start_time, end_time),
                parse_dates=['timestamp'])
            
            if df.empty:
                return pd.DataFrame()

            # Resample to desired interval
            df.set_index('timestamp', inplace=True)
            resampled = df.resample(interval).agg({
                'ltp': 'ohlc',
                'volume': 'sum',
                'oi': 'last'
            })
            
            # Flatten column names
            resampled.columns = ['open', 'high', 'low', 'close', 'volume', 'oi']
            return resampled.reset_index()

    def cleanup_old_data(self, days_to_keep: int = 5) -> None:
        """Remove market data older than specified days"""
        cutoff_date = datetime.now() - timedelta(days=days_to_keep)
        
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('''
                DELETE FROM market_ticks 
                WHERE timestamp < ?
            ''', (cutoff_date,))
            conn.commit()

    def get_last_price(self, symbol: str) -> Optional[float]:
        """Get the most recent price for a symbol"""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('''
                SELECT ltp FROM market_ticks 
                WHERE symbol = ? 
                ORDER BY timestamp DESC 
                LIMIT 1
            ''', (symbol,))
            result = cursor.fetchone()
            return result[0] if result else None

# Example usage
from datetime import datetime, timedelta

# Initialize store
store = MarketDataStore()

# Get 5-minute OHLCV data
start_time = datetime.now() - timedelta(days=1)
end_time = datetime.now()
ohlcv_data = store.get_ohlcv_data(
    symbol="NIFTY-I",
    start_time=start_time,
    end_time=end_time,
    interval='5min'
)

# Cleanup old data
store.cleanup_old_data(days_to_keep=5)

# Get last price
last_price = store.get_last_price("NIFTY-I")