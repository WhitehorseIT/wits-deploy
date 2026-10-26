// Phase 1c: mode selection must happen BEFORE USB.begin(). USB interfaces
// are registered by their object constructors, not by begin(), so each USB
// personality is constructed only after setup() has read bootMode. The
// framework's automatic USB startup must stay disabled in platformio.ini.
//
// The board starts as a keyboard (HID + storage) by default. A one-shot request for the
// programming personality lives in uninitialized RTC memory so it survives the deliberate
// esp_restart(). It is accepted only after a software reset and only with the expected
// marker, then immediately cleared. A crash or hang also comes up in programming mode
// (see boot_mode.h), so a firmware fault can never trap the board as a keyboard in a boot
// loop. Switching modes requires a reboot because USB descriptors cannot be changed after
// USB.begin().
//
// Dev-only: typing "hid" over serial triggers the switch. HID mode has no
// CDC interface by design; unplug/replug returns to the safe programming
// default. The real product will use the physical mode button.

#include <Arduino.h>
#include <FS.h>
#include <USB.h>
#include <USBCDC.h>
#include <USBHIDKeyboard.h>
#include <esp32-hal-tinyusb.h>

#include "ble_transport.h"
#include "firmware_version.h"
#include "status_display.h"
#include "board_hardware.h"
#include "board_profile.h"
#include "usb_storage.h"
#include "startup_trace.h"
#include "firmware_update.h"
#include "boot_mode.h"
#include "fault_test.h"

constexpr int LEFT_BUTTON_PIN = 0;  // IO00 / BOOT button
constexpr int RIGHT_BUTTON_PIN = 47;
constexpr uint32_t LONG_PRESS_MS = 2000;
constexpr uint32_t BOND_RESET_PRESS_MS = 5000;
constexpr uint32_t PROGRAM_BOOT_MAGIC = 0x57495450; // ASCII "WITP": next boot is programming mode
constexpr uint32_t PROGRAM_CHORD_MS = 3000;           // hold both buttons (T-QT Pro) for programming mode

RTC_NOINIT_ATTR uint32_t nextBootMagic;

USBCDC *usbSerial = nullptr;
USBHIDKeyboard *keyboard = nullptr;
bool hidMode = false;
bool previousBleConnection = false;
uint32_t nextKeyAt = 0;

struct ButtonState {
  bool wasPressed = false;
  bool longPressHandled = false;
  uint32_t pressedAt = 0;
};

ButtonState leftButton;
ButtonState rightButton;

uint16_t holdProgressPermille(const ButtonState &button,
                              uint32_t requiredHoldMs) {
  if (!button.wasPressed || button.longPressHandled) {
    return 0;
  }

  uint32_t elapsed = millis() - button.pressedAt;
  if (elapsed >= requiredHoldMs) {
    return 1000;
  }
  return static_cast<uint16_t>((elapsed * 1000) / requiredHoldMs);
}

void logLine(const char *message) {
  if (usbSerial != nullptr) {
    usbSerial->println(message);
  }
}

void setup() {
  // RTC_NOINIT memory is undefined after power loss, so a request for programming mode
  // needs both an exact marker and a software reset. Clear it before starting USB so any
  // later reset takes the default path.
  BootMode::Reset resetKind = BootMode::Reset::Other;
  switch (esp_reset_reason()) {
    case ESP_RST_POWERON: resetKind = BootMode::Reset::PowerOn; break;
    case ESP_RST_EXT: resetKind = BootMode::Reset::External; break;
    case ESP_RST_SW: resetKind = BootMode::Reset::Software; break;
    case ESP_RST_PANIC:
    case ESP_RST_INT_WDT:
    case ESP_RST_TASK_WDT:
    case ESP_RST_WDT: resetKind = BootMode::Reset::Fault; break;
    default: break;
  }
  hidMode = !BootMode::programMode(resetKind, nextBootMagic, PROGRAM_BOOT_MAGIC);
  nextBootMagic = 0;
#if WITS_HAS_STORAGE
  esp_rom_printf("[WITS] firmware=%s reset_reason=%u mode=%s\n", Firmware::VERSION,
                 static_cast<unsigned>(esp_reset_reason()), hidMode ? "HID+MSC" : "PROGRAM");
#endif
  StartupTrace::mark("Board IO begin");
  bool boardReady = BoardHardware::begin();
  StartupTrace::mark("Board IO ready");
#if !WITS_HAS_TOUCHSCREEN
  pinMode(LEFT_BUTTON_PIN, INPUT_PULLUP);
  pinMode(RIGHT_BUTTON_PIN, INPUT_PULLUP);
#endif

  if (hidMode) {
    // Construction registers the HID interface; begin() initializes its
    // report synchronization primitives. Both must happen before USB.begin().
    StartupTrace::mark("HID interface begin");
    keyboard = new USBHIDKeyboard();
    keyboard->begin();
    StartupTrace::mark("HID interface ready; MSC begin");
    Storage::begin();
    StartupTrace::mark("MSC ready");
    USB.productName("WITS Deployment Keyboard");
  } else {
    // ARDUINO_USB_CDC_ON_BOOT is deliberately off, so create CDC ourselves
    // only for the programming personality.
    usbSerial = new USBCDC();
    usbSerial->begin(115200);
    USB.productName("WITS Deploy Programming");
  }
  StartupTrace::mark("USB begin");
  bool usbReady = USB.begin();
  FirmwareUpdate::confirmBoot(boardReady && usbReady);
  StartupTrace::mark("USB ready; display begin");
  StatusDisplay::begin();
  StartupTrace::mark("Display ready");

  if (hidMode) {
    StartupTrace::mark("BLE begin");
    BleTransport::begin();
    StartupTrace::mark("BLE ready");
  }

  if (usbSerial != nullptr) {
    usbSerial->print("WITS Deploy firmware ");
    usbSerial->println(Firmware::VERSION);
  }
  logLine("Booted in programming mode (CDC only).");
  logLine("Type 'hid' + Enter to switch to HID mode (reboots).");
  logLine("Type 'bootloader' + Enter to enter the ROM flasher.");

  StatusDisplay::update(hidMode, false, false, false, false, false, false, 0);
  StartupTrace::mark("Startup complete");
}

void switchToHidMode() {
  StartupTrace::mark("HID mode requested");
  if (usbSerial != nullptr) {
    usbSerial->println("Switching to HID mode, rebooting...");
    usbSerial->flush();
  }
  delay(100);
  if (!StatusDisplay::prepareRestart()) {
    StartupTrace::mark("HID switch canceled: display cleanup failed");
    return;
  }
  nextBootMagic = 0;  // HID is the default boot
  StartupTrace::mark("Entering esp_restart for HID mode");
  esp_restart();
}

void switchToBootloader() {
  StatusDisplay::showBootloader();
  if (usbSerial != nullptr) {
    usbSerial->println("Switching to ROM bootloader...");
    usbSerial->flush();
  }
  // Give the LCD controller time to latch the final frame. The application
  // cannot redraw once the ESP32-S3 ROM downloader takes control.
  delay(300);
  if (!StatusDisplay::prepareRestart()) return;
  StartupTrace::mark("Entering ROM bootloader");
  usb_persist_restart(RESTART_BOOTLOADER);
}

void emergencyStop() {
  BleTransport::setArmed(false);
  if (keyboard != nullptr) {
    keyboard->releaseAll();
  }
}

void switchToProgrammingMode() {
  // A writable host filesystem must finish its eject before resetting USB.
  if (!Storage::prepareRestart()) {
    StatusDisplay::showStorageBusy();
    return;
  }
  emergencyStop();
  StartupTrace::mark("Programming mode requested");
  if (!StatusDisplay::prepareRestart()) return;
  nextBootMagic = PROGRAM_BOOT_MAGIC;
  StartupTrace::mark("Entering esp_restart for programming mode");
  esp_restart();
}

void updateKeyboardOutput() {
  if (keyboard == nullptr || !BleTransport::typingInProgress()) {
    nextKeyAt = millis();
    return;
  }
  if (static_cast<int32_t>(millis() - nextKeyAt) < 0) {
    return;
  }

  uint8_t value = 0;
  uint16_t sequence = 0;
  bool lastByte = false;
  if (!BleTransport::takeNextTextByte(value, sequence, lastByte)) {
    return;
  }

  bool written = keyboard->write(value) != 0;
  if (!written || lastByte) {
    if (!written) {
      keyboard->releaseAll();
    }
    BleTransport::finishTyping(sequence, written);
  }
  nextKeyAt = millis() + BleTransport::keyIntervalMs();
}

uint8_t keyCodeToHidUsage(uint8_t keyCode) {
  if (keyCode >= 'A' && keyCode <= 'Z') {
    return HID_KEY_A + (keyCode - 'A');
  }
  if (keyCode >= '1' && keyCode <= '9') {
    return HID_KEY_1 + (keyCode - '1');
  }
  if (keyCode == '0') return HID_KEY_0;
  if (keyCode >= BleTransport::KEY_CODE_F1 &&
      keyCode <= BleTransport::KEY_CODE_F12) {
    return HID_KEY_F1 + (keyCode - BleTransport::KEY_CODE_F1);
  }

  switch (keyCode) {
    case BleTransport::KEY_CODE_BACKSPACE: return HID_KEY_BACKSPACE;
    case BleTransport::KEY_CODE_DELETE: return HID_KEY_DELETE;
    case BleTransport::KEY_CODE_ENTER: return HID_KEY_ENTER;
    case BleTransport::KEY_CODE_TAB: return HID_KEY_TAB;
    case BleTransport::KEY_CODE_ESCAPE: return HID_KEY_ESCAPE;
    case BleTransport::KEY_CODE_LEFT: return HID_KEY_ARROW_LEFT;
    case BleTransport::KEY_CODE_RIGHT: return HID_KEY_ARROW_RIGHT;
    case BleTransport::KEY_CODE_UP: return HID_KEY_ARROW_UP;
    case BleTransport::KEY_CODE_DOWN: return HID_KEY_ARROW_DOWN;
    case BleTransport::KEY_CODE_HOME: return HID_KEY_HOME;
    case BleTransport::KEY_CODE_END: return HID_KEY_END;
    case BleTransport::KEY_CODE_PAGE_UP: return HID_KEY_PAGE_UP;
    case BleTransport::KEY_CODE_PAGE_DOWN: return HID_KEY_PAGE_DOWN;
    case BleTransport::KEY_CODE_INSERT: return HID_KEY_INSERT;
    case BleTransport::KEY_CODE_SPACE: return HID_KEY_SPACE;
    default: return HID_KEY_NONE;
  }
}

void updateKeyAction() {
  if (keyboard == nullptr || BleTransport::typingInProgress()) {
    return;
  }

  BleTransport::KeyAction action = {};
  if (!BleTransport::takeKeyAction(action)) {
    return;
  }

  uint8_t usage = keyCodeToHidUsage(action.keyCode);
  bool valid = usage != HID_KEY_NONE;
  if (valid) {
    KeyReport report = {};
    report.modifiers = action.modifiers;
    report.keys[0] = usage;
    keyboard->sendReport(&report);
    delay(30);
  }
  keyboard->releaseAll();
  BleTransport::finishKeyAction(action.sequence, valid);
}

void updateLeftButton() {
  bool pressed = digitalRead(LEFT_BUTTON_PIN) == LOW;
  if (pressed && !leftButton.wasPressed) {
    leftButton.pressedAt = millis();
    leftButton.longPressHandled = false;
  }

  if (pressed && !leftButton.longPressHandled &&
      millis() - leftButton.pressedAt >= LONG_PRESS_MS) {
    emergencyStop();
    BleTransport::startPairingWindow();
    leftButton.longPressHandled = true;
  }

  if (!pressed && leftButton.wasPressed && !leftButton.longPressHandled) {
    emergencyStop();
  }
  leftButton.wasPressed = pressed;
}

void updateRightButton() {
  bool pressed = digitalRead(RIGHT_BUTTON_PIN) == LOW;
  if (pressed && !rightButton.wasPressed) {
    rightButton.pressedAt = millis();
    rightButton.longPressHandled = false;
  }

  if (pressed && !rightButton.longPressHandled &&
      millis() - rightButton.pressedAt >= BOND_RESET_PRESS_MS) {
    emergencyStop();
    if (BleTransport::clearBonds()) {
      StatusDisplay::showPairingCleared();
    }
    rightButton.longPressHandled = true;
  }

  if (!pressed && rightButton.wasPressed && !rightButton.longPressHandled) {
    if (millis() - rightButton.pressedAt < LONG_PRESS_MS &&
        BleTransport::authenticated()) {
      BleTransport::setArmed(!BleTransport::isArmed());
      if (!BleTransport::isArmed() && keyboard != nullptr) {
        keyboard->releaseAll();
      }
    }
  }
  rightButton.wasPressed = pressed;
}

void updateProgrammingButtons() {
  bool leftPressed = digitalRead(LEFT_BUTTON_PIN) == LOW;
  if (leftPressed && !leftButton.wasPressed) {
    leftButton.pressedAt = millis();
    leftButton.longPressHandled = false;
  }

  if (leftPressed && !leftButton.longPressHandled &&
      millis() - leftButton.pressedAt >= LONG_PRESS_MS) {
    leftButton.longPressHandled = true;
    switchToBootloader();
  }
  leftButton.wasPressed = leftPressed;

  bool rightPressed = digitalRead(RIGHT_BUTTON_PIN) == LOW;
  if (rightPressed && !rightButton.wasPressed) {
    rightButton.pressedAt = millis();
    rightButton.longPressHandled = false;
  }

  if (rightPressed && !rightButton.longPressHandled &&
      millis() - rightButton.pressedAt >= LONG_PRESS_MS) {
    rightButton.longPressHandled = true;
    switchToHidMode();
  }

  rightButton.wasPressed = rightPressed;
}

#if !WITS_HAS_TOUCHSCREEN
uint16_t programChordPermille = 0;  // progress for the on-screen PROGRAM bar
// T-QT Pro has no touch menu, so holding both buttons for 3 seconds enters programming mode.
// While both are down, the single-button actions (pairing, arming, clearing bonds) are
// suppressed, including when each button is released.
void updateProgramChord() {
  static bool active = false;
  static uint32_t startedAt = 0;
  bool both = digitalRead(LEFT_BUTTON_PIN) == LOW && digitalRead(RIGHT_BUTTON_PIN) == LOW;
  if (!both) {
    active = false;
    programChordPermille = 0;
    return;
  }
  if (!active) {
    active = true;
    startedAt = millis();
    emergencyStop();
  }
  leftButton.longPressHandled = true;
  rightButton.longPressHandled = true;
  uint32_t held = millis() - startedAt;
  programChordPermille = held >= PROGRAM_CHORD_MS ? 1000 : static_cast<uint16_t>(held * 1000 / PROGRAM_CHORD_MS);
  if (held >= PROGRAM_CHORD_MS) {
    active = false;
    switchToProgrammingMode();
  }
}
#endif

void loop() {
#ifdef WITS_FAULT_TEST
  FaultTest::poll(hidMode);
#endif
  if (hidMode) {
    FirmwareUpdate::loop();
    if (FirmwareUpdate::active()) {
      BleTransport::loop();
      delay(1);
      return;
    }
  }
  switch (StatusDisplay::pollAction()) {
    case StatusDisplay::Action::Hid: switchToHidMode(); break;
    case StatusDisplay::Action::Program: switchToProgrammingMode(); break;
    case StatusDisplay::Action::Flash: switchToBootloader(); break;
    case StatusDisplay::Action::Stop: emergencyStop(); break;
    case StatusDisplay::Action::Pair:
      emergencyStop();
      BleTransport::startPairingWindow();
      break;
    case StatusDisplay::Action::Clear:
      emergencyStop();
      if (BleTransport::clearBonds()) StatusDisplay::showPairingCleared();
      break;
    case StatusDisplay::Action::Arm:
      if (hidMode && BleTransport::authenticated()) {
        BleTransport::setArmed(!BleTransport::isArmed());
        if (!BleTransport::isArmed()) emergencyStop();
      }
      break;
    case StatusDisplay::Action::None: break;
  }
  if (usbSerial != nullptr && usbSerial->available()) {
    String line = usbSerial->readStringUntil('\n');
    line.trim();
    if (line == "hid") {
      switchToHidMode();
    } else if (line == "bootloader") {
      switchToBootloader();
    }
  }

  if (hidMode) {
    Storage::loop();
    BleTransport::loop();
#if !WITS_HAS_TOUCHSCREEN
    updateLeftButton();
    updateRightButton();
    updateProgramChord();
#endif
    updateKeyboardOutput();
    updateKeyAction();

    bool bleConnection = BleTransport::connected();
    if (previousBleConnection && !bleConnection) {
      emergencyStop();
    }
    previousBleConnection = bleConnection;

    StatusDisplay::update(
        true,
        bleConnection,
        BleTransport::authenticated(),
        BleTransport::pairingWindowOpen(),
        BleTransport::isArmed(),
        BleTransport::typingInProgress(),
        BleTransport::identifying(),
        BleTransport::pairingSecondsRemaining());
    StatusDisplay::updateHoldProgress(
        holdProgressPermille(leftButton, LONG_PRESS_MS),
        holdProgressPermille(rightButton, BOND_RESET_PRESS_MS));
#if !WITS_HAS_TOUCHSCREEN
    StatusDisplay::updateProgramChord(programChordPermille);
#endif
  } else {
#if !WITS_HAS_TOUCHSCREEN
    updateProgrammingButtons();
#endif
    StatusDisplay::update(false, false, false, false, false, false, false, 0);
    StatusDisplay::updateHoldProgress(
        holdProgressPermille(leftButton, LONG_PRESS_MS),
        holdProgressPermille(rightButton, LONG_PRESS_MS));
  }

  delay(20);
}
