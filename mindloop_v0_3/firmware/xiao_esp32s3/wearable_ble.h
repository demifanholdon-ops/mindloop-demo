#pragma once
#include <BLEDevice.h>
#include <ArduinoJson.h>

// Nordic UART matches the existing nRF52840 firmware. Notifications run on
// the BLE task: queue whole lines and serialize USB output only in loop().
namespace Wearable {
static const char *SERVICE = "6e400001-b5a3-f393-e0a9-e50e24dcca9e";
static const char *RX = "6e400002-b5a3-f393-e0a9-e50e24dcca9e";
static const char *TX = "6e400003-b5a3-f393-e0a9-e50e24dcca9e";
struct Line { char data[3600]; };
static QueueHandle_t events;
static BLEClient *client;
static BLERemoteCharacteristic *rx;
static Line incoming;
static size_t length = 0;
static bool overflow = false;
static uint32_t nextScan = 0;
static bool linked = false;
static bool agentReady = false;
static char agentState[24] = "waiting_cloud";
static uint32_t nextStatus = 0;
static portMUX_TYPE lock = portMUX_INITIALIZER_UNLOCKED;
static volatile bool lost = false;

static void notify(BLERemoteCharacteristic *, uint8_t *data, size_t size, bool) {
  for (size_t i = 0; i < size; ++i) {
    char c = data[i];
    if (c == '\n') {
      incoming.data[length] = 0;
      if (overflow || xQueueSend(events, &incoming, 0) != pdTRUE) {
        portENTER_CRITICAL(&lock); lost = true; portEXIT_CRITICAL(&lock);
      }
      length = 0; overflow = false;
    } else if (c != '\r') {
      if (length < sizeof(incoming.data) - 1) incoming.data[length++] = c;
      else overflow = true;
    }
  }
}

static bool send(const String &line) {
  if (!linked || !client->isConnected() || !rx) return false;
  String packet = line + '\n';
  size_t chunk = min((size_t)244, (size_t)(client->getMTU() - 3));
  for (size_t offset = 0; offset < packet.length(); offset += chunk) {
    size_t count = min(chunk, packet.length() - offset);
    if (!client->isConnected() || !rx->writeValue((uint8_t *)packet.c_str() + offset, count, true)) {
      // Never continue a partially transmitted JSON line on this connection.
      client->disconnect();
      return false;
    }
  }
  return true;
}

static void setAgentReady(bool ready) {
  agentReady = ready;
  nextStatus = 0;
}

static void setAgentState(const char *state) {
  const char *next = state ? state : "waiting_cloud";
  if (!strcmp(agentState, next)) return;
  strlcpy(agentState, next, sizeof(agentState));
  nextStatus = 0;
}

static void begin() {
  events = xQueueCreate(8, sizeof(Line));
  if (!events) { Serial.println("{\"event\":\"error\",\"reason\":\"ble_queue_allocation\"}"); return; }
  BLEDevice::init("MindLoop-S3");
  client = BLEDevice::createClient();
  BLEDevice::getScan()->setActiveScan(true);
}

static void poll() {
  if (!events || !client) return;
  Line line;
  while (xQueueReceive(events, &line, 0) == pdTRUE) {
    JsonDocument payload;
    if (deserializeJson(payload, line.data)) {
      Serial.println("{\"event\":\"error\",\"reason\":\"invalid_wearable_json\"}");
      continue;
    }
    JsonDocument event;
    event["event"] = "wearable";
    event["payload"].set(payload.as<JsonVariant>());
    serializeJson(event, Serial); Serial.println();
  }
  portENTER_CRITICAL(&lock); bool dropped = lost; lost = false; portEXIT_CRITICAL(&lock);
  if (dropped) Serial.println("{\"event\":\"error\",\"reason\":\"wearable_rx_overflow\"}");
  if (linked && !client->isConnected()) {
    linked = false; rx = nullptr;
    Serial.println("{\"event\":\"ble_disconnected\"}");
    nextScan = millis() + 3000;
  }
  if (linked && client->isConnected() && (int32_t)(millis() - nextStatus) >= 0) {
    String status = String("{\"cmd\":\"gateway_status\",\"gateway_linked\":true,\"agent_ready\":") +
                    (agentReady ? "true" : "false") + ",\"state\":\"" + agentState + "\"}";
    if (!send(status)) Serial.println("{\"event\":\"error\",\"reason\":\"gateway_status_failed\"}");
    nextStatus = millis() + 3000;
  }
  if (linked || (int32_t)(millis() - nextScan) < 0 || Serial.available()) return;
  BLEScan *scan = BLEDevice::getScan();
  BLEScanResults *results = scan->start(2, false);
  if (results) for (int i = 0; i < results->getCount(); ++i) {
    BLEAdvertisedDevice device = results->getDevice(i);
    // Scan responses may be lost in a crowded RF environment. A missing
    // name must not hide a peripheral advertising the required service.
    if (!device.isAdvertisingService(BLEUUID(SERVICE))) continue;
    if (device.haveName() && device.getName() != "MindLoop") continue;
    length = 0; overflow = false;
    Serial.println("{\"event\":\"ble_connecting\"}");
    if (!client->connect(device.getAddress(), device.getAddressType(), 5000)) {
      Serial.println("{\"event\":\"error\",\"reason\":\"ble_connect_failed\"}");
      break;
    }
    client->updateConnParams(6, 12, 0, 400);
    client->setMTU(247);
    BLERemoteService *service = client->getService(SERVICE);
    rx = service ? service->getCharacteristic(RX) : nullptr;
    BLERemoteCharacteristic *tx = service ? service->getCharacteristic(TX) : nullptr;
    if (!rx || !rx->canWrite() || !tx || !tx->canNotify()) {
      client->disconnect(); rx = nullptr;
      Serial.println("{\"event\":\"error\",\"reason\":\"wearable_service_missing\"}");
      break;
    }
    tx->registerForNotify(notify);
    linked = true;
    nextStatus = 0;
    Serial.printf("{\"event\":\"ble_connected\",\"mtu\":%u}\n", client->getMTU());
    if (!send("{\"cmd\":\"hello\",\"role\":\"gateway\",\"agent_ready\":false}"))
      Serial.println("{\"event\":\"error\",\"reason\":\"wearable_write_failed\"}");
    break;
  }
  scan->clearResults();
  nextScan = millis() + 3000;
}
}
