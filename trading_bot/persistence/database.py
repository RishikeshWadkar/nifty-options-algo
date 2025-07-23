from typing import Optional, Any, Dict, List
import sqlite3
from threading import Lock

class Database:
    """
    SQLite interface for persisting trades, orders, and system state.
    Ensures ACID compliance and provides methods for crash recovery and reconciliation.

    Args:
        db_path (str): Path to the SQLite database file.
    """
    def __init__(self, db_path: str = "data/trading_bot.db") -> None:
        """
        Initialize the Database and create tables if they do not exist.

        Args:
            db_path (str): Path to the SQLite database file.
        """
        self.db_path: str = db_path
        self._lock: Lock = Lock()
        self._init_db()

    def _init_db(self) -> None:
        """
        Create required tables if they do not exist.
        """
        with self._get_conn() as conn:
            cursor = conn.cursor()
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS trades (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    trade_uuid TEXT UNIQUE,
                    symbol TEXT,
                    strategy_id TEXT,
                    entry_timestamp DATETIME,
                    entry_price REAL,
                    exit_timestamp DATETIME,
                    exit_price REAL,
                    quantity INTEGER,
                    pnl REAL,
                    status TEXT
                )
            ''')
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS orders (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    order_uuid TEXT UNIQUE,
                    broker_order_id TEXT,
                    trade_uuid TEXT,
                    timestamp DATETIME,
                    symbol TEXT,
                    order_type TEXT,
                    side TEXT,
                    price REAL,
                    quantity INTEGER,
                    status TEXT
                )
            ''')
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS system_state (
                    key TEXT PRIMARY KEY,
                    value TEXT
                )
            ''')
            conn.commit()

    def _get_conn(self) -> sqlite3.Connection:
        """
        Get a new SQLite connection.

        Returns:
            sqlite3.Connection: SQLite connection object.
        """
        return sqlite3.connect(self.db_path, check_same_thread=False)

    def save_trade(self, trade: Dict[str, Any]) -> None:
        """
        Save or update a trade record in the database.

        Args:
            trade (Dict[str, Any]): Trade data to save.
        """
        with self._lock, self._get_conn() as conn:
            cursor = conn.cursor()
            cursor.execute('''
                INSERT OR REPLACE INTO trades (
                    trade_uuid, symbol, strategy_id, entry_timestamp, entry_price, exit_timestamp, exit_price, quantity, pnl, status
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ''', (
                trade.get('trade_uuid'), trade.get('symbol'), trade.get('strategy_id'),
                trade.get('entry_timestamp'), trade.get('entry_price'),
                trade.get('exit_timestamp'), trade.get('exit_price'),
                trade.get('quantity'), trade.get('pnl'), trade.get('status')
            ))
            conn.commit()

    def save_order(self, order: Dict[str, Any]) -> None:
        """
        Save or update an order record in the database.

        Args:
            order (Dict[str, Any]): Order data to save.
        """
        with self._lock, self._get_conn() as conn:
            cursor = conn.cursor()
            cursor.execute('''
                INSERT OR REPLACE INTO orders (
                    order_uuid, broker_order_id, trade_uuid, timestamp, symbol, order_type, side, price, quantity, status
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ''', (
                order.get('order_uuid'), order.get('broker_order_id'), order.get('trade_uuid'),
                order.get('timestamp'), order.get('symbol'), order.get('order_type'),
                order.get('side'), order.get('price'), order.get('quantity'), order.get('status')
            ))
            conn.commit()

    def save_system_state(self, key: str, value: str) -> None:
        """
        Save or update a system state variable in the database.

        Args:
            key (str): State variable name.
            value (str): State variable value.
        """
        with self._lock, self._get_conn() as conn:
            cursor = conn.cursor()
            cursor.execute('''
                INSERT OR REPLACE INTO system_state (key, value) VALUES (?, ?)
            ''', (key, value))
            conn.commit()

    def get_open_trades(self) -> List[Any]:
        """
        Get all open trades from the database.

        Returns:
            List[Any]: List of open trade records.
        """
        with self._lock, self._get_conn() as conn:
            cursor = conn.cursor()
            cursor.execute('''SELECT * FROM trades WHERE status = 'OPEN' ''')
            return cursor.fetchall()

    def get_pending_orders(self) -> List[Any]:
        """
        Get all pending orders from the database.

        Returns:
            List[Any]: List of pending order records.
        """
        with self._lock, self._get_conn() as conn:
            cursor = conn.cursor()
            cursor.execute('''SELECT * FROM orders WHERE status IN ('PENDING', 'SENT_TO_BROKER')''')
            return cursor.fetchall()

    def get_system_state(self, key: str) -> Optional[str]:
        """
        Get the value of a system state variable from the database.

        Args:
            key (str): State variable name.

        Returns:
            Optional[str]: State variable value, or None if not found.
        """
        with self._lock, self._get_conn() as conn:
            cursor = conn.cursor()
            cursor.execute('''SELECT value FROM system_state WHERE key = ?''', (key,))
            row = cursor.fetchone()
            return row[0] if row else None

    def reset_system_halt(self) -> None:
        """
        Reset the SYSTEM_HALTED flag in the system state table.
        """
        self.save_system_state('SYSTEM_HALTED', 'FALSE')
