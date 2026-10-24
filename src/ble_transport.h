#pragma once

#include <Arduino.h>

namespace BleTransport {

constexpr uint32_t PAIRING_WINDOW_MS = 60000;
constexpr uint32_t IDENTIFY_DURATION_MS = 5000;
constexpr size_t MAX_TEXT_BYTES = 2048;
constexpr size_t MAX_IDENTIFY_LABEL_BYTES = 32;
constexpr uint16_t DEFAULT_KEY_INTERVAL_MS = 25;
constexpr uint16_t MAX_KEY_INTERVAL_MS = 2000;

enum KeyCode : uint8_t {
  KEY_CODE_BACKSPACE = 0x01,
  KEY_CODE_DELETE = 0x02,
  KEY_CODE_ENTER = 0x03,
  KEY_CODE_TAB = 0x04,
  KEY_CODE_ESCAPE = 0x05,
  KEY_CODE_LEFT = 0x06,
  KEY_CODE_RIGHT = 0x07,
  KEY_CODE_UP = 0x08,
  KEY_CODE_DOWN = 0x09,
  KEY_CODE_HOME = 0x0a,
  KEY_CODE_END = 0x0b,
  KEY_CODE_PAGE_UP = 0x0c,
  KEY_CODE_PAGE_DOWN = 0x0d,
  KEY_CODE_INSERT = 0x0e,
  KEY_CODE_F1 = 0x10,
  KEY_CODE_F12 = 0x1b,
  KEY_CODE_SPACE = 0x20,
};

constexpr uint8_t MODIFIER_CTRL = 0x01;
constexpr uint8_t MODIFIER_SHIFT = 0x02;
constexpr uint8_t MODIFIER_ALT = 0x04;
constexpr uint8_t MODIFIER_GUI = 0x08;

struct KeyAction {
  uint8_t keyCode;
  uint8_t modifiers;
  uint16_t sequence;
};

void begin();
void loop();
void startPairingWindow();
bool clearBonds();
void setArmed(bool armed);

bool connected();
bool authenticated();
bool pairingWindowOpen();
bool reconnecting();
bool isArmed();
bool typingInProgress();
uint16_t keyIntervalMs();
bool identifying();
const char *deviceId();
uint32_t copyIdentifyLabel(char *destination, size_t capacity);
uint32_t passkey();
uint32_t pairingSecondsRemaining();
bool takeNextTextByte(uint8_t &value, uint16_t &sequence, bool &lastByte);
void finishTyping(uint16_t sequence, bool success);
bool takeKeyAction(KeyAction &action);
void finishKeyAction(uint16_t sequence, bool success);

} // namespace BleTransport
