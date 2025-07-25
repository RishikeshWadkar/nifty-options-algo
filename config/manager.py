import yaml
import os
from typing import Dict, Any, List
from loguru import logger

class ConfigManager:
    """
    Centralized configuration management with environment-specific settings
    and credential security.
    """
    
    def __init__(self, config_path: str = 'config/config.yaml'):
        self.config_path = config_path
        self.config = self.load_config()
        self.validate_config()
    
    def load_config(self) -> Dict[str, Any]:
        """Load configuration from YAML file with environment variable support"""
        try:
            with open(self.config_path, 'r') as f:
                config = yaml.safe_load(f)
            
            # Replace environment variables
            config = self._replace_env_vars(config)
            
            logger.info(f"Configuration loaded from {self.config_path}")
            return config
            
        except FileNotFoundError:
            logger.error(f"Configuration file not found: {self.config_path}")
            raise
        except yaml.YAMLError as e:
            logger.error(f"Error parsing configuration file: {e}")
            raise
    
    def _replace_env_vars(self, config: Dict[str, Any]) -> Dict[str, Any]:
        """Replace ${ENV_VAR} patterns with environment variable values"""
        def replace_recursive(obj):
            if isinstance(obj, dict):
                return {k: replace_recursive(v) for k, v in obj.items()}
            elif isinstance(obj, list):
                return [replace_recursive(item) for item in obj]
            elif isinstance(obj, str) and obj.startswith('${') and obj.endswith('}'):
                env_var = obj[2:-1]
                return os.environ.get(env_var, obj)
            else:
                return obj
        
        return replace_recursive(config)
    
    def validate_config(self):
        """Validate required configuration parameters"""
        required_sections = ['shoonya', 'strategy', 'risk']
        required_shoonya_fields = ['user_id', 'password', 'api_key', 'api_secret', 'vendor_code']
        
        for section in required_sections:
            if section not in self.config:
                raise ValueError(f"Missing required configuration section: {section}")
        
        for field in required_shoonya_fields:
            if field not in self.config['shoonya']:
                raise ValueError(f"Missing required Shoonya field: {field}")
        
        logger.info("Configuration validation passed")
    
    def get(self, key_path: str, default=None):
        """Get configuration value using dot notation (e.g., 'shoonya.user_id')"""
        keys = key_path.split('.')
        value = self.config
        
        for key in keys:
            if isinstance(value, dict) and key in value:
                value = value[key]
            else:
                return default
        
        return value
    
    def get_trading_symbols(self) -> List[str]:
        """Get list of trading symbols with proper formatting"""
        symbols = self.get('strategy.symbols', ['NIFTY'])
        # Add exchange prefix if not present
        formatted_symbols = []
        for symbol in symbols:
            if '|' not in symbol:
                formatted_symbols.append(f"NSE|{symbol}")
            else:
                formatted_symbols.append(symbol)
        return formatted_symbols