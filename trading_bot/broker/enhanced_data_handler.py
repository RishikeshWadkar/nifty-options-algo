import json
import time
from datetime import datetime, time as dt_time
from typing import Any, List, Dict
from trading_bot.event import MarketEvent
from loguru import logger

class EnhancedDataHandler:
    """
    Enhanced data handler with reconnection logic, data validation,
    and market hours checking for Indian markets.
    """
    
    def __init__(self, api_wrapper: Any, event_queue: Any, symbols: List[str]):
        self.api_wrapper = api_wrapper
        self.event_queue = event_queue
        self.symbols = symbols
        self.ws_connected = False
        self.last_tick_time = {}
        self.reconnect_attempts = 0
        self.max_reconnect_attempts = 5
        
        # Indian market hours (IST)
        self.market_open = dt_time(9, 15)
        self.market_close = dt_time(15, 30)
    
    def is_market_hours(self) -> bool:
        """Check if current time is within market hours"""
        now = datetime.now().time()
        return self.market_open <= now <= self.market_close
    
    def start_with_reconnection(self):
        """Start data feed with automatic reconnection"""
        while self.reconnect_attempts < self.max_reconnect_attempts:
            try:
                if not self.is_market_hours():
                    logger.info("Outside market hours, waiting...")
                    time.sleep(60)
                    continue
                
                logger.info(f"Starting data handler (attempt {self.reconnect_attempts + 1})")
                
                # Start WebSocket connection
                self.api_wrapper.session.start_websocket(
                    subscribe_callback=self.on_tick_enhanced,
                    order_update_callback=self.on_order_update,
                    socket_open_callback=self.on_ws_open,
                    socket_close_callback=self.on_ws_close
                )
                
                # Wait for connection
                retry_count = 0
                while not self.ws_connected and retry_count < 30:
                    time.sleep(1)
                    retry_count += 1
                
                if self.ws_connected:
                    # Subscribe to symbols
                    formatted_symbols = [f"NSE|{symbol}" for symbol in self.symbols]
                    self.api_wrapper.session.subscribe(formatted_symbols)
                    logger.info(f"Subscribed to: {formatted_symbols}")
                    
                    # Reset reconnect counter on successful connection
                    self.reconnect_attempts = 0
                    
                    # Keep connection alive
                    self.keep_alive()
                else:
                    raise Exception("Failed to establish WebSocket connection")
                    
            except Exception as e:
                logger.error(f"Data handler error: {e}")
                self.reconnect_attempts += 1
                if self.reconnect_attempts < self.max_reconnect_attempts:
                    wait_time = min(60 * self.reconnect_attempts, 300)  # Max 5 min wait
                    logger.info(f"Reconnecting in {wait_time} seconds...")
                    time.sleep(wait_time)
                else:
                    logger.error("Max reconnection attempts reached. Stopping.")
                    break
    
    def keep_alive(self):
        """Keep the connection alive and monitor data flow"""
        last_heartbeat = datetime.now()
        
        while self.ws_connected and self.is_market_hours():
            time.sleep(1)
            
            # Check if we're still receiving data
            now = datetime.now()
            if (now - last_heartbeat).seconds > 30:
                # No data for 30 seconds, might be disconnected
                logger.warning("No data received for 30 seconds, checking connection...")
                if not self.ping_connection():
                    logger.error("Connection appears dead, will reconnect")
                    self.ws_connected = False
                    break
                last_heartbeat = now
    
    def ping_connection(self) -> bool:
        """Simple connection health check"""
        try:
            # You could implement a simple ping or just try to get quotes
            response = self.api_wrapper.session.get_quotes(exchange='NSE', token='26000')  # Nifty
            return response.get('stat') == 'Ok'
        except:
            return False
    
    def on_tick_enhanced(self, tick_data: dict):
        """Enhanced tick processing with validation"""
        try:
            # Validate tick data
            if not self.validate_tick_data(tick_data):
                return
            
            # Extract data
            symbol = tick_data.get('tsym', '').replace('-EQ', '').replace('-I', '')
            price = float(tick_data.get('lp', 0))
            volume = int(tick_data.get('v', 0))
            timestamp = datetime.now()  # Use system time for consistency
            
            # Create market event
            event = MarketEvent(
                symbol=symbol,
                timestamp=timestamp,
                price=price,
                volume=volume,
                ohlcv={
                    'open': float(tick_data.get('o', price)),
                    'high': float(tick_data.get('h', price)),
                    'low': float(tick_data.get('l', price)),
                    'close': price,
                    'volume': volume
                }
            )
            
            # Update last tick time for connection monitoring
            self.last_tick_time[symbol] = timestamp
            
            # Queue the event
            self.event_queue.put(event)
            
            if symbol == 'NIFTY':  # Log only major index for cleaner logs
                logger.debug(f"Tick: {symbol} @ {price}")
                
        except Exception as e:
            logger.error(f"Error processing tick: {e}, Data: {tick_data}")
    
    def validate_tick_data(self, tick_data: dict) -> bool:
        """Validate incoming tick data"""
        required_fields = ['tsym', 'lp']
        
        # Check required fields
        for field in required_fields:
            if field not in tick_data:
                logger.warning(f"Missing field {field} in tick data")
                return False
        
        # Validate price
        try:
            price = float(tick_data['lp'])
            if price <= 0:
                logger.warning(f"Invalid price: {price}")
                return False
        except (ValueError, TypeError):
            logger.warning(f"Invalid price format: {tick_data['lp']}")
            return False
        
        return True
    
    def on_ws_open(self):
        """WebSocket open callback"""
        logger.info("WebSocket connection established")
        self.ws_connected = True
    
    def on_ws_close(self):
        """WebSocket close callback"""
        logger.warning("WebSocket connection closed")
        self.ws_connected = False
    
    def on_order_update(self, order_data: dict):
        """Handle order updates from WebSocket"""
        logger.info(f"Order update: {json.dumps(order_data, indent=2)}")
