#pragma once

#include <WiFi.h>
#include <WiFiManager.h>
#include <Preferences.h>
#include <ArduinoJson.h>

namespace StandaloneConfig {
static WiFiManager manager;
static Preferences preferences;
static char apiKey[129] = {0};
static char model[65] = "deepseek-ai/DeepSeek-V4-Flash";
static WiFiManagerParameter apiKeyParam(
  "siliconflow_key", "SiliconFlow API key", "", 128,
  "type='password' autocomplete='off'"
);
static WiFiManagerParameter modelParam(
  "agent_model", "Agent model", "deepseek-ai/DeepSeek-V4-Flash", 64
);
static bool saveRequested = false;
static bool portalActive = false;

static void persistParameters() {
  strlcpy(apiKey, apiKeyParam.getValue(), sizeof(apiKey));
  strlcpy(model, modelParam.getValue(), sizeof(model));
  preferences.begin("mindloop", false);
  preferences.putString("api_key", apiKey);
  preferences.putString("model", model);
  preferences.end();
  saveRequested = false;
}

static void begin() {
  preferences.begin("mindloop", true);
  String storedKey = preferences.getString("api_key", "");
  String storedModel = preferences.getString("model", model);
  preferences.end();
  strlcpy(apiKey, storedKey.c_str(), sizeof(apiKey));
  strlcpy(model, storedModel.c_str(), sizeof(model));
  apiKeyParam.setValue(apiKey, sizeof(apiKey));
  modelParam.setValue(model, sizeof(model));

  manager.setDebugOutput(false);
  manager.addParameter(&apiKeyParam);
  manager.addParameter(&modelParam);
  manager.setSaveParamsCallback([]() { saveRequested = true; });
  manager.setConfigPortalBlocking(false);
  manager.setConnectTimeout(12);
  manager.setConfigPortalTimeout(0);

  // The setup network is only a one-time local provisioning path. Wi-Fi and
  // API credentials remain in ESP32 NVS and are never emitted over serial.
  if (WiFi.SSID().isEmpty() || storedKey.isEmpty()) {
    portalActive = manager.startConfigPortal("MindLoop-Setup", "mindloop-setup");
  } else {
    manager.autoConnect("MindLoop-Setup", "mindloop-setup");
    portalActive = manager.getConfigPortalActive();
  }
}

static void poll() {
  manager.process();
  portalActive = manager.getConfigPortalActive();
  if (saveRequested) persistParameters();
}

static bool wifiConnected() { return WiFi.status() == WL_CONNECTED; }
static bool cloudConfigured() { return wifiConnected() && apiKey[0] != 0; }
static bool apiKeyConfigured() { return apiKey[0] != 0; }
static bool configPortalActive() { return portalActive; }
static const char *key() { return apiKey; }
static const char *agentModel() { return model; }

static bool configureCloud(const char *newKey, const char *newModel) {
  if (!newKey || !newKey[0] || strlen(newKey) >= sizeof(apiKey)) return false;
  strlcpy(apiKey, newKey, sizeof(apiKey));
  if (newModel && newModel[0] && strlen(newModel) < sizeof(model)) {
    strlcpy(model, newModel, sizeof(model));
  }
  apiKeyParam.setValue(apiKey, sizeof(apiKey));
  modelParam.setValue(model, sizeof(model));
  preferences.begin("mindloop", false);
  preferences.putString("api_key", apiKey);
  preferences.putString("model", model);
  preferences.end();
  return true;
}

static void emitStatus() {
  JsonDocument status;
  status["event"] = "standalone_status";
  status["wifi_connected"] = wifiConnected();
  status["api_key_configured"] = apiKey[0] != 0;
  status["portal_active"] = portalActive;
  status["setup_ssid"] = portalActive ? "MindLoop-Setup" : "";
  status["agent_runtime"] = false;
  serializeJson(status, Serial); Serial.println();
}

static void reset() {
  preferences.begin("mindloop", false);
  preferences.clear();
  preferences.end();
  manager.resetSettings();
  apiKey[0] = 0;
  ESP.restart();
}
}
