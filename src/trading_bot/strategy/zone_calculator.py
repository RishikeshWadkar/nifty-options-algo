from typing import Dict
from datetime import datetime, time
from loguru import logger

class ZoneCalculator:
    """Calculate zones based on 9:16 AM INDEX price for Nifty Small SL Algo"""
    
    def __init__(self, zone_offset: float = 2.5):
        self.zone_offset = zone_offset
        self.zones_calculated = False
        self.calculation_time = time(9, 16, 0)
    
    def calculate_zones_at_916(self, index_price: float) -> Dict[str, float]:
        """Calculate zones based on INDEX price at 9:16 AM"""
        zones = {
            'middle_zone': index_price,
            'upper_zone': index_price + self.zone_offset,  # CE entry
            'lower_zone': index_price - self.zone_offset,  # PE entry
            'calculation_time': datetime.now(),
            'base_price': index_price
        }
        
        self.zones_calculated = True
        logger.info(f"Zones calculated at 9:16 AM - Upper: {zones['upper_zone']}, Middle: {zones['middle_zone']}, Lower: {zones['lower_zone']}")
        
        return zones
    
    def should_calculate_zones(self, current_time: time) -> bool:
        """Check if it's time to calculate zones (9:16 AM)"""
        return (current_time >= self.calculation_time and 
                current_time <= time(9, 16, 10) and 
                not self.zones_calculated)