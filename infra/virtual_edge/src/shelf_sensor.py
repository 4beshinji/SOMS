"""
VirtualShelfSensor — simulates gradual weight decrease on a shelf.

Starts at a configured initial weight and slowly decreases over time,
simulating consumption of consumable items. Periodically "restocks"
to simulate replenishment. Optionally simulates barcode scans.
"""
import random
import logging
from device import VirtualDevice

# Simulated barcode catalog for virtual scans
_VIRTUAL_BARCODES = [
    ("4901234567890", "コーヒー豆 200g"),
    ("4902345678901", "紅茶ティーバッグ"),
    ("4903456789012", "砂糖 1kg"),
]

logger = logging.getLogger(__name__)


class VirtualShelfSensor(VirtualDevice):
    """Simulates a shelf with HX711 weight sensor."""

    def __init__(
        self,
        client,
        device_id: str = "shelf_01",
        zone: str = "kitchen",
        initial_weight_g: float = 650.0,
        tare_weight_g: float = 50.0,
        consumption_rate_g: float = 5.0,
        restock_threshold_g: float = 80.0,
        restock_weight_g: float = 650.0,
        barcode_scan_interval: int = 200,
    ):
        topic_prefix = f"office/{zone}/sensor/{device_id}"
        super().__init__(device_id, topic_prefix, client)

        self._zone = zone
        self._weight = initial_weight_g
        self._tare = tare_weight_g
        self._consumption_rate = consumption_rate_g
        self._restock_threshold = restock_threshold_g
        self._restock_weight = restock_weight_g
        self._tick = 0
        self._barcode_scan_interval = barcode_scan_interval

        self._calibrated_offset = 0.0
        self._calibrated_scale = 1.0

        self.register_tool("get_status", self.get_status)
        self.register_tool("tare", self.tare)
        self.register_tool("calibrate", self.calibrate)

    def get_status(self):
        return {"weight": round(self._weight, 1)}

    def tare(self, readings=20):
        """Virtual tare — record current weight as zero offset."""
        self._calibrated_offset = self._weight
        return {
            "status": "ok",
            "offset": self._calibrated_offset,
            "scale": self._calibrated_scale,
        }

    def calibrate(self, known_weight_g, readings=10):
        """Virtual calibration — compute scale from known weight."""
        if known_weight_g <= 0:
            return {"status": "error", "message": "known_weight_g must be positive"}
        self._calibrated_scale = (self._weight - self._calibrated_offset) / known_weight_g
        return {
            "status": "ok",
            "scale": self._calibrated_scale,
            "offset": self._calibrated_offset,
        }

    def update(self):
        self._tick += 1

        # Simulate gradual consumption with noise
        consumption = self._consumption_rate * random.uniform(0.5, 1.5)
        self._weight -= consumption

        # Add small sensor noise (±0.5g)
        noise = random.uniform(-0.5, 0.5)

        # Clamp to tare minimum
        if self._weight < self._tare:
            self._weight = self._tare

        # Auto-restock every ~100 ticks when weight drops low
        if self._weight <= self._restock_threshold and self._tick % 100 == 0:
            self._weight = self._restock_weight
            logger.info(
                "[%s] Restocked to %.1fg", self.device_id, self._weight,
            )

        # Publish weight reading
        reported = round(self._weight + noise, 1)
        self.publish_sensor_data({"weight": reported})

        # Simulate occasional barcode scan
        if self._barcode_scan_interval > 0 and self._tick % self._barcode_scan_interval == 0:
            barcode, name = random.choice(_VIRTUAL_BARCODES)
            self.publish_sensor_data({"barcode": barcode})
            logger.info("[%s] Virtual barcode scan: %s (%s)", self.device_id, barcode, name)
