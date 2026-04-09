"""
HX711 ADC Driver for MicroPython — GPIO bit-bang implementation.

Reads 24-bit ADC values from HX711 load cell amplifier.
Supports gain selection (128/64 for channel A, 32 for channel B).
"""
from machine import Pin
import time


class HX711:
    """HX711 load cell amplifier driver using GPIO bit-bang."""

    # Gain pulses: 25=128(A), 26=32(B), 27=64(A)
    GAIN_128 = 25
    GAIN_64 = 27
    GAIN_32 = 26

    def __init__(self, dout_pin, sck_pin, gain=GAIN_128):
        """
        Args:
            dout_pin: GPIO pin number for DOUT (data out)
            sck_pin: GPIO pin number for PD_SCK (clock)
            gain: Number of clock pulses (25/26/27) for gain selection
        """
        self._dout = Pin(dout_pin, Pin.IN)
        self._sck = Pin(sck_pin, Pin.OUT, value=0)
        self._gain = gain
        self._offset = 0
        self._scale = 1.0

    def is_ready(self):
        """Check if HX711 has data ready (DOUT goes LOW)."""
        return self._dout.value() == 0

    def _read_raw(self):
        """Read raw 24-bit signed value from HX711."""
        # Wait for ready (DOUT LOW), timeout 1s
        t0 = time.ticks_ms()
        while not self.is_ready():
            if time.ticks_diff(time.ticks_ms(), t0) > 1000:
                raise OSError("HX711 timeout: not ready")
            time.sleep_us(10)

        # Read 24 bits, MSB first
        value = 0
        for _ in range(24):
            self._sck.value(1)
            time.sleep_us(1)
            value = (value << 1) | self._dout.value()
            self._sck.value(0)
            time.sleep_us(1)

        # Send extra pulses for gain selection (next read)
        for _ in range(self._gain - 24):
            self._sck.value(1)
            time.sleep_us(1)
            self._sck.value(0)
            time.sleep_us(1)

        # Convert from 24-bit two's complement
        if value & 0x800000:
            value -= 0x1000000

        return value

    def tare(self, readings=10):
        """Set the zero offset by averaging multiple readings."""
        total = 0
        for _ in range(readings):
            total += self._read_raw()
            time.sleep_ms(50)
        self._offset = total / readings

    def set_scale(self, scale):
        """Set the scale factor (raw units per gram)."""
        self._scale = scale

    def read_weight(self, readings=3):
        """Read weight in grams (averaged over multiple readings).

        Returns:
            Weight in grams (float), or None on read failure.
        """
        try:
            total = 0
            for _ in range(readings):
                total += self._read_raw()
                time.sleep_ms(20)
            raw_avg = total / readings
            return (raw_avg - self._offset) / self._scale
        except OSError:
            return None

    def read_sensor(self):
        """Standard sensor interface — returns dict for SensorRegistry."""
        weight = self.read_weight()
        if weight is not None:
            return {"weight": round(weight, 1)}
        return {}

    def calibrate(self, known_weight_g, readings=10):
        """Calculate scale factor using a known weight.

        Place a known weight on the sensor AFTER calling tare() on empty,
        then call this method. Returns the computed scale factor.

        Args:
            known_weight_g: Actual weight of the calibration object in grams.
            readings: Number of readings to average.
        Returns:
            Computed scale factor (raw units per gram).
        """
        if known_weight_g <= 0:
            raise ValueError("known_weight_g must be positive")
        total = 0
        for _ in range(readings):
            total += self._read_raw()
            time.sleep_ms(50)
        raw_avg = total / readings
        self._scale = (raw_avg - self._offset) / known_weight_g
        return self._scale

    def read_raw_avg(self, readings=10):
        """Read averaged raw ADC value (for multi-point calibration)."""
        total = 0
        for _ in range(readings):
            total += self._read_raw()
            time.sleep_ms(50)
        return total / readings

    def calibrate_multi(self, points):
        """Multi-point least-squares calibration.

        Args:
            points: list of (known_weight_g, raw_avg) tuples.
                    Must include at least 2 points (e.g., 0g and one known weight).
        Sets offset and scale via linear regression: raw = scale * weight + offset.
        Returns: (offset, scale) tuple.
        """
        n = len(points)
        if n < 2:
            raise ValueError("Need at least 2 calibration points")
        sum_w = sum(p[0] for p in points)
        sum_r = sum(p[1] for p in points)
        sum_wr = sum(p[0] * p[1] for p in points)
        sum_ww = sum(p[0] * p[0] for p in points)
        denom = n * sum_ww - sum_w * sum_w
        if abs(denom) < 1e-10:
            raise ValueError("Degenerate calibration points")
        # Linear fit: raw = scale * weight + offset
        scale = (n * sum_wr - sum_w * sum_r) / denom
        offset = (sum_r - scale * sum_w) / n
        self._scale = scale
        self._offset = offset
        return offset, scale

    def get_calibration(self):
        """Return current calibration parameters."""
        return {"offset": self._offset, "scale": self._scale}

    def save_calibration(self, path="/calibration.json"):
        """Persist calibration to filesystem (NVS)."""
        import json
        data = {"offset": self._offset, "scale": self._scale}
        with open(path, "w") as f:
            json.dump(data, f)

    def load_calibration(self, path="/calibration.json"):
        """Load calibration from filesystem. Returns True on success."""
        import json
        try:
            with open(path, "r") as f:
                data = json.load(f)
            self._offset = data["offset"]
            self._scale = data["scale"]
            return True
        except (OSError, KeyError, ValueError):
            return False

    def power_down(self):
        """Put HX711 into low-power mode."""
        self._sck.value(0)
        self._sck.value(1)
        time.sleep_us(100)

    def power_up(self):
        """Wake HX711 from low-power mode."""
        self._sck.value(0)
        time.sleep_ms(50)
