import json
import time
import threading
from datetime import datetime, time as dt_time
from typing import Any, List, Dict, Optional
from loguru import logger

from trading_bot.event import MarketEvent
from trading_bot.event_queue import EventQueue

class DataHandler:
    """
    Data handler with reconnection logic, data validation,
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
        self.heartbeat_thread = None
        self.running = False
        
        # Indian market hours (IST)
        self.market_open = dt_time(9, 15)
        self.market_close = dt_time(15, 30)
    
    def is_market_hours(self) -> bool:
        """Check if current time is within market hours"""
        now = datetime.now().time()
        return self.market_open <= now <= self.market_close
    
    def start_with_reconnection(self):
        """Start data feed with automatic reconnection"""
        self.running = True
        while self.running and self.reconnect_attempts < self.max_reconnect_attempts:
            try:
                if not self.is_market_hours():
                    logger.info("Outside market hours, waiting...")
                    time.sleep(60)
                    continue
                
                logger.info(f"Starting data handler (attempt {self.reconnect_attempts + 1}/{self.max_reconnect_attempts})")
                
                # Start WebSocket connection
                self.api_wrapper.start_websocket(
                    subscribe_callback=self.on_tick,
                    order_update_callback=self.on_order_update,
                    socket_open_callback=self.on_ws_open,
                    socket_close_callback=self.on_ws_close
                )
                
                # Wait for connection
                retry_count = 0
                while not self.ws_connected and retry_count < 30 and self.running:
                    time.sleep(1)
                    retry_count += 1
                
                if self.ws_connected:
                    # Subscribe to symbols
                    formatted_symbols = []
                    for symbol in self.symbols:
                        # Format for index symbols
                        if symbol in ['NIFTY', 'BANKNIFTY']:
                            formatted_symbols.append(f"NSE|{symbol}")
                        # Format for option symbols (if needed)
                        elif 'CE' in symbol or 'PE' in symbol:
                            formatted_symbols.append(f"NFO|{symbol}")
                        else:
                            formatted_symbols.append(f"NSE|{symbol}")
                    
                    self.api_wrapper.subscribe_symbols(formatted_symbols)
                    logger.info(f"Subscribed to: {formatted_symbols}")
                    
                    # Reset reconnect counter on successful connection
                    self.reconnect_attempts = 0
                    
                    # Start heartbeat thread
                    self.start_heartbeat_monitor()
                    
                    # Keep connection alive
                    while self.ws_connected and self.running and self.is_market_hours():
                        time.sleep(1)
                else:
                    raise Exception("Failed to establish WebSocket connection")
                    
            except Exception as e:
                logger.error(f"Data handler error: {e}")
                self.reconnect_attempts += 1
                if self.reconnect_attempts < self.max_reconnect_attempts and self.running:
                    wait_time = min(60 * self.reconnect_attempts, 300)  # Max 5 min wait
                    logger.info(f"Reconnecting in {wait_time} seconds...")
                    time.sleep(wait_time)
                else:
                    logger.error("Max reconnection attempts reached. Stopping.")
                    break
    
    def start_heartbeat_monitor(self):
        """Start a separate thread to monitor connection health"""
        if self.heartbeat_thread and self.heartbeat_thread.is_alive():
            return
            
        self.heartbeat_thread = threading.Thread(
            target=self._heartbeat_monitor,
            daemon=True,
            name="WebSocketHeartbeat"
        )
        self.heartbeat_thread.start()
    
    def _heartbeat_monitor(self):
        """Monitor WebSocket connection health"""
        last_heartbeat = datetime.now()
        
        while self.ws_connected and self.running:
            time.sleep(5)  # Check every 5 seconds
            
            now = datetime.now()
            # Check if we've received data recently for any symbol
            most_recent = max(self.last_tick_time.values()) if self.last_tick_time else last_heartbeat
            
            if (now - most_recent).seconds > 30:
                # No data for 30 seconds, check connection
                logger.warning("No data received for 30 seconds, checking connection...")
                if not self.ping_connection():
                    logger.error("Connection appears dead, will reconnect")
                    self.ws_connected = False
                    break
                last_heartbeat = now
    
    def ping_connection(self) -> bool:
        """Simple connection health check"""
        try:
            # Try to get quotes for Nifty index
            response = self.api_wrapper.get_quotes(exchange='NSE', token='26000')  # Nifty
            return response and response.get('stat') == 'Ok'
        except Exception as e:
            logger.error(f"Ping connection failed: {e}")
            return False
    
    def on_tick(self, tick_data: dict):
        """Enhanced tick processing with validation"""
        try:
            # Validate tick data
            if not self.validate_tick_data(tick_data):
                return
            
            # Extract data
            symbol = tick_data.get('tsym', '').replace('-EQ', '').replace('-I', '')
            price = float(tick_data.get('lp', 0))
            volume = int(tick_data.get('v', 0)) if tick_data.get('v') else 0
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
            
            if symbol in ['NIFTY', 'BANKNIFTY']:  # Log only major indices for cleaner logs
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
    
    def stop(self):
        """Stop the data handler and close connections"""
        self.running = False
        self.ws_connected = False
        logger.info("Data handler stopping...")