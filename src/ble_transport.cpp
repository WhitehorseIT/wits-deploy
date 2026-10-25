#include "ble_transport.h"
#include "firmware_version.h"
#include "board_profile.h"
#include "usb_storage.h"
#include "firmware_update.h"

#include <BLE2902.h>
#include <BLEDevice.h>
#include <BLESecurity.h>
#include <BLEServer.h>
#include <BLEUtils.h>
#include <esp_system.h>
#include <freertos/FreeRTOS.h>
#include <freertos/queue.h>
#include <freertos/semphr.h>

#if defined(CONFIG_NIMBLE_ENABLED)
#include <host/ble_store.h>
#endif

namespace BleTransport {
namespace {

constexpr char SERVICE_UUID[] = "62fa47a0-d77c-4045-9e7e-81d5a93931cc";
constexpr char RX_UUID[] = "2bcd9577-d0b1-4164-9ff4-88f0cc29cbc3";
constexpr char TX_UUID[] = "7cb2a248-dad7-4149-a36f-fc2dfe91675d";
constexpr char INFO_UUID[] = "3abfae15-ec3c-49db-a65d-17c8d977c102";
constexpr char OTA_CONTROL_UUID[] = "f42aa901-5ac7-4b64-983a-2c4433216101";
constexpr char OTA_DATA_UUID[] = "f42aa902-5ac7-4b64-983a-2c4433216101";
constexpr char OTA_STATUS_UUID[] = "f42aa903-5ac7-4b64-983a-2c4433216101";

constexpr uint8_t PROTOCOL_VERSION = 2;
constexpr uint8_t OPCODE_PING = 0x01;
constexpr uint8_t OPCODE_TYPE_TEXT = 0x10;
constexpr uint8_t OPCODE_STOP = 0x11;
constexpr uint8_t OPCODE_KEY_ACTION = 0x12;
constexpr uint8_t OPCODE_IDENTIFY = 0x13;
constexpr uint8_t OPCODE_KEY_INTERVAL = 0x14;
constexpr uint8_t OPCODE_STORAGE_MODE = 0x15;
constexpr uint8_t TEXT_FLAG_START = 0x01;
constexpr uint8_t TEXT_FLAG_END = 0x02;
constexpr uint8_t TEXT_VALID_FLAGS = TEXT_FLAG_START | TEXT_FLAG_END;

enum Status : uint8_t {
  STATUS_OK = 0,
  STATUS_BAD_VERSION = 1,
  STATUS_UNKNOWN_OPCODE = 2,
  STATUS_MALFORMED = 3,
  STATUS_NOT_ARMED = 4,
  STATUS_BUSY = 5,
  STATUS_UNSUPPORTED_TEXT = 6,
  STATUS_TOO_LARGE = 7,
  STATUS_BAD_STATE = 8,
  STATUS_HID_ERROR = 9,
  STATUS_UNSUPPORTED_KEY = 10,
  STATUS_TYPING_COMPLETE = 0x10,
  STATUS_TYPING_CANCELED = 0x11,
  STATUS_STATE_CHANGED = 0x12,
  STATUS_KEY_COMPLETE = 0x13,
  STATUS_KEY_CANCELED = 0x14,
};

volatile bool bleConnected = false;
volatile bool bleAuthenticated = false;
volatile bool advertising = false;
volatile bool pairingOpen = false;
volatile bool advertisingRefreshRequested = false;
volatile bool connectionMayPair = false;
volatile bool connectionWasBonded = false;
volatile uint32_t advertisingResumeAt = 0;
volatile bool armed = false;
volatile bool typingActive = false;
volatile bool keyActionActive = false;
volatile uint16_t characterIntervalMs = DEFAULT_KEY_INTERVAL_MS;
uint32_t advertisingDeadline = 0;
uint32_t identifyDeadline = 0;
char identifyLabelBuffer[MAX_IDENTIFY_LABEL_BYTES + 1] = {};
uint32_t identifyRevision = 0;
portMUX_TYPE identifyMux = portMUX_INITIALIZER_UNLOCKED;

char deviceIdBuffer[5] = {};
char deviceNameBuffer[24] = {};
uint32_t devicePasskey = 0;

BLECharacteristic *txCharacteristic = nullptr;
BLECharacteristic *otaStatusCharacteristic = nullptr;
BLEServer *bleServer = nullptr;
BLESecurity *bleSecurity = nullptr;
QueueHandle_t responseQueue = nullptr;
SemaphoreHandle_t textMutex = nullptr;

uint8_t stagingText[MAX_TEXT_BYTES];
size_t stagingLength = 0;
bool receivingText = false;
uint8_t typingText[MAX_TEXT_BYTES];
size_t typingLength = 0;
size_t typingOffset = 0;
uint16_t typingSequence = 0;
KeyAction pendingKeyAction = {};

struct PendingResponse {
  uint8_t status;
  uint16_t sequence;
};

void secureClear(uint8_t *buffer, size_t length) {
  volatile uint8_t *cursor = buffer;
  while (length-- > 0) {
    *cursor++ = 0;
  }
}

void initializeIdentity() {
  if (deviceIdBuffer[0] != '\0') {
    return;
  }

  uint16_t suffix = static_cast<uint16_t>(ESP.getEfuseMac() & 0xffff);
  snprintf(deviceIdBuffer, sizeof(deviceIdBuffer), "%04X", suffix);
  snprintf(deviceNameBuffer, sizeof(deviceNameBuffer),
           "WITS Keyboard-%s", deviceIdBuffer);
}

void rotatePasskey() {
  uint32_t previousPasskey = devicePasskey;
  do {
    devicePasskey = 100000 + (esp_random() % 900000);
  } while (devicePasskey == previousPasskey);

  if (bleSecurity != nullptr) {
    // Display-only I/O plus MITM/Secure Connections forces a newly pairing
    // computer to enter the passkey currently visible on the board.
    bleSecurity->setPassKey(true, devicePasskey);
  }
}

void queueStatus(uint8_t status, uint16_t sequence) {
  if (responseQueue == nullptr) {
    return;
  }
  PendingResponse response = {status, sequence};
  xQueueSend(responseQueue, &response, 0);
}

void clearStagingLocked() {
  secureClear(stagingText, sizeof(stagingText));
  stagingLength = 0;
  receivingText = false;
}

void clearTypingLocked() {
  secureClear(typingText, sizeof(typingText));
  typingLength = 0;
  typingOffset = 0;
  typingSequence = 0;
  typingActive = false;
}

void clearKeyActionLocked() {
  secureClear(reinterpret_cast<uint8_t *>(&pendingKeyAction),
              sizeof(pendingKeyAction));
  keyActionActive = false;
}

void clearAllText(bool notifyCancellation) {
  if (textMutex == nullptr || xSemaphoreTake(textMutex, portMAX_DELAY) != pdTRUE) {
    return;
  }

  bool wasTyping = typingActive;
  uint16_t canceledSequence = typingSequence;
  bool hadKeyAction = keyActionActive;
  uint16_t canceledKeySequence = pendingKeyAction.sequence;
  clearStagingLocked();
  clearTypingLocked();
  clearKeyActionLocked();
  xSemaphoreGive(textMutex);

  if (notifyCancellation && wasTyping) {
    queueStatus(STATUS_TYPING_CANCELED, canceledSequence);
  }
  if (notifyCancellation && hadKeyAction) {
    queueStatus(STATUS_KEY_CANCELED, canceledKeySequence);
  }
}

bool supportedTextByte(uint8_t value) {
  return value == '\t' || value == '\n' ||
         (value >= 0x20 && value <= 0x7e);
}

bool disconnectCurrentClient() {
  if (!bleConnected) {
    return true;
  }
  if (bleServer == nullptr) {
    return false;
  }

  armed = false;
  clearAllText(false);
  uint16_t connectionId = bleServer->getConnId();
#if defined(CONFIG_NIMBLE_ENABLED)
  if (bleServer->disconnect(connectionId) != 0) {
    return false;
  }
#elif defined(CONFIG_BLUEDROID_ENABLED)
  bleServer->disconnect(connectionId);
#else
  return false;
#endif

  uint32_t deadline = millis() + 2000;
  while (bleConnected &&
         static_cast<int32_t>(millis() - deadline) < 0) {
    delay(10);
  }
  return !bleConnected;
}

// The screen's pairing window and radio advertising are separate: known
// computers can reconnect indefinitely, without allowing new pairing requests.
void refreshAdvertisingAfter(uint32_t delayMs) {
  advertisingResumeAt = millis() + delayMs;
  advertisingRefreshRequested = true;
}

bool startBondedAdvertising() {
  BLEDevice::stopAdvertising();
  advertising = false;
  if (bleConnected) return false;

#if defined(CONFIG_NIMBLE_ENABLED)
  constexpr int MAX_BONDS = 16;
  ble_addr_t peers[MAX_BONDS];
  int count = 0;
  if (ble_store_util_bonded_peers(peers, &count, MAX_BONDS) != 0) {
    refreshAdvertisingAfter(1000);
    return false;
  }
  if (count == 0) return false;
  // Use identity addresses and their stored IRKs (restored by NimBLE). The
  // controller's accept list also supports resolved private peer addresses.
  for (int index = 0; index < count; ++index) {
    peers[index].type &= 1;  // Public/random identity -> controller address type.
  }
  if (ble_gap_wl_set(peers, count) != 0) {
    refreshAdvertisingAfter(1000);
    return false;  // Never fall back to unrestricted advertising on failure.
  }
#else
  // This target uses NimBLE. Other stacks retain physical-window pairing
  // until their controller accept-list implementation is provided.
  return false;
#endif

  BLEDevice::getAdvertising()->setScanFilter(false, true);
  if (bleConnected) return false;
  BLEDevice::startAdvertising();
#if defined(CONFIG_NIMBLE_ENABLED)
  advertising = ble_gap_adv_active() != 0;
#endif
  if (!advertising) refreshAdvertisingAfter(1000);
  return advertising;
}

#if defined(CONFIG_NIMBLE_ENABLED)
ble_gap_event_fn *originalGapCallback = nullptr;
void *originalGapArgument = nullptr;

int guardedGapCallback(ble_gap_event *event, void *) {
  // The core's default repeat-pairing handler deletes the existing bond.
  // Intercept that event BEFORE it reaches the core, preserving the bond
  // unless the physical pairing window authorized this connection.
  if (!connectionMayPair && event->type == BLE_GAP_EVENT_REPEAT_PAIRING) {
    ble_gap_terminate(event->repeat_pairing.conn_handle, BLE_ERR_AUTH_FAIL);
    return BLE_GAP_REPEAT_PAIRING_IGNORE;
  }
  if (!connectionMayPair && event->type == BLE_GAP_EVENT_PASSKEY_ACTION) {
    ble_gap_terminate(event->passkey.conn_handle, BLE_ERR_AUTH_FAIL);
    return 0;
  }
  return originalGapCallback != nullptr ? originalGapCallback(event, originalGapArgument) : 0;
}

bool isBondedPeer(const ble_addr_t &address) {
  constexpr int MAX_BONDS = 16;
  ble_addr_t peers[MAX_BONDS];
  int count = 0;
  if (ble_store_util_bonded_peers(peers, &count, MAX_BONDS) != 0) return false;
  for (int index = 0; index < count; ++index) {
    if ((peers[index].type & 1) == (address.type & 1) &&
        memcmp(peers[index].val, address.val, sizeof(address.val)) == 0) {
      return true;
    }
  }
  return false;
}
#endif

bool supportedKeyCode(uint8_t keyCode) {
  return (keyCode >= KEY_CODE_BACKSPACE && keyCode <= KEY_CODE_INSERT) ||
         (keyCode >= KEY_CODE_F1 && keyCode <= KEY_CODE_F12) ||
         keyCode == KEY_CODE_SPACE ||
         (keyCode >= '0' && keyCode <= '9') ||
         (keyCode >= 'A' && keyCode <= 'Z');
}

uint8_t acceptKeyAction(uint8_t keyCode,
                        uint8_t modifiers,
                        uint16_t sequence) {
  if (FirmwareUpdate::active()) return STATUS_BUSY;
  constexpr uint8_t VALID_MODIFIERS =
      MODIFIER_CTRL | MODIFIER_SHIFT | MODIFIER_ALT | MODIFIER_GUI;
  if (!supportedKeyCode(keyCode)) {
    return STATUS_UNSUPPORTED_KEY;
  }
  if ((modifiers & ~VALID_MODIFIERS) != 0) {
    return STATUS_MALFORMED;
  }
  if (textMutex == nullptr ||
      xSemaphoreTake(textMutex, pdMS_TO_TICKS(50)) != pdTRUE) {
    return STATUS_BUSY;
  }

  uint8_t result = STATUS_OK;
  if (!armed || !bleConnected || !bleAuthenticated) {
    result = STATUS_NOT_ARMED;
  } else if (typingActive || keyActionActive || receivingText) {
    result = STATUS_BUSY;
  } else {
    pendingKeyAction = {keyCode, modifiers, sequence};
    keyActionActive = true;
  }
  xSemaphoreGive(textMutex);
  return result;
}

uint8_t acceptTextChunk(const uint8_t *payload,
                        size_t payloadLength,
                        uint8_t flags,
                        uint16_t sequence) {
  if (FirmwareUpdate::active()) return STATUS_BUSY;
  if ((flags & ~TEXT_VALID_FLAGS) != 0) {
    return STATUS_MALFORMED;
  }
  if (textMutex == nullptr ||
      xSemaphoreTake(textMutex, pdMS_TO_TICKS(50)) != pdTRUE) {
    return STATUS_BUSY;
  }

  uint8_t result = STATUS_OK;
  bool startsText = (flags & TEXT_FLAG_START) != 0;
  bool endsText = (flags & TEXT_FLAG_END) != 0;

  if (startsText) {
    if (typingActive) {
      result = STATUS_BUSY;
      goto done;
    }
    clearStagingLocked();
    receivingText = true;
  } else if (!receivingText) {
    result = STATUS_BAD_STATE;
    goto done;
  }

  for (size_t index = 0; index < payloadLength; ++index) {
    if (!supportedTextByte(payload[index])) {
      clearStagingLocked();
      result = STATUS_UNSUPPORTED_TEXT;
      goto done;
    }
  }

  if (payloadLength > MAX_TEXT_BYTES - stagingLength) {
    clearStagingLocked();
    result = STATUS_TOO_LARGE;
    goto done;
  }

  if (payloadLength > 0) {
    memcpy(stagingText + stagingLength, payload, payloadLength);
    stagingLength += payloadLength;
  }

  if (endsText) {
    if (stagingLength == 0) {
      clearStagingLocked();
      result = STATUS_MALFORMED;
      goto done;
    }
    if (!armed || !bleConnected || !bleAuthenticated) {
      clearStagingLocked();
      result = STATUS_NOT_ARMED;
      goto done;
    }
    if (typingActive) {
      clearStagingLocked();
      result = STATUS_BUSY;
      goto done;
    }

    memcpy(typingText, stagingText, stagingLength);
    typingLength = stagingLength;
    typingOffset = 0;
    typingSequence = sequence;
    typingActive = true;
    clearStagingLocked();
  }

done:
  xSemaphoreGive(textMutex);
  return result;
}

void sendStatus(uint8_t status, uint16_t sequence) {
  if (txCharacteristic == nullptr || !bleConnected || !bleAuthenticated) {
    return;
  }

  uint8_t response[5] = {
    PROTOCOL_VERSION,
    status,
    static_cast<uint8_t>(sequence & 0xff),
    static_cast<uint8_t>((sequence >> 8) & 0xff),
    static_cast<uint8_t>((bleAuthenticated ? 0x01 : 0x00) |
                         (armed ? 0x02 : 0x00) |
                         (typingActive ? 0x04 : 0x00)),
  };
  txCharacteristic->setValue(response, sizeof(response));
  txCharacteristic->notify();
}

class ServerCallbacks : public BLEServerCallbacks {
  void onConnect(BLEServer *) override {
    // USB access belongs to the mounted export, not the BLE control session.
    // Reconnecting must not write-protect a host filesystem with dirty caches.
    clearAllText(false);
    if (responseQueue != nullptr) {
      xQueueReset(responseQueue);
    }
    bleConnected = true;
    bleAuthenticated = false;
    advertising = false;
    connectionMayPair = pairingOpen;
    characterIntervalMs = DEFAULT_KEY_INTERVAL_MS;
    connectionWasBonded = false;
    armed = false;
    identifyDeadline = 0;
  }

#if defined(CONFIG_NIMBLE_ENABLED)
  void onConnect(BLEServer *server, ble_gap_conn_desc *connection) override {
    connectionWasBonded = connection != nullptr && isBondedPeer(connection->peer_id_addr);
    if (!connectionMayPair && !connectionWasBonded && connection != nullptr) {
      server->disconnect(connection->conn_handle);
    }
  }
#endif

  void onDisconnect(BLEServer *) override {
    FirmwareUpdate::disconnected();
    // Keep an authorized R/W export writable until the USB host safely ejects.
    bleConnected = false;
    bleAuthenticated = false;
    advertising = false;
    connectionMayPair = false;
    connectionWasBonded = false;
    characterIntervalMs = DEFAULT_KEY_INTERVAL_MS;
    refreshAdvertisingAfter(30);
    armed = false;
    identifyDeadline = 0;
    clearAllText(false);
    if (responseQueue != nullptr) {
      xQueueReset(responseQueue);
    }
  }
};

class SecurityCallbacks : public BLESecurityCallbacks {
  bool onSecurityRequest() override {
    return pairingOpen || connectionMayPair || connectionWasBonded;
  }

#if defined(CONFIG_BLUEDROID_ENABLED)
  void onAuthenticationComplete(esp_ble_auth_cmpl_t result) override {
    bleAuthenticated = result.success && (connectionMayPair || connectionWasBonded);
    if (!bleAuthenticated) {
      armed = false;
      clearAllText(false);
    }
    if (bleAuthenticated) {
      advertising = false;
      pairingOpen = false;
      connectionWasBonded = true;
      connectionMayPair = false;
    }
  }
#endif

#if defined(CONFIG_NIMBLE_ENABLED)
  void onAuthenticationComplete(ble_gap_conn_desc *connection,
                                int status) override {
    bleAuthenticated = status == 0 && connection != nullptr &&
                       (connectionMayPair || connectionWasBonded) &&
                       connection->sec_state.encrypted &&
                       connection->sec_state.authenticated;
    if (!bleAuthenticated) {
      armed = false;
      clearAllText(false);
    }
    if (bleAuthenticated) {
      advertising = false;
      pairingOpen = false;
      connectionWasBonded = true;
      connectionMayPair = false;
    }
  }
#endif
};

class RxCallbacks : public BLECharacteristicCallbacks {
  void wipeRequest(BLECharacteristic *characteristic) {
    uint8_t *data = characteristic->getData();
    size_t length = characteristic->getLength();
    if (data != nullptr && length > 0) {
      secureClear(data, length);
    }
  }

  void processWrite(BLECharacteristic *characteristic) {
    size_t requestLength = characteristic->getLength();
    const uint8_t *bytes = characteristic->getData();
    if (requestLength < 4 || bytes == nullptr) {
      queueStatus(STATUS_MALFORMED, 0);
      wipeRequest(characteristic);
      return;
    }

    uint16_t sequence = static_cast<uint16_t>(bytes[2]) |
                        (static_cast<uint16_t>(bytes[3]) << 8);

    if (bytes[0] != PROTOCOL_VERSION) {
      queueStatus(STATUS_BAD_VERSION, sequence);
      wipeRequest(characteristic);
      return;
    }

    switch (bytes[1]) {
      case OPCODE_PING:
        queueStatus(requestLength == 4 ? STATUS_OK : STATUS_MALFORMED,
                    sequence);
        break;

      case OPCODE_TYPE_TEXT:
        if (requestLength < 5) {
          queueStatus(STATUS_MALFORMED, sequence);
        } else {
          queueStatus(acceptTextChunk(bytes + 5, requestLength - 5,
                                      bytes[4], sequence),
                      sequence);
        }
        break;

      case OPCODE_STOP:
        if (requestLength != 4) {
          queueStatus(STATUS_MALFORMED, sequence);
        } else {
          setArmed(false);
          queueStatus(STATUS_OK, sequence);
        }
        break;

      case OPCODE_KEY_ACTION:
        if (requestLength != 6) {
          queueStatus(STATUS_MALFORMED, sequence);
        } else {
          queueStatus(acceptKeyAction(bytes[4], bytes[5], sequence),
                      sequence);
        }
        break;

      case OPCODE_IDENTIFY:
        if (requestLength > 4 + MAX_IDENTIFY_LABEL_BYTES) {
          queueStatus(STATUS_MALFORMED, sequence);
        } else if (!bleConnected || !bleAuthenticated || armed ||
                   typingActive || keyActionActive) {
          queueStatus(STATUS_BUSY, sequence);
        } else {
          bool validLabel = true;
          for (size_t index = 4; index < requestLength; ++index) {
            if (bytes[index] < 0x20 || bytes[index] > 0x7e) {
              validLabel = false;
              break;
            }
          }
          if (!validLabel) {
            queueStatus(STATUS_UNSUPPORTED_TEXT, sequence);
            break;
          }
          size_t labelLength = requestLength - 4;
          portENTER_CRITICAL(&identifyMux);
          memcpy(identifyLabelBuffer, bytes + 4, labelLength);
          identifyLabelBuffer[labelLength] = '\0';
          ++identifyRevision;
          portEXIT_CRITICAL(&identifyMux);
          identifyDeadline = millis() + IDENTIFY_DURATION_MS;
          queueStatus(STATUS_OK, sequence);
        }
        break;

      case OPCODE_KEY_INTERVAL:
        if (requestLength != 6) {
          queueStatus(STATUS_MALFORMED, sequence);
        } else if (!bleConnected || !bleAuthenticated || typingActive || keyActionActive) {
          queueStatus(STATUS_BUSY, sequence);
        } else {
          uint16_t interval = static_cast<uint16_t>(bytes[4]) |
                              (static_cast<uint16_t>(bytes[5]) << 8);
          if (interval > MAX_KEY_INTERVAL_MS) {
            queueStatus(STATUS_MALFORMED, sequence);
          } else {
            characterIntervalMs = interval;
            queueStatus(STATUS_OK, sequence);
          }
        }
        break;

      case OPCODE_STORAGE_MODE:
        if (requestLength != 5 || bytes[4] > 1) {
          queueStatus(STATUS_MALFORMED, sequence);
        } else if (!bleConnected || !bleAuthenticated || armed || typingActive || keyActionActive) {
          queueStatus(STATUS_BUSY, sequence);
        } else {
          queueStatus(static_cast<uint8_t>(Storage::configure(bytes[4] == 1)), sequence);
        }
        break;

      default:
        queueStatus(STATUS_UNKNOWN_OPCODE, sequence);
        break;
    }
    wipeRequest(characteristic);
  }

  void onWrite(BLECharacteristic *characteristic) override {
    processWrite(characteristic);
  }

#if defined(CONFIG_NIMBLE_ENABLED)
  void onWrite(BLECharacteristic *characteristic,
               ble_gap_conn_desc *connection) override {
    // Use the security state attached to this exact authorized write. This is
    // immune to authentication-callback ordering on bonded reconnects.
    bleAuthenticated = connection != nullptr &&
                       (connectionMayPair || connectionWasBonded) &&
                       connection->sec_state.encrypted &&
                       connection->sec_state.authenticated;
    if (bleAuthenticated) {
      processWrite(characteristic);
    } else {
      armed = false;
      clearAllText(false);
    }
  }
#endif
};

class InfoCallbacks : public BLECharacteristicCallbacks {
  void onRead(BLECharacteristic *characteristic) override {
    auto s = Storage::snapshot();
    const auto &p = s.policy;
    // The desktop app rejects board information longer than 512 bytes. The
    // largest possible output below is about 440 bytes.
    char value[512];
    int length = snprintf(value, sizeof(value),
        "{\"schema\":1,\"firmware\":\"%s\",\"board\":\"%s\","
        "\"supported\":%s,\"present\":%s,\"exported\":%s,\"writable\":%s,"
        "\"ejected\":%s,\"error\":%s,\"bytes\":%llu",
        Firmware::VERSION,
        BoardProfile::ID,
        p.supported ? "true" : "false", p.present ? "true" : "false",
        p.exported ? "true" : "false", p.writable ? "true" : "false",
        p.ejected ? "true" : "false", p.error ? "true" : "false",
        static_cast<unsigned long long>(s.bytes));
    if (p.supported && length > 0 && static_cast<size_t>(length) < sizeof(value)) {
      const auto &io = s.io;
      // Cumulative counters since boot (microsecond times); the app takes differences.
      length += snprintf(value + length, sizeof(value) - length,
          ",\"io\":{\"rb\":%llu,\"wb\":%llu,\"rc\":%lu,\"wc\":%lu,\"mx\":%lu,"
          "\"rt\":%llu,\"wt\":%llu,\"ru\":%llu,\"wu\":%llu,\"sl\":%lu,\"er\":%lu}",
          static_cast<unsigned long long>(io.readBytes), static_cast<unsigned long long>(io.writeBytes),
          static_cast<unsigned long>(io.readCalls), static_cast<unsigned long>(io.writeCalls),
          static_cast<unsigned long>(io.largestRequestBytes),
          static_cast<unsigned long long>(io.readCallbackUs), static_cast<unsigned long long>(io.writeCallbackUs),
          static_cast<unsigned long long>(io.readSdUs), static_cast<unsigned long long>(io.writeSdUs),
          static_cast<unsigned long>(io.slowestRequestMs), static_cast<unsigned long>(io.errors));
    }
    if (length > 0 && static_cast<size_t>(length) + 1 < sizeof(value)) {
      value[length] = '}';
      value[length + 1] = '\0';
    }
    characteristic->setValue(value);
  }
};

class OtaControlCallbacks : public BLECharacteristicCallbacks {
  void onWrite(BLECharacteristic *characteristic) override {
    if (bleConnected && bleAuthenticated)
      FirmwareUpdate::control(characteristic->getData(), characteristic->getLength());
  }
};
class OtaDataCallbacks : public BLECharacteristicCallbacks {
  void onWrite(BLECharacteristic *characteristic) override {
    if (bleConnected && bleAuthenticated)
      FirmwareUpdate::data(characteristic->getData(), characteristic->getLength());
  }
};

} // namespace

#if defined(CONFIG_NIMBLE_ENABLED)
// Wrap the public advertising entry point so its otherwise-private Arduino
// server callback can be forwarded without modifying the installed framework.
// This project has one peripheral server and one advertising instance.
extern "C" int __real_ble_gap_adv_start(uint8_t ownType, const ble_addr_t *peer,
    int32_t duration, const ble_gap_adv_params *params, ble_gap_event_fn *callback, void *argument);

extern "C" int __wrap_ble_gap_adv_start(uint8_t ownType, const ble_addr_t *peer,
    int32_t duration, const ble_gap_adv_params *params, ble_gap_event_fn *callback, void *argument) {
  originalGapCallback = callback;
  originalGapArgument = argument;
  return __real_ble_gap_adv_start(ownType, peer, duration, params, guardedGapCallback, nullptr);
}
#endif

void begin() {
  responseQueue = xQueueCreate(8, sizeof(PendingResponse));
  textMutex = xSemaphoreCreateMutex();

  initializeIdentity();
  rotatePasskey();
  BLEDevice::init(deviceNameBuffer);
  BLEDevice::setMTU(517);

  bleSecurity = new BLESecurity();
  bleSecurity->setPassKey(true, devicePasskey);
  bleSecurity->setCapability(ESP_IO_CAP_OUT);
  bleSecurity->setAuthenticationMode(true, true, true);
  BLEDevice::setSecurityCallbacks(new SecurityCallbacks());

  bleServer = BLEDevice::createServer();
  bleServer->setCallbacks(new ServerCallbacks());
  bleServer->advertiseOnDisconnect(false);

  BLEService *service = bleServer->createService(BLEUUID(SERVICE_UUID), 24);

  uint32_t rxProperties = BLECharacteristic::PROPERTY_WRITE |
                          BLECharacteristic::PROPERTY_WRITE_AUTHEN;
  BLECharacteristic *rx = service->createCharacteristic(RX_UUID, rxProperties);
  rx->setAccessPermissions(ESP_GATT_PERM_WRITE_ENC_MITM);
  rx->setCallbacks(new RxCallbacks());

  uint32_t txProperties = BLECharacteristic::PROPERTY_READ |
                          BLECharacteristic::PROPERTY_NOTIFY |
                          BLECharacteristic::PROPERTY_READ_AUTHEN;
  txCharacteristic = service->createCharacteristic(TX_UUID, txProperties);
  txCharacteristic->setAccessPermissions(ESP_GATT_PERM_READ_ENC_MITM);

  BLECharacteristic *info = service->createCharacteristic(
      INFO_UUID, BLECharacteristic::PROPERTY_READ | BLECharacteristic::PROPERTY_READ_AUTHEN);
  info->setAccessPermissions(ESP_GATT_PERM_READ_ENC_MITM);
  info->setCallbacks(new InfoCallbacks());

  BLECharacteristic *otaControl = service->createCharacteristic(OTA_CONTROL_UUID,
      BLECharacteristic::PROPERTY_WRITE | BLECharacteristic::PROPERTY_WRITE_AUTHEN);
  otaControl->setAccessPermissions(ESP_GATT_PERM_WRITE_ENC_MITM);
  otaControl->setCallbacks(new OtaControlCallbacks());
  BLECharacteristic *otaData = service->createCharacteristic(OTA_DATA_UUID,
      BLECharacteristic::PROPERTY_WRITE_NR | BLECharacteristic::PROPERTY_WRITE_AUTHEN);
  otaData->setAccessPermissions(ESP_GATT_PERM_WRITE_ENC_MITM);
  otaData->setCallbacks(new OtaDataCallbacks());
  otaStatusCharacteristic = service->createCharacteristic(OTA_STATUS_UUID,
      BLECharacteristic::PROPERTY_READ | BLECharacteristic::PROPERTY_NOTIFY | BLECharacteristic::PROPERTY_READ_AUTHEN);
  otaStatusCharacteristic->setAccessPermissions(ESP_GATT_PERM_READ_ENC_MITM);
  FirmwareUpdate::begin([](const uint8_t *bytes, size_t length) {
    if (bleConnected && bleAuthenticated && otaStatusCharacteristic) {
      otaStatusCharacteristic->setValue(bytes, length);
      otaStatusCharacteristic->notify();
    }
  });

#if defined(CONFIG_BLUEDROID_ENABLED)
  // NimBLE creates its CCCD automatically for notifying characteristics.
  BLE2902 *cccd = new BLE2902();
  cccd->setAccessPermissions(ESP_GATT_PERM_READ_ENC_MITM |
                             ESP_GATT_PERM_WRITE_ENC_MITM);
  txCharacteristic->addDescriptor(cccd);
  BLE2902 *otaCccd = new BLE2902();
  otaCccd->setAccessPermissions(ESP_GATT_PERM_READ_ENC_MITM |
                              ESP_GATT_PERM_WRITE_ENC_MITM);
  otaStatusCharacteristic->addDescriptor(otaCccd);
#endif

  uint8_t initialStatus[5] = {PROTOCOL_VERSION, STATUS_OK, 0, 0, 0};
  txCharacteristic->setValue(initialStatus, sizeof(initialStatus));

  service->start();

  BLEAdvertising *bleAdvertising = BLEDevice::getAdvertising();
  bleAdvertising->addServiceUUID(SERVICE_UUID);
  bleAdvertising->setScanResponse(true);
  bleAdvertising->setMinPreferred(0x06);
  bleAdvertising->setMaxPreferred(0x12);
  refreshAdvertisingAfter(0);
}

void loop() {
  if (responseQueue != nullptr) {
    PendingResponse response;
    while (xQueueReceive(responseQueue, &response, 0) == pdTRUE) {
      sendStatus(response.status, response.sequence);
    }
  }

  if (bleConnected && advertising) {
    BLEDevice::stopAdvertising();
    advertising = false;
  }

  if (pairingOpen && !bleConnected &&
      static_cast<int32_t>(millis() - advertisingDeadline) >= 0) {
    BLEDevice::stopAdvertising();
    advertising = false;
    pairingOpen = false;
    refreshAdvertisingAfter(30);
  }

  if (advertisingRefreshRequested && !bleConnected &&
      static_cast<int32_t>(millis() - advertisingResumeAt) >= 0) {
    advertisingRefreshRequested = false;
    if (pairingOpen) {
      BLEDevice::getAdvertising()->setScanFilter(false, false);
      BLEDevice::startAdvertising();
      advertising = true;
#if defined(CONFIG_NIMBLE_ENABLED)
      advertising = ble_gap_adv_active() != 0;
      if (!advertising) refreshAdvertisingAfter(500);
#endif
    } else {
      startBondedAdvertising();
    }
  }
}

void startPairingWindow() {
  if (!disconnectCurrentClient()) {
    return;
  }
  BLEDevice::stopAdvertising();
  rotatePasskey();
  advertisingDeadline = millis() + PAIRING_WINDOW_MS;
  advertising = false;
  pairingOpen = true;
  refreshAdvertisingAfter(30);
}

bool clearBonds() {
  if (!disconnectCurrentClient()) {
    return false;
  }

  BLEDevice::stopAdvertising();
  advertising = false;
  pairingOpen = false;
  refreshAdvertisingAfter(30);
  armed = false;
  clearAllText(false);

#if defined(CONFIG_BLUEDROID_ENABLED)
  // Bond removal is asynchronous. Remove one entry at a time and wait for
  // Bluedroid's store count to shrink before proceeding to the next one.
  while (true) {
    int bondCount = esp_ble_get_bond_device_num();
    if (bondCount == 0) {
      return true;
    }
    if (bondCount < 0) {
      return false;
    }

    auto *bonds = static_cast<esp_ble_bond_dev_t *>(
        calloc(static_cast<size_t>(bondCount), sizeof(esp_ble_bond_dev_t)));
    if (bonds == nullptr) {
      return false;
    }

    int listedCount = bondCount;
    esp_err_t listResult = esp_ble_get_bond_device_list(&listedCount, bonds);
    if (listResult != ESP_OK || listedCount < 1) {
      free(bonds);
      return false;
    }

    esp_err_t removeResult = esp_ble_remove_bond_device(bonds[0].bd_addr);
    free(bonds);
    if (removeResult != ESP_OK) {
      return false;
    }

    uint32_t deadline = millis() + 1500;
    while (esp_ble_get_bond_device_num() >= bondCount &&
           static_cast<int32_t>(millis() - deadline) < 0) {
      delay(20);
    }
    if (esp_ble_get_bond_device_num() >= bondCount) {
      return false;
    }
  }
#elif defined(CONFIG_NIMBLE_ENABLED)
  // Delete each bonded peer while preserving this device's own identity keys.
  // The configured store currently allows only a few entries, but leave room
  // for future configuration changes.
  constexpr int MAX_BONDS = 16;
  ble_addr_t peers[MAX_BONDS];
  int bondCount = 0;
  int listResult =
      ble_store_util_bonded_peers(peers, &bondCount, MAX_BONDS);
  if (listResult != 0) {
    return false;
  }

  for (int index = 0; index < bondCount; ++index) {
    if (ble_store_util_delete_peer(&peers[index]) != 0) {
      return false;
    }
  }
  return true;
#else
  return false;
#endif
}

void setArmed(bool newArmed) {
  bool nextArmed = newArmed && bleConnected && bleAuthenticated && !FirmwareUpdate::active();
  bool changed = armed != nextArmed;
  armed = nextArmed;
  if (armed) {
    identifyDeadline = 0;
  }
  if (!armed) {
    clearAllText(true);
  }
  if (changed && bleConnected && bleAuthenticated) {
    queueStatus(STATUS_STATE_CHANGED, 0);
  }
}

bool connected() {
  return bleConnected;
}

bool authenticated() {
  return bleAuthenticated;
}

bool pairingWindowOpen() {
  return pairingOpen && !bleConnected;
}

bool reconnecting() {
  return bleConnected && !bleAuthenticated && connectionWasBonded && !connectionMayPair;
}

bool isArmed() {
  return armed;
}

bool typingInProgress() {
  return typingActive;
}

uint16_t keyIntervalMs() {
  return characterIntervalMs;
}

bool identifying() {
  return identifyDeadline != 0 &&
         static_cast<int32_t>(identifyDeadline - millis()) > 0;
}

const char *deviceId() {
  initializeIdentity();
  return deviceIdBuffer;
}

uint32_t copyIdentifyLabel(char *destination, size_t capacity) {
  portENTER_CRITICAL(&identifyMux);
  uint32_t revision = identifyRevision;
  if (destination != nullptr && capacity > 0) {
    size_t length = strlen(identifyLabelBuffer);
    if (length >= capacity) length = capacity - 1;
    memcpy(destination, identifyLabelBuffer, length);
    destination[length] = '\0';
  }
  portEXIT_CRITICAL(&identifyMux);
  return revision;
}

uint32_t passkey() {
  if (devicePasskey < 100000 || devicePasskey > 999999) {
    rotatePasskey();
  }
  return devicePasskey;
}

bool takeNextTextByte(uint8_t &value,
                      uint16_t &sequence,
                      bool &lastByte) {
  if (textMutex == nullptr ||
      xSemaphoreTake(textMutex, pdMS_TO_TICKS(20)) != pdTRUE) {
    return false;
  }

  bool available = typingActive && armed && bleConnected &&
                   bleAuthenticated && typingOffset < typingLength;
  if (available) {
    value = typingText[typingOffset++];
    sequence = typingSequence;
    lastByte = typingOffset == typingLength;
  }
  xSemaphoreGive(textMutex);
  return available;
}

void finishTyping(uint16_t sequence, bool success) {
  if (textMutex == nullptr ||
      xSemaphoreTake(textMutex, pdMS_TO_TICKS(20)) != pdTRUE) {
    return;
  }

  bool matches = typingActive && typingSequence == sequence;
  if (matches) {
    clearTypingLocked();
  }
  xSemaphoreGive(textMutex);

  if (!matches) {
    return;
  }
  if (!success) {
    armed = false;
  }
  queueStatus(success ? STATUS_TYPING_COMPLETE : STATUS_HID_ERROR, sequence);
  if (!success) {
    queueStatus(STATUS_STATE_CHANGED, 0);
  }
}

bool takeKeyAction(KeyAction &action) {
  if (textMutex == nullptr ||
      xSemaphoreTake(textMutex, pdMS_TO_TICKS(20)) != pdTRUE) {
    return false;
  }

  bool available = keyActionActive && armed && bleConnected &&
                   bleAuthenticated;
  if (available) {
    action = pendingKeyAction;
  }
  xSemaphoreGive(textMutex);
  return available;
}

void finishKeyAction(uint16_t sequence, bool success) {
  if (textMutex == nullptr ||
      xSemaphoreTake(textMutex, pdMS_TO_TICKS(20)) != pdTRUE) {
    return;
  }

  bool matches = keyActionActive && pendingKeyAction.sequence == sequence;
  if (matches) {
    clearKeyActionLocked();
  }
  xSemaphoreGive(textMutex);

  if (!matches) {
    return;
  }
  if (!success) {
    armed = false;
  }
  queueStatus(success ? STATUS_KEY_COMPLETE : STATUS_HID_ERROR, sequence);
  if (!success) {
    queueStatus(STATUS_STATE_CHANGED, 0);
  }
}

uint32_t pairingSecondsRemaining() {
  if (!pairingOpen) {
    return 0;
  }

  int32_t remainingMs =
      static_cast<int32_t>(advertisingDeadline - millis());
  if (remainingMs <= 0) {
    return 0;
  }
  return (static_cast<uint32_t>(remainingMs) + 999) / 1000;
}

} // namespace BleTransport
