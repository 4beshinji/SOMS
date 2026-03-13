"""
GM65 Barcode Scanner Driver for MicroPython — UART interface.

Reads barcode/QR code data from GM65 module.
Default baud rate: 9600, 8N1.
"""
from machine import UART
import time


class GM65:
    """GM65 barcode scanner driver using UART."""

    def __init__(self, uart_id=2, tx_pin=17, rx_pin=16, baudrate=9600):
        self._uart = UART(uart_id, baudrate=baudrate, tx=tx_pin, rx=rx_pin)
        self._buffer = b""

    def read_barcode(self, timeout_ms=100):
        """Read a barcode string if available.

        Returns the barcode string, or None if no data.
        The GM65 sends barcode data terminated by CR+LF.
        """
        deadline = time.ticks_add(time.ticks_ms(), timeout_ms)
        while time.ticks_diff(deadline, time.ticks_ms()) > 0:
            if self._uart.any():
                data = self._uart.read()
                if data:
                    self._buffer += data
            time.sleep_ms(10)

        if b"\r\n" in self._buffer:
            line, self._buffer = self._buffer.split(b"\r\n", 1)
            barcode = line.decode("utf-8", "ignore").strip()
            if barcode:
                return barcode

        # Also handle LF-only termination
        if b"\n" in self._buffer:
            line, self._buffer = self._buffer.split(b"\n", 1)
            barcode = line.decode("utf-8", "ignore").strip()
            if barcode:
                return barcode

        return None

    def read_sensor(self):
        """Standard sensor interface — returns dict for SensorRegistry."""
        barcode = self.read_barcode()
        if barcode:
            return {"barcode": barcode}
        return {}
