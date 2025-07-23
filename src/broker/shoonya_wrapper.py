from typing import Dict, Optional
from NorenRestApiPy.NorenApi import NorenApi
from ..models.market_data import MarketTick

class ShoonyaWrapper:
    def __init__(self, config: Dict):
        self.api = NorenApi()
        self.config = config
        self._session_token = None
        
    def connect(self) -> bool:
        """Initialize connection with Shoonya"""
        try:
            response = self.api.login(
                userid=self.config['client_id'],
                password=self.config['password'],
                twoFA=self.config['totp_key'],
                vendor_code=self.config['vendor_code'],
                api_secret=self.config['api_secret'],
                imei="test123"
            )
            self._session_token = response.get('susertoken')
            return bool(self._session_token)
        except Exception as e:
            print(f"Login failed: {e}")
            return False

    def subscribe_symbols(self, symbols: list) -> None:
        """Subscribe to market data for given symbols"""
        if not self._session_token:
            raise ValueError("Not connected to Shoonya")
        
        for symbol in symbols:
            self.api.subscribe(symbol)