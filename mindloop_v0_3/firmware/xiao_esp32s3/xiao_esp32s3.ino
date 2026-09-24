#include <Arduino.h>
#include <Wire.h>
#include <ArduinoJson.h>
#include <ESP_I2S.h>
#include "wearable_ble.h"
#include "standalone_config.h"

// USB control and Nordic UART BLE Central for the nRF52840 wearable, plus a
// bench diagnostic path for the DRV2605L haptic driver wired to the reSpeaker
// Flex header. Nothing here drives the motor unless a haptic command arrives.
unsigned long lastHeartbeat = 0;
unsigned long sequence = 0;
I2SClass audioI2s;
bool audioI2sReady = false;

// reSpeaker Flex official examples use the XIAO default Wire bus (GPIO5/6),
// the same bus that configures the XVF3800 (slave 0x2C).
constexpr uint8_t DRV2605_ADDR = 0x5A;
constexpr uint8_t DRV_STATUS = 0x00;
constexpr uint8_t DRV_MODE = 0x01;
constexpr uint8_t DRV_RTP = 0x02;
constexpr uint8_t DRV_LIBRARY = 0x03;
constexpr uint8_t DRV_SEQ1 = 0x04;
constexpr uint8_t DRV_SEQ2 = 0x05;
constexpr uint8_t DRV_SEQ3 = 0x06;
constexpr uint8_t DRV_GO = 0x0C;
constexpr uint8_t DRV_FEEDBACK = 0x1A;

void emit(const String &json) {
  Serial.println(json);
}

String hexByte(uint8_t value) {
  char buffer[6];
  snprintf(buffer, sizeof(buffer), "0x%02X", value);
  return String(buffer);
}

void beginHapticBus() {
  Wire.begin(SDA, SCL, 100000);
  Wire.setTimeOut(50);
}

bool drvAck() {
  Wire.beginTransmission(DRV2605_ADDR);
  return Wire.endTransmission() == 0;
}

bool drvWrite(uint8_t reg, uint8_t value) {
  Wire.beginTransmission(DRV2605_ADDR);
  Wire.write(reg);
  Wire.write(value);
  return Wire.endTransmission() == 0;
}

// 0 on success; otherwise the Wire error code (1-5), 100 for a short read.
int busRead(uint8_t addr, uint8_t reg, uint8_t *out, size_t length) {
  Wire.beginTransmission(addr);
  Wire.write(reg);
  int error = Wire.endTransmission(false);
  if (error) return error;
  if (Wire.requestFrom(addr, (uint8_t)length) != (int)length) return 100;
  for (size_t i = 0; i < length; ++i) out[i] = Wire.read();
  return 0;
}

void addDrvRegisters(JsonObject target) {
  uint8_t status = 0, mode = 0, library = 0, feedback = 0;
  int statusError = busRead(DRV2605_ADDR, DRV_STATUS, &status, 1);
  int modeError = busRead(DRV2605_ADDR, DRV_MODE, &mode, 1);
  int libraryError = busRead(DRV2605_ADDR, DRV_LIBRARY, &library, 1);
  int feedbackError = busRead(DRV2605_ADDR, DRV_FEEDBACK, &feedback, 1);
  if (!statusError) {
    target["status"] = status;
    target["device_id"] = status >> 5;
  }
  if (!modeError) target["mode"] = mode;
  if (!libraryError) target["library"] = library;
  if (!feedbackError) target["feedback"] = feedback;
  JsonArray errors = target["read_errors"].to<JsonArray>();
  errors.add(statusError);
  errors.add(modeError);
  errors.add(libraryError);
  errors.add(feedbackError);
}

// Releases the bus and samples both lines as plain inputs, so the wiring and
// any external load can be checked without a multimeter. ADC range is 3.3 V.
void sampleBusLevels(int &sdaDigital, int &sclDigital, uint16_t &sdaMv, uint16_t &sclMv) {
  Wire.end();
  pinMode(SDA, INPUT);
  pinMode(SCL, INPUT);
  delay(2);
  sdaDigital = digitalRead(SDA);
  sclDigital = digitalRead(SCL);
  uint32_t sda = 0, scl = 0;
  for (int i = 0; i < 8; ++i) {
    sda += analogReadMilliVolts(SDA);
    scl += analogReadMilliVolts(SCL);
    delay(1);
  }
  sdaMv = (uint16_t)(sda / 8);
  sclMv = (uint16_t)(scl / 8);
}

void scanHapticBus() {
  int idleSda = 0, idleScl = 0;
  uint16_t sdaMv = 0, sclMv = 0;
  sampleBusLevels(idleSda, idleScl, sdaMv, sclMv);
  beginHapticBus();
  JsonDocument result;
  result["event"] = "i2c_scan";
  result["sda_gpio"] = SDA; result["scl_gpio"] = SCL;
  result["sda_level"] = digitalRead(SDA); result["scl_level"] = digitalRead(SCL);
  result["idle_sda_level"] = idleSda; result["idle_scl_level"] = idleScl;
  result["sda_mv"] = sdaMv; result["scl_mv"] = sclMv;
  JsonArray addresses = result["addresses"].to<JsonArray>();
  JsonArray labels = result["addresses_hex"].to<JsonArray>();
  for (uint8_t addr = 8; addr < 120; ++addr) {
    Wire.beginTransmission(addr);
    if (Wire.endTransmission() == 0) {
      addresses.add(addr);
      labels.add(hexByte(addr));
    }
  }
  bool ack = drvAck();
  result["drv_present"] = ack;
  if (ack) {
    JsonObject registers = result["drv_registers"].to<JsonObject>();
    addDrvRegisters(registers);
  }
  serializeJson(result, Serial); Serial.println();
}

void readI2cCommand(JsonDocument &doc) {
  beginHapticBus();
  JsonDocument result;
  result["event"] = "i2c_read";
  int addr = doc["addr"] | -1;
  int reg = doc["reg"] | 0;
  int length = constrain((int)(doc["length"] | 1), 1, 32);
  if (addr < 8 || addr > 119) {
    result["error"] = "invalid_address";
    serializeJson(result, Serial); Serial.println();
    return;
  }
  result["addr"] = addr; result["reg"] = reg; result["length"] = length;
  uint8_t data[32];
  int error = busRead((uint8_t)addr, (uint8_t)reg, data, (size_t)length);
  result["read_error"] = error;
  if (!error) {
    String text;
    for (int i = 0; i < length; ++i) {
      if (i) text += ' ';
      text += hexByte(data[i]);
    }
    result["data"] = text;
  }
  serializeJson(result, Serial); Serial.println();
}

void pinLevelCommand() {
  int sdaDigital = 0, sclDigital = 0;
  uint16_t sdaMv = 0, sclMv = 0;
  sampleBusLevels(sdaDigital, sclDigital, sdaMv, sclMv);
  JsonDocument result;
  result["event"] = "pin_level";
  result["sda_gpio"] = SDA; result["scl_gpio"] = SCL;
  result["sda_level"] = sdaDigital; result["scl_level"] = sclDigital;
  result["sda_mv"] = sdaMv; result["scl_mv"] = sclMv;
  result["adc_full_scale_mv"] = 3300;
  serializeJson(result, Serial); Serial.println();
}

bool beginAudioBus() {
  if (audioI2sReady) return true;
  // Official reSpeaker XVF3800/XIAO mapping: BCLK=8, WS=7,
  // playback=44 and microphone RX=43; 16 kHz stereo, 32-bit slots.
  audioI2s.setPins(8, 7, 44, 43);
  audioI2sReady = audioI2s.begin(
    I2S_MODE_STD, 16000, I2S_DATA_BIT_WIDTH_32BIT, I2S_SLOT_MODE_STEREO
  );
  return audioI2sReady;
}

void audioProbeCommand(JsonDocument &doc) {
  JsonDocument result;
  result["event"] = "audio_probe";
  result["sample_rate"] = 16000;
  result["channels"] = 2;
  result["bits"] = 32;
  if (!beginAudioBus()) {
    result["ok"] = false;
    result["reason"] = "i2s_init_failed";
    serializeJson(result, Serial); Serial.println();
    return;
  }
  uint32_t duration = constrain((int)(doc["duration_ms"] | 1000), 100, 5000);
  int32_t samples[256];
  uint64_t absoluteTotal = 0;
  uint32_t peak = 0, nonzero = 0, count = 0, bytes = 0;
  uint32_t deadline = millis() + duration;
  while ((int32_t)(millis() - deadline) < 0) {
    size_t got = audioI2s.readBytes((char *)samples, sizeof(samples));
    bytes += got;
    size_t sampleCount = got / sizeof(samples[0]);
    for (size_t i = 0; i < sampleCount; ++i) {
      int64_t value = samples[i];
      uint32_t magnitude = value < 0 ? (uint32_t)(-value) : (uint32_t)value;
      if (magnitude) nonzero++;
      if (magnitude > peak) peak = magnitude;
      absoluteTotal += magnitude;
    }
    count += sampleCount;
    Wearable::poll();
  }
  result["ok"] = bytes > 0;
  result["duration_ms"] = duration;
  result["bytes"] = bytes;
  result["samples"] = count;
  result["nonzero"] = nonzero;
  result["peak"] = peak;
  result["mean_abs"] = count ? absoluteTotal / count : 0;
  if (!bytes) result["reason"] = "no_i2s_data";
  serializeJson(result, Serial); Serial.println();
}

// Only reached from an explicit USB command; never fires on its own.
void hapticCommand(JsonDocument &doc) {
  beginHapticBus();
  JsonDocument result;
  result["event"] = "haptic";
  bool ack = drvAck();
  result["drv_present"] = ack;
  if (!ack) {
    result["ok"] = false;
    result["reason"] = "no_drv2605_at_0x5A";
    serializeJson(result, Serial); Serial.println();
    return;
  }
  String motor = doc["motor"] | "erm";
  bool lra = motor == "lra";
  result["motor"] = lra ? "lra" : "erm";
  String action = doc["action"] | "play";
  result["action"] = action;
  bool written = true;
  if (action == "status") {
    // Read-only: just report the registers.
  } else if (action == "stop") {
    written = drvWrite(DRV_GO, 0x00) && drvWrite(DRV_RTP, 0x00);
  } else {
    // Internal-trigger mode plus motor feedback path and waveform library.
    written = drvWrite(DRV_MODE, 0x00) &&
              drvWrite(DRV_FEEDBACK, lra ? 0xB6 : 0x36) &&
              drvWrite(DRV_LIBRARY, lra ? 0x06 : 0x01);
    if (written && action == "rtp") {
      uint8_t level = (uint8_t)constrain((int)(doc["level"] | 100), 0, 127);
      result["level"] = level;
      written = drvWrite(DRV_MODE, 0x05) && drvWrite(DRV_RTP, level);
    } else if (written) {
      String pattern = doc["pattern"] | "short";
      uint8_t first = 0, second = 0;
      result["pattern"] = pattern;
      if (pattern == "short") first = 10;               // sharp click
      else if (pattern == "double_soft") { first = 1; second = 1; }
      else if (pattern == "success") first = 14;        // strong click
      else if (pattern != "init") {
        result["ok"] = false;
        result["reason"] = "invalid_haptic_pattern";
        serializeJson(result, Serial); Serial.println();
        return;
      }
      written = drvWrite(DRV_SEQ1, first) && drvWrite(DRV_SEQ2, second) &&
                drvWrite(DRV_SEQ3, 0x00) && drvWrite(DRV_GO, pattern == "init" ? 0x00 : 0x01);
    }
  }
  result["ok"] = written;
  if (!written) result["reason"] = "drv2605_write_failed";
  JsonObject registers = result["registers"].to<JsonObject>();
  addDrvRegisters(registers);
  serializeJson(result, Serial); Serial.println();
}

void setup() {
  Serial.setRxBufferSize(8192);
  Serial.begin(115200);
  unsigned long start = millis();
  while (!Serial && millis() - start < 1500) delay(10);
  emit("{\"event\":\"hello\",\"firmware\":\"mindloop-s3-0.5\",\"node\":\"esp32-s3\",\"imu\":false,\"wifi\":true,\"ble\":true}");
  Wearable::begin();
  StandaloneConfig::begin();
}

void loop() {
  if (millis() - lastHeartbeat >= 5000) {
    lastHeartbeat = millis();
    emit(String("{\"event\":\"heartbeat\",\"seq\":") + String(sequence++) + ",\"uptime_ms\":" + String(millis()) + "}");
  }
  static char input[4096];
  static size_t used = 0;
  static bool overflow = false;
  while (Serial.available()) {
    char c = Serial.read();
    if (c == '\r') continue;
    if (c != '\n') {
      if (used < sizeof(input) - 1) input[used++] = c;
      else overflow = true;
      continue;
    }
    input[used] = 0;
    JsonDocument doc;
    bool invalid = overflow || deserializeJson(doc, input);
    used = 0; overflow = false;
    if (invalid) { emit("{\"event\":\"error\",\"reason\":\"invalid_or_oversized_json\"}"); continue; }
    String cmd = doc["cmd"] | "";
    if (cmd == "i2c_scan") {
      scanHapticBus();
    } else if (cmd == "i2c_read") {
      readI2cCommand(doc);
    } else if (cmd == "pin_level") {
      pinLevelCommand();
    } else if (cmd == "haptic") {
      hapticCommand(doc);
    } else if (cmd == "audio_probe") {
      audioProbeCommand(doc);
    } else if (cmd == "ble_send") {
      if (!doc["payload"].is<JsonObject>()) {
        emit("{\"event\":\"error\",\"reason\":\"invalid_payload\"}"); continue;
      }
      String payload; serializeJson(doc["payload"], payload);
      if (payload.length() > 3599) emit("{\"event\":\"error\",\"reason\":\"payload_too_long\"}");
      else if (!Wearable::send(payload)) emit("{\"event\":\"error\",\"reason\":\"wearable_write_failed\"}");
    } else if (cmd == "hello") {
      emit("{\"event\":\"hello\",\"firmware\":\"mindloop-s3-0.5\",\"node\":\"esp32-s3\",\"imu\":false,\"wifi\":true,\"ble\":true}");
    } else if (cmd == "standalone_status") {
      StandaloneConfig::emitStatus();
    } else if (cmd == "configure_cloud") {
      const char *apiKey = doc["api_key"] | "";
      const char *model = doc["model"] | "deepseek-ai/DeepSeek-V4-Flash";
      bool ok = StandaloneConfig::configureCloud(apiKey, model);
      emit(ok ? "{\"event\":\"cloud_configured\",\"ok\":true}" :
                "{\"event\":\"cloud_configured\",\"ok\":false}");
    } else if (cmd == "reset_standalone_config") {
      emit("{\"event\":\"standalone_config_resetting\"}");
      delay(50);
      StandaloneConfig::reset();
    } else if (cmd == "ping") {
      emit("{\"event\":\"pong\"}");
    } else if (cmd == "context" || cmd == "drift") {
      doc.clear(); doc["event"] = cmd; doc["source"] = "esp32-s3"; doc["uptime_ms"] = millis();
      if (cmd == "drift") doc["reason"] = "manual_signal";
      serializeJson(doc, Serial); Serial.println();
    } else emit("{\"event\":\"error\",\"reason\":\"unsupported_command\"}");
  }
  StandaloneConfig::poll();
  if (StandaloneConfig::configPortalActive()) Wearable::setAgentState("setup_required");
  else if (!StandaloneConfig::wifiConnected()) Wearable::setAgentState("wifi_connecting");
  else if (!StandaloneConfig::apiKeyConfigured()) Wearable::setAgentState("key_required");
  else Wearable::setAgentState("agent_starting");
  // Do not block in a scan while a serial command is being assembled.
  if (used == 0 && !overflow) Wearable::poll();
}
