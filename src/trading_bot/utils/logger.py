import sys
import os
from datetime import datetime
from loguru import logger

def setup_logger(log_dir: str = "logs", log_level: str = "INFO") -> None:
    """
    Sets up structured logging for the trading bot using Loguru.
    Logs are written in JSON format to both console and a daily rotating file.

    Args:
        log_dir (str): Directory to store log files.
        log_level (str): Logging level (e.g., 'INFO', 'DEBUG').
    """
    os.makedirs(log_dir, exist_ok=True)
    log_file = os.path.join(log_dir, f"trading_bot_{datetime.now().strftime('%Y%m%d')}.log")
    logger.remove()
    logger.add(sys.stdout, level=log_level, serialize=True, enqueue=True)
    logger.add(log_file, level=log_level, serialize=True, rotation="1 day", retention="7 days", enqueue=True)
    logger.info("Structured logger initialized.") 