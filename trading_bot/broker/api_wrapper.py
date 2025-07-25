# trading_bot/broker/api_wrapper.py
# Updated to use official Shoonya API patterns

import os
import pyotp
import yaml
from typing import Any, Optional, Dict, List
from datetime import datetime
from loguru import logger

# Import the official Shoonya API
try:
    from NorenRestApiPy.NorenApi import NorenApi
except ImportError:
    logger.error("NorenRestApiPy not installed. Install with: pip install NorenRestApiPy")
    raise

class ShoonyaAPIWrapper:
    """
    Production-ready Shoonya API wrapper using official NorenRestApiPy.
    Handles authentication, order management, data feeds, and error recovery.
    """
    
    def __init__(self, config_path: str = 'config/config.yaml') -> None:
        """Initialize the Shoonya API wrapper with configuration."""
        self.config = self._load_config(config_path)
        self.session: Optional[NorenApi] = None
        self.susertoken: Optional[str] = None
        self.is_connected = False
        
        # Credentials from config
        self.user_id = self.config['user_id']
        self.password = self.config['password']
        self.api_key = self.config['api_key']
        self.api_secret = self.config['api_secret']
        self.vendor_code = self.config['vendor_code']
        self.imei = self.config['imei']
        self.totp_secret = self.config['totp_secret']
    
    def _load_config(self, config_path: str) -> Dict[str, str]:
        """Load Shoonya configuration from YAML file."""
        try:
            with open(config_path, 'r') as f:
                config = yaml.safe_load(f)
            
            shoonya_config = config.get('shoonya', {})
            
            # Resolve environment variables
            resolved_config = {}
            for key, value in shoonya_config.items():
                if isinstance(value, str) and value.startswith('${') and value.endswith('}'):
                    env_var = value[2:-1]
                    resolved_config[key] = os.environ.get(env_var)
                    if not resolved_config[key]:
                        raise ValueError(f"Environment variable {env_var} not set")
                else:
                    resolved_config[key] = value
            
            return resolved_config
            
        except Exception as e:
            logger.error(f"Failed to load Shoonya config: {e}")
            raise
    
    def connect(self) -> bool:
        """
        Authenticate with Shoonya API using TOTP.
        Returns True if successful, False otherwise.
        """
        try:
            # Generate TOTP for 2FA
            totp = pyotp.TOTP(self.totp_secret)
            otp = totp.now()
            logger.info(f"Generated OTP for Shoonya login: {otp}")
            
            # Initialize API session
            self.session = NorenApi(
                host='https://api.shoonya.com/NorenWClientTP/',
                websocket='wss://api.shoonya.com/NorenWSTP/'
            )
            
            # Login with credentials
            ret = self.session.login(
                userid=self.user_id,
                password=self.password,
                twoFA=otp,
                vendor_code=self.vendor_code,
                api_secret=self.api_key,
                imei=self.imei
            )
            
            if ret and ret.get('stat') == 'Ok':
                self.susertoken = ret.get('susertoken')
                self.is_connected = True
                logger.info("Successfully connected to Shoonya API")
                return True
            else:
                logger.error(f"Shoonya login failed: {ret}")
                return False
                
        except Exception as e:
            logger.error(f"Error connecting to Shoonya API: {e}")
            return False
    
    def place_order(self, order_details: Dict[str, Any]) -> Dict[str, Any]:
        """
        Place an order using Shoonya API.
        
        Args:
            order_details: Order parameters following Shoonya format
            
        Returns:
            API response dictionary
        """
        if not self.is_connected:
            raise RuntimeError("Not connected to Shoonya API")
        
        try:
            # Map internal order format to Shoonya API format
            shoonya_order = {
                'buy_or_sell': 'B' if order_details.get('side') == 'BUY' else 'S',
                'product_type': order_details.get('product_type', 'I'),  # I=Intraday, C=CNC
                'exchange': order_details.get('exchange', 'NSE'),
                'tradingsymbol': order_details.get('symbol'),
                'quantity': str(order_details.get('quantity', 1)),
                'discloseqty': str(order_details.get('disclosed_qty', 0)),
                'price_type': order_details.get('order_type', 'MKT'),  # MKT, LMT, SL-LMT
                'price': str(order_details.get('price', 0)),
                'trigger_price': str(order_details.get('trigger_price', 0)) if order_details.get('trigger_price') else None,
                'retention': order_details.get('validity', 'DAY'),
                'remarks': order_details.get('tag', 'algo_trade')
            }
            
            # Add stop loss and take profit for bracket orders
            if order_details.get('product_type') == 'B':  # Bracket order
                shoonya_order['product_type'] = 'B'
                if order_details.get('stop_loss'):
                    shoonya_order['bookloss_price'] = str(order_details['stop_loss'])
                if order_details.get('take_profit'):
                    shoonya_order['bookprofit_price'] = str(order_details['take_profit'])
            
            ret = self.session.place_order(**shoonya_order)
            logger.info(f"Order placed: {ret}")
            return ret
            
        except Exception as e:
            logger.error(f"Error placing order: {e}")
            raise
    
    def modify_order(self, order_id: str, **kwargs) -> Dict[str, Any]:
        """Modify an existing order."""
        if not self.is_connected:
            raise RuntimeError("Not connected to Shoonya API")
        
        try:
            modify_params = {
                'orderno': order_id,
                'exchange': kwargs.get('exchange', 'NSE'),
                'tradingsymbol': kwargs.get('symbol'),
                'newquantity': str(kwargs.get('quantity')) if kwargs.get('quantity') else None,
                'newprice_type': kwargs.get('order_type'),
                'newprice': str(kwargs.get('price')) if kwargs.get('price') else None,
                'newtrigger_price': str(kwargs.get('trigger_price')) if kwargs.get('trigger_price') else None
            }
            
            # Remove None values
            modify_params = {k: v for k, v in modify_params.items() if v is not None}
            
            ret = self.session.modify_order(**modify_params)
            logger.info(f"Order modified: {ret}")
            return ret
            
        except Exception as e:
            logger.error(f"Error modifying order: {e}")
            raise
    
    def cancel_order(self, order_id: str) -> Dict[str, Any]:
        """Cancel an order."""
        if not self.is_connected:
            raise RuntimeError("Not connected to Shoonya API")
        
        try:
            ret = self.session.cancel_order(orderno=order_id)
            logger.info(f"Order cancelled: {ret}")
            return ret
            
        except Exception as e:
            logger.error(f"Error cancelling order: {e}")
            raise
    
    def get_order_book(self) -> List[Dict[str, Any]]:
        """Get all orders for the day."""
        if not self.is_connected:
            raise RuntimeError("Not connected to Shoonya API")
        
        try:
            ret = self.session.get_order_book()
            return ret if ret else []
            
        except Exception as e:
            logger.error(f"Error fetching order book: {e}")
            return []
    
    def get_trade_book(self) -> List[Dict[str, Any]]:
        """Get all trades for the day."""
        if not self.is_connected:
            raise RuntimeError("Not connected to Shoonya API")
        
        try:
            ret = self.session.get_trade_book()
            return ret if ret else []
            
        except Exception as e:
            logger.error(f"Error fetching trade book: {e}")
            return []
    
    def get_positions(self) -> List[Dict[str, Any]]:
        """Get current positions."""
        if not self.is_connected:
            raise RuntimeError("Not connected to Shoonya API")
        
        try:
            ret = self.session.get_positions()
            return ret if ret else []
            
        except Exception as e:
            logger.error(f"Error fetching positions: {e}")
            return []
    
    def get_order_status(self, order_id: str) -> Dict[str, Any]:
        """Get status of a specific order."""
        if not self.is_connected:
            raise RuntimeError("Not connected to Shoonya API")
        
        try:
            ret = self.session.single_order_history(orderno=order_id)
            return ret if ret else {}
            
        except Exception as e:
            logger.error(f"Error fetching order status: {e}")
            return {}
    
    def get_quotes(self, exchange: str, token: str) -> Dict[str, Any]:
        """Get market quotes for a symbol."""
        if not self.is_connected:
            raise RuntimeError("Not connected to Shoonya API")
        
        try:
            ret = self.session.get_quotes(exchange=exchange, token=token)
            return ret if ret else {}
            
        except Exception as e:
            logger.error(f"Error fetching quotes: {e}")
            return {}
    
    def get_time_price_series(self, exchange: str, token: str, 
                             starttime: int, endtime: int, interval: int = 1) -> List[Dict]:
        """
        Get historical time-price series data.
        
        Args:
            exchange: Exchange code (NSE, NFO, etc.)
            token: Symbol token
            starttime: Start timestamp (seconds since epoch)
            endtime: End timestamp (seconds since epoch)
            interval: Interval in minutes (1, 3, 5, 10, 15, 30, 60, etc.)
        """
        if not self.is_connected:
            raise RuntimeError("Not connected to Shoonya API")
        
        try:
            ret = self.session.get_time_price_series(
                exchange=exchange,
                token=token,
                starttime=starttime,
                endtime=endtime,
                interval=interval
            )
            return ret if ret else []
            
        except Exception as e:
            logger.error(f"Error fetching time price series: {e}")
            return []
    
    def search_scrip(self, exchange: str, searchtext: str) -> List[Dict[str, Any]]:
        """Search for symbols."""
        if not self.is_connected:
            raise RuntimeError("Not connected to Shoonya API")
        
        try:
            ret = self.session.searchscrip(exchange=exchange, searchtext=searchtext)
            if ret and ret.get('stat') == 'Ok':
                return ret.get('values', [])
            return []
            
        except Exception as e:
            logger.error(f"Error searching scrip: {e}")
            return []
    
    def start_websocket(self, **callbacks):
        """Start WebSocket connection for live data."""
        if not self.is_connected:
            raise RuntimeError("Not connected to Shoonya API")
        
        try:
            self.session.start_websocket(**callbacks)
            logger.info("WebSocket connection started")
            
        except Exception as e:
            logger.error(f"Error starting WebSocket: {e}")
            raise
    
    def subscribe_symbols(self, symbols: List[str]):
        """Subscribe to market data for symbols."""
        try:
            self.session.subscribe(symbols)
            logger.info(f"Subscribed to: {symbols}")
            
        except Exception as e:
            logger.error(f"Error subscribing to symbols: {e}")
            raise
    
    def unsubscribe_symbols(self, symbols: List[str]):
        """Unsubscribe from market data."""
        try:
            self.session.unsubscribe(symbols)
            logger.info(f"Unsubscribed from: {symbols}")
            
        except Exception as e:
            logger.error(f"Error unsubscribing from symbols: {e}")
            raise
    
    def cancel_all_orders(self):
        """Cancel all pending orders."""
        try:
            orders = self.get_order_book()
            cancelled_orders = []
            
            for order in orders:
                if order.get('status') in ['OPEN', 'PENDING', 'TRIGGER_PENDING']:
                    result = self.cancel_order(order['norenordno'])
                    if result.get('stat') == 'Ok':
                        cancelled_orders.append(order['norenordno'])
            
            logger.info(f"Cancelled {len(cancelled_orders)} orders")
            return cancelled_orders
            
        except Exception as e:
            logger.error(f"Error cancelling all orders: {e}")
            return []
    
    def close_all_positions(self):
        """Close all open positions by placing opposite orders."""
        try:
            positions = self.get_positions()
            closed_positions = []
            
            for pos in positions:
                netqty = float(pos.get('netqty', 0))
                if netqty != 0:
                    # Place opposite order to close position
                    side = 'SELL' if netqty > 0 else 'BUY'
                    
                    order_details = {
                        'side': side,
                        'symbol': pos['tsym'],
                        'quantity': abs(int(netqty)),
                        'order_type': 'MKT',
                        'product_type': pos['prd'],
                        'exchange': pos['exch']
                    }
                    
                    result = self.place_order(order_details)
                    if result.get('stat') == 'Ok':
                        closed_positions.append(pos['tsym'])
            
            logger.info(f"Initiated closure for {len(closed_positions)} positions")
            return closed_positions
            
        except Exception as e:
            logger.error(f"Error closing all positions: {e}")
            return []
    
    def logout(self):
        """Logout from Shoonya API."""
        try:
            if self.session:
                ret = self.session.logout()
                self.is_connected = False
                logger.info("Logged out from Shoonya API")
                return ret
                
        except Exception as e:
            logger.error(f"Error during logout: {e}")
            return None