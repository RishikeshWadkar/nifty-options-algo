import yaml
from pathlib import Path
from .broker.shoonya_wrapper import ShoonyaWrapper
from .data.data_store import MarketDataStore
from .models.market_data import MarketTick

class TradingApp:
    def __init__(self, config_path: str = "config/config.yaml"):
        self.config = self._load_config(config_path)
        self.broker = ShoonyaWrapper(self.config['broker'])
        self.data_store = MarketDataStore(self.config['data']['db_path'])
        
    def _load_config(self, config_path: str) -> dict:
        with open(config_path, 'r') as f:
            return yaml.safe_load(f)
            
    def start(self):
        """Start the trading application"""
        # Connect to broker
        if not self.broker.connect():
            raise RuntimeError("Failed to connect to broker")
            
        # Subscribe to symbols
        self.broker.subscribe_symbols(self.config['data']['symbols'])