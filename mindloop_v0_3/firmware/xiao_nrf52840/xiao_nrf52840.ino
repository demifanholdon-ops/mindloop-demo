#include <Arduino.h>
#include <Adafruit_TinyUSB.h>
#include <bluefruit.h>
#include <ArduinoJson.h>
#include <PDM.h>
#include <Wire.h>
#include <Seeed_GFX.h>
#include "board/boards/XIAO_LCD_Board.h"
#include "driver/tft/Driver_ST7789.h"
#include "panel/Panel_TFT.h"

Seeed_GFX display;
BLEUart uart;
bool displayReady = false;
bool bleReady = false;
bool advertisingStarted = false;
bool hapticReady = false;
uint32_t lastHostSeen = 0;
bool hostOfflineShown = true;
static constexpr uint8_t DRV2605_ADDR = 0x5A;
uint8_t frame[1600];
// Preallocated RGB565 line buffer (160 px) so the batch path needs no heap
// allocation and flips the screen with a single window + bulk write instead
// of 12800 single-pixel transactions (~1.9 s measured with drawBitmap).
uint16_t frameLine[160];
struct Input { char data[3600]; size_t length = 0; bool overflow = false; } usbInput, bleInput;
struct Button {
  uint8_t pin;
  bool raw = true;
  bool stable = true;
  uint32_t changed = 0;
  uint32_t pressed = 0;
  uint32_t clickDeadline = 0;
  uint8_t clicks = 0;
  Button(uint8_t p) : pin(p) {}
};
Button buttons[] = {{D6}, {D7}};
uint32_t eventSeq = 0;
static constexpr uint32_t DOUBLE_CLICK_MS = 350;
static constexpr uint32_t LONG_PRESS_MS = 800;
static constexpr uint32_t MAX_RECORDING_MS = 15000;
// Absorb temporary BLE/display stalls without dropping 16 kHz PCM16 audio.
static constexpr size_t AUDIO_RING_SIZE = 32768;
static constexpr size_t AUDIO_CHUNK_SIZE = 768;
uint8_t audioRing[AUDIO_RING_SIZE];
uint8_t pdmBuffer[512];
volatile uint16_t audioRead = 0;
volatile uint16_t audioWrite = 0;
volatile uint32_t audioDropped = 0;
volatile bool recording = false;
bool stopPending = false;
bool micReady = false;
uint32_t recordingStarted = 0;
uint32_t audioSeq = 0;

void onPdmReceive() {
  int available = PDM.available();
  while (available > 0) {
    int count = min(available, (int)sizeof(pdmBuffer));
    int read = PDM.read(pdmBuffer, count);
    if (read <= 0) return;
    if (recording) {
      for (int i = 0; i < read; i++) {
        uint16_t next = (audioWrite + 1) & (AUDIO_RING_SIZE - 1);
        if (next == audioRead) audioDropped++;
        else { audioRing[audioWrite] = pdmBuffer[i]; audioWrite = next; }
      }
    }
    available -= read;
  }
}

// Protect only the PCM producer; never mask Bluetooth/USB timing interrupts.
size_t audioAvailable() {
  NVIC_DisableIRQ(PDM_IRQn);
  uint16_t read = audioRead, write = audioWrite;
  NVIC_EnableIRQ(PDM_IRQn);
  return (write - read) & (AUDIO_RING_SIZE - 1);
}

void emitAudioChunk() {
  static uint8_t chunk[AUDIO_CHUNK_SIZE];
  static char line[AUDIO_CHUNK_SIZE * 4 / 3 + 70];
  size_t available = audioAvailable();
  if (!available || !Serial) return;
  size_t count = min(available, AUDIO_CHUNK_SIZE);
  NVIC_DisableIRQ(PDM_IRQn);
  for (size_t i = 0; i < count; i++) {
    chunk[i] = audioRing[audioRead];
    audioRead = (audioRead + 1) & (AUDIO_RING_SIZE - 1);
  }
  NVIC_EnableIRQ(PDM_IRQn);
  int offset = snprintf(line, sizeof(line), "{\"event\":\"audio_chunk\",\"seq\":%lu,\"audio\":\"", (unsigned long)audioSeq++);
  const char *base64 = "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789+/";
  for (size_t i = 0; i < count; i += 3) {
    uint32_t value = (uint32_t)chunk[i] << 16;
    if (i + 1 < count) value |= (uint32_t)chunk[i + 1] << 8;
    if (i + 2 < count) value |= chunk[i + 2];
    line[offset++] = base64[(value >> 18) & 63];
    line[offset++] = base64[(value >> 12) & 63];
    line[offset++] = i + 1 < count ? base64[(value >> 6) & 63] : '=';
    line[offset++] = i + 2 < count ? base64[value & 63] : '=';
  }
  line[offset++] = '\"'; line[offset++] = '}'; line[offset++] = '\n';
  Serial.write((uint8_t *)line, offset);
}

void startRecording(bool ble) {
  if (ble) { reply("{\"error\":\"voice_usb_only\"}", true); return; }
  if (!micReady) { reply("{\"error\":\"microphone_unavailable\"}", false); return; }
  NVIC_DisableIRQ(PDM_IRQn);
  audioRead = audioWrite = 0; audioDropped = 0;
  NVIC_EnableIRQ(PDM_IRQn);
  audioSeq = 0; stopPending = false; recordingStarted = millis(); recording = true;
  if (displayReady) {
    display.fillScreen(TFT_BLACK);
    display.setTextColor(TFT_WHITE, TFT_BLACK);
    display.setTextSize(1);
    display.setCursor(8, 18); display.print("Listening...");
    display.setCursor(8, 42); display.print("Press K1 to finish");
  }
  Serial.println("{\"event\":\"audio_start\",\"sample_rate\":16000,\"channels\":1,\"sample_width\":2}");
}

void stopRecording(bool ble) {
  if (ble) { reply("{\"error\":\"voice_usb_only\"}", true); return; }
  if (!recording) return;
  recording = false;
  stopPending = true;
}

void reply(const String &line, bool ble) {
  if (ble) {
    // BLEUart's unbuffered notify path splits at the negotiated MTU (up to
    // 244 bytes with the 247 MTU negotiated by the S3 central) and returns
    // false when the SoftDevice hvn queue is full. Passing the whole line
    // at once cuts a 3,300-byte frame from ~165 20-byte notifications to
    // ~14, and the retry loop handles backpressure instead of the old fixed
    // 20-byte chunking that stalled every chunk for up to 2 s.
    String packet = line + '\n';
    uint32_t deadline = millis() + 4000;
    size_t total = packet.length();
    while (Bluefruit.connected() && (int32_t)(millis() - deadline) < 0) {
      // BLEUart::write returns len only when the whole notify completed; it
      // returns 0 when the hvn queue is full. Retry the entire remainder.
      if (uart.write((const uint8_t *)packet.c_str(), total) == total) break;
      delay(1);
    }
    if (!Bluefruit.connected() || (int32_t)(millis() - deadline) >= 0) {
      if (Serial) Serial.println("{\"event\":\"error\",\"reason\":\"ble_notify_timeout\"}");
      Bluefruit.disconnect(Bluefruit.connHandle());
    }
  } else Serial.println(line);
}
bool drvWrite(uint8_t reg, uint8_t value) {
  Wire.beginTransmission(DRV2605_ADDR);
  Wire.write(reg);
  Wire.write(value);
  return Wire.endTransmission() == 0;
}

bool initHaptic() {
  Wire.begin();
  Wire.beginTransmission(DRV2605_ADDR);
  if (Wire.endTransmission() != 0) return false;
  // DRV2605L internal-trigger mode, LRA feedback, LRA waveform library.
  return drvWrite(0x01, 0x00) && drvWrite(0x1A, 0xB6) &&
         drvWrite(0x03, 0x06) && drvWrite(0x04, 0x00) &&
         drvWrite(0x05, 0x00);
}

bool playHaptic(const char *pattern) {
  if (!hapticReady) return false;
  uint8_t first = 0, second = 0;
  if (!strcmp(pattern, "short")) first = 10;             // sharp click
  else if (!strcmp(pattern, "double_soft")) { first = 1; second = 1; }
  else if (!strcmp(pattern, "success")) first = 14;      // strong click
  else return false;
  return drvWrite(0x04, first) && drvWrite(0x05, second) &&
         drvWrite(0x06, 0x00) && drvWrite(0x0C, 0x01);
}

int nibble(char c) {
  if (c >= '0' && c <= '9') return c - '0';
  if (c >= 'a' && c <= 'f') return c - 'a' + 10;
  return -1;
}
void command(char *line, bool ble) {
  JsonDocument doc;
  if (deserializeJson(doc, line)) { reply("{\"error\":\"invalid_json\"}", ble); return; }
  const char *cmd = doc["cmd"] | "";
  if (!strcmp(cmd, "hello") || !strcmp(cmd, "frame")) {
    lastHostSeen = millis();
    hostOfflineShown = false;
  }
  if (!strcmp(cmd, "hello")) {
    reply(String("{\"event\":\"ready\",\"firmware\":\"mindloop-0.7\",\"width\":160,\"height\":80,\"haptic\":") + (hapticReady ? "true" : "false") + ",\"microphone\":" + (micReady ? "true" : "false") + ",\"display\":" + (displayReady ? "true}" : "false}"), ble);
  } else if (!strcmp(cmd, "ble_status")) {
    JsonDocument status;
    status["event"] = "ble_status";
    status["initialized"] = bleReady;
    status["advertising_started"] = advertisingStarted;
    status["advertising"] = Bluefruit.Advertising.isRunning();
    status["connected"] = Bluefruit.connected();
    String output; serializeJson(status, output); reply(output, ble);
  } else if (!strcmp(cmd, "haptic")) {
    const char *pattern = doc["pattern"] | "";
    if (!hapticReady) reply("{\"error\":\"haptic_unavailable\"}", ble);
    else if (!playHaptic(pattern)) reply("{\"error\":\"invalid_haptic_pattern\"}", ble);
    else reply(String("{\"event\":\"haptic_played\",\"pattern\":\"") + pattern + "\"}", ble);
  } else if (!strcmp(cmd, "record")) {
    const char *action = doc["action"] | "";
    if (!strcmp(action, "start")) startRecording(ble);
    else if (!strcmp(action, "stop")) stopRecording(ble);
    else reply("{\"error\":\"invalid_record_action\"}", ble);
  } else if (!strcmp(cmd, "frame")) {
    const char *hex = doc["hex"] | "";
    if (!displayReady || strlen(hex) != 3200) { reply("{\"error\":\"invalid_frame\"}", ble); return; }
    for (size_t i = 0; i < sizeof(frame); i++) {
      int a = nibble(hex[i*2]), b = nibble(hex[i*2+1]);
      if (a < 0 || b < 0) { reply("{\"error\":\"invalid_hex\"}", ble); return; }
      frame[i] = (a << 4) | b;
    }
    // Batch blit: one addr window + bulk RGB565 writes. drawBitmap() would
    // call drawPixel 12800 times (measured ~1.9 s); this path targets <50 ms.
    display.setAddrWindow(0, 0, 160, 80);
    for (int y = 0; y < 80; y++) {
      for (int x = 0; x < 160; x += 8) {
        uint8_t byte = frame[y * 20 + x / 8];
        for (int bit = 0; bit < 8; bit++) {
          bool on = byte & (0x80 >> bit);
          frameLine[x + bit] = on ? 0xFFFF : 0x0000;
        }
      }
      display.pushPixels(frameLine, 160);
    }
    reply(String("{\"event\":\"displayed\",\"id\":") + (doc["id"] | 0) + "}", ble);
  } else { reply("{\"error\":\"unsupported_command\"}", ble); }
}
void consume(Stream &stream, Input &input, bool ble) {
  // Bound work so a long incoming frame cannot starve button debouncing.
  for (int n = 0; n < 256 && stream.available(); n++) {
    char c = stream.read();
    if (c == '\n') {
      if (!input.overflow) { input.data[input.length] = 0; command(input.data, ble); }
      else reply("{\"error\":\"line_too_long\"}", ble);
      input.length = 0; input.overflow = false;
    } else if (c != '\r') {
      if (input.length < sizeof(input.data)-1) input.data[input.length++] = c;
      else input.overflow = true;
    }
  }
}
void emitButton(int index, const char *gesture) {
  const char *key = index == 0 ? "k1" : "k2";
  String event = String("{\"event\":\"button\",\"key\":\"") + key +
                 "\",\"gesture\":\"" + gesture + "\",\"seq\":" + (++eventSeq) + "}";
  if (Serial) Serial.println(event);
  if (Bluefruit.connected()) reply(event, true);
}
void setup() {
  Serial.begin(115200);
  for (auto &b : buttons) pinMode(b.pin, INPUT_PULLUP);
  displayReady = display.begin<Board_XIAO_0inch96_LCD<38,37>, Config_Seeed_0inch96_LCD_ST7789>();
  if (displayReady) {
    display.setRotation(1);
    display.fillScreen(TFT_BLACK);
    display.setTextColor(TFT_WHITE, TFT_BLACK);
    display.setTextSize(1);
    display.setTextSize(2);
    display.setCursor(25, 17); display.print("MindLoop");
    display.setTextSize(1);
    display.setCursor(39, 48); display.print("Starting...");
    delay(1200);
    display.fillScreen(TFT_BLACK);
    display.setCursor(8, 10); display.print("MindLoop Ready");
    display.setCursor(8, 31); display.print("Connect computer");
    display.setCursor(8, 52); display.print("Waiting for Agent");
  }
  PDM.setPins(D1, D0, -1);
  PDM.onReceive(onPdmReceive);
  PDM.setBufferSize(512);
  micReady = PDM.begin(1, 16000);
  if (micReady) PDM.setGain(30);
  hapticReady = initHaptic();
  Bluefruit.configPrphBandwidth(BANDWIDTH_MAX);
  bleReady = Bluefruit.begin();
  Bluefruit.Periph.setConnInterval(6, 12);
  Bluefruit.setName("MindLoop");
  uart.begin();
  Bluefruit.Advertising.addFlags(BLE_GAP_ADV_FLAGS_LE_ONLY_GENERAL_DISC_MODE);
  Bluefruit.Advertising.addTxPower();
  Bluefruit.Advertising.addService(uart);
  Bluefruit.ScanResponse.addName();
  Bluefruit.Advertising.restartOnDisconnect(true);
  Bluefruit.Advertising.setInterval(32, 244);
  advertisingStarted = Bluefruit.Advertising.start(0);
}
void loop() {
  if (!hostOfflineShown && millis() - lastHostSeen > 8000 && !recording) {
    hostOfflineShown = true;
    if (displayReady) {
      display.fillScreen(TFT_BLACK);
      display.setTextSize(1);
      display.setCursor(8, 18); display.print("Connection lost");
      display.setCursor(8, 42); display.print("Waiting for Agent");
    }
  }
  consume(Serial, usbInput, false);
  consume(uart, bleInput, true);
  emitAudioChunk();
  if (recording && millis() - recordingStarted >= MAX_RECORDING_MS) stopRecording(false);
  if (stopPending && audioAvailable() == 0) {
    stopPending = false;
    Serial.println(String("{\"event\":\"audio_stop\",\"chunks\":") + audioSeq + ",\"dropped\":" + audioDropped + "}");
  }
  uint32_t now = millis();
  for (int i = 0; i < 2; i++) {
    auto &b = buttons[i];
    bool raw = digitalRead(b.pin);
    if (raw != b.raw) { b.raw = raw; b.changed = now; }
    if (raw != b.stable && now - b.changed >= 30) {
      b.stable = raw;
      if (!raw) {
        if (b.clicks == 1 && (int32_t)(now - b.clickDeadline) >= 0) {
          emitButton(i, "single");
          b.clicks = 0;
        }
        b.pressed = now;
      } else if (now - b.pressed >= LONG_PRESS_MS) {
        b.clicks = 0;
        emitButton(i, "long");
      } else if (b.clicks == 1) {
        b.clicks = 0;
        emitButton(i, "double");
      } else {
        b.clicks = 1;
        b.clickDeadline = now + DOUBLE_CLICK_MS;
      }
    }
    if (b.stable && b.clicks == 1 && (int32_t)(now - b.clickDeadline) >= 0) {
      b.clicks = 0;
      emitButton(i, "single");
    }
  }
  delay(1);
}
