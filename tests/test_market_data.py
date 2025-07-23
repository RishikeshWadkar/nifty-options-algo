import pytest
from datetime import datetime
from src.models.market_data import MarketTick
from src.data.data_store import MarketDataStore

@pytest.fixture
def data_store():
    """Fixture to create a test database"""
    store = MarketDataStore(":memory:")
    return store

def test_market_data_storage(data_store):
    # Create sample tick
    tick = MarketTick(
        symbol="NIFTY-I",
        ltp=19500.0,
        timestamp=datetime.now(),
        volume=100,
        oi=1000
    )
    
    # Store and retrieve
    data_store.store_tick(tick)
    last_price = data_store.get_last_price("NIFTY-I")
    assert last_price == 19500.0

def test_ohlcv_data(data_store):
    """Test OHLCV data aggregation"""
    start_time = datetime.now()
    
    # Insert some test ticks
    ticks = [
        MarketTick("NIFTY-I", 19500.0, start_time, 100, 1000),
        MarketTick("NIFTY-I", 19550.0, start_time.replace(second=30), 150, 1100),
        MarketTick("NIFTY-I", 19525.0, start_time.replace(minute=1), 200, 1200)
    ]
    
    for tick in ticks:
        data_store.store_tick(tick)
    
    # Get 1-minute OHLCV data
    ohlcv = data_store.get_ohlcv_data(
        symbol="NIFTY-I",
        start_time=start_time,
        end_time=start_time.replace(minute=2),
        interval='1min'
    )
    
    assert not ohlcv.empty
    assert len(ohlcv) > 0