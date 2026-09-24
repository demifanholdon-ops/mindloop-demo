import json
from bleak import BleakClient, BleakScanner


class BLEDeviceAdapter:
    """Ready for the real wearable once BLE UUIDs are known."""

    def __init__(self, device_name="MindLoop", write_char_uuid=""):
        self.device_name = device_name
        self.write_char_uuid = write_char_uuid
        self.client = None

    async def discover(self):
        devices = await BleakScanner.discover(timeout=5)
        return [
            {"name": d.name or "", "address": d.address}
            for d in devices
            if self.device_name.lower() in (d.name or "").lower()
        ]

    async def connect(self, address):
        self.client = BleakClient(address)
        await self.client.connect()
        return self.client.is_connected

    async def send(self, command):
        if not self.client or not self.client.is_connected:
            raise RuntimeError("BLE device not connected")
        if not self.write_char_uuid:
            raise RuntimeError("BLE write UUID not configured")
        payload = (json.dumps(command, ensure_ascii=False) + "\n").encode("utf-8")
        await self.client.write_gatt_char(self.write_char_uuid, payload)
