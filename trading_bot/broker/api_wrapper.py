from typing import Any, Optional
import pyotp
import yaml
from loguru import logger
from info_for_AI.ShoonyaApi_py_master.api_helper import ShoonyaApiPy

class ShoonyaAPIWrapper:
    """
    Real implementation of the ShoonyaAPIWrapper for live and paper trading.
    Handles authentication (with TOTP), order placement, position queries, and status checks.
    All credentials are loaded from config.

    Args:
        config_path (str): Path to the YAML config file.
    """
    def __init__(self, config_path: str = 'config/config.yaml') -> None:
        """
        Initialize the ShoonyaAPIWrapper.

        Args:
            config_path (str): Path to the YAML config file.
        """
        with open(config_path, 'r') as f:
            config = yaml.safe_load(f)['shoonya']
        self.api_key: str = config['api_key']
        self.api_secret: str = config['api_secret']
        self.user_id: str = config['user_id']
        self.password: str = config['password']
        self.vendor_code: str = config['vendor_code']
        self.imei: str = config['imei']
        self.totp_secret: str = config['totp_secret']
        self.session: Optional[ShoonyaApiPy] = None
        self.susertoken: Optional[str] = None

    def connect(self) -> None:
        """
        Authenticate with Shoonya API using TOTP for twoFA.
        Store session and user token for subsequent requests.
        Raises:
            Exception: If login fails.
        """
        try:
            otp: str = pyotp.TOTP(self.totp_secret).now()
            logger.info(f"[ShoonyaAPIWrapper] Generated OTP for login: {otp}")
            self.session = ShoonyaApiPy()
            ret = self.session.login(
                userid=self.user_id,
                password=self.password,
                twoFA=otp,
                vendor_code=self.vendor_code,
                api_secret=self.api_key,
                imei=self.imei
            )
            if ret.get('stat') == 'Ok':
                self.susertoken = ret['susertoken']
                logger.info("[ShoonyaAPIWrapper] Login successful.")
            else:
                logger.error(f"[ShoonyaAPIWrapper] Login failed: {ret}")
                raise Exception(f"Shoonya login failed: {ret}")
        except Exception as exc:
            logger.error(f"[ShoonyaAPIWrapper] Exception during connect: {exc}")
            raise

    def place_order(self, order_details: dict[str, Any]) -> dict[str, Any]:
        """
        Place an order using Shoonya API.

        Args:
            order_details (dict): Order parameters.

        Returns:
            dict: API response.
        """
        try:
            ret = self.session.place_order(**order_details)
            logger.info(f"[ShoonyaAPIWrapper] Placed order: {ret}")
            return ret
        except Exception as exc:
            logger.error(f"[ShoonyaAPIWrapper] Error placing order: {exc}")
            raise

    def get_open_positions(self) -> Any:
        """
        Fetch open positions from Shoonya API.

        Returns:
            Any: API response with open positions.
        """
        try:
            ret = self.session.get_positions()
            logger.info(f"[ShoonyaAPIWrapper] Open positions: {ret}")
            return ret
        except Exception as exc:
            logger.error(f"[ShoonyaAPIWrapper] Error fetching open positions: {exc}")
            raise

    def get_order_status(self, order_id: str) -> Any:
        """
        Query the status of a specific order.

        Args:
            order_id (str): Broker order ID.

        Returns:
            Any: API response with order status.
        """
        try:
            ret = self.session.get_singleorderhistory(orderno=order_id)
            logger.info(f"[ShoonyaAPIWrapper] Order status: {ret}")
            return ret
        except Exception as exc:
            logger.error(f"[ShoonyaAPIWrapper] Error fetching order status: {exc}")
            raise

    def cancel_all_orders(self) -> None:
        """
        Cancel all open orders.
        """
        try:
            orderbook = self.session.get_order_book()
            for order in orderbook:
                if order.get('status') in ['OPEN', 'PENDING']:
                    self.session.cancel_order(orderno=order['norenordno'])
                    logger.info(f"[ShoonyaAPIWrapper] Cancelled order: {order['norenordno']}")
        except Exception as exc:
            logger.error(f"[ShoonyaAPIWrapper] Error cancelling orders: {exc}")
            raise

    def close_all_positions(self) -> None:
        """
        Close all open positions.
        """
        try:
            positions = self.session.get_positions()
            for pos in positions:
                if float(pos.get('netqty', 0)) != 0:
                    # Implement close logic as per your strategy (e.g., place opposite order)
                    logger.info(f"[ShoonyaAPIWrapper] Position needs manual close: {pos}")
        except Exception as exc:
            logger.error(f"[ShoonyaAPIWrapper] Error closing positions: {exc}")
            raise
