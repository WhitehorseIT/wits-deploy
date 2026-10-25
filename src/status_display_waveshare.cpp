#ifdef WITS_BOARD_WAVESHARE7
#include "status_display.h"
#include "board_hardware.h"
#include "ble_transport.h"
#include "firmware_version.h"
#include "usb_storage.h"
#include "startup_trace.h"
#include <Arduino_GFX_Library.h>

namespace {
esp_lcd_panel_handle_t activeRgbPanel = nullptr;
}

// The GFX library keeps its driver handle private. Capture creation via the
// linker, then use IDF's supported delete API; do not depend on class layout
// or modify the installed library. There is one RGB panel in this firmware.
extern "C" esp_err_t __real_esp_lcd_new_rgb_panel(
    const esp_lcd_rgb_panel_config_t *, esp_lcd_panel_handle_t *);
extern "C" esp_err_t __wrap_esp_lcd_new_rgb_panel(
    const esp_lcd_rgb_panel_config_t *config, esp_lcd_panel_handle_t *result) {
  esp_err_t error = __real_esp_lcd_new_rgb_panel(config, result);
  if (error == ESP_OK) activeRgbPanel = *result;
  return error;
}

namespace StatusDisplay {
namespace {
// RGB565, ST7262, manufacturer timings and pin mapping (base 7-inch model).
Arduino_ESP32RGBPanel *panel = new Arduino_ESP32RGBPanel(
    5, 3, 46, 7, 1, 2, 42, 41, 40, 39, 0, 45, 48, 47, 21,
    14, 38, 18, 17, 10,
    0, 8, 4, 8, 0, 8, 4, 8, 1, 16000000, false, 0, 0, 800 * 10);
Arduino_RGB_Display *gfx = new Arduino_RGB_Display(800, 480, panel);
constexpr uint16_t WHITE = 0xffff;
constexpr uint16_t MUTED = 0xbdf7;
constexpr uint16_t BLUE = 0x10e8;
constexpr uint16_t RED = 0xa8c4;
constexpr uint16_t TEAL = 0x02c9;
constexpr uint16_t GRAY = 0x2965;
constexpr uint16_t AMBER = 0xfea0;
constexpr uint16_t DARK = 0x1082;
bool initialized = false;
bool hid = false;
bool authenticated = false;
bool armed = false;
bool bootloader = false;
uint32_t noticeUntil = 0;
String previous;
uint32_t previousPairingSeconds = UINT32_MAX;
Action heldAction = Action::None;
int heldButton = -1;
uint32_t heldAt = 0;
uint32_t lastTouchAt = 0;
bool touchDown = false;
bool handled = false;
bool canceled = false;
bool waitForRelease = false;
int previousProgress = -1;

void text(const char *value, int x, int y, int scale, uint16_t color = WHITE) {
  gfx->setTextColor(color);
  gfx->setTextSize(scale);
  gfx->setCursor(x, y);
  gfx->print(value);
}
int buttonX(int index) { return hid ? 14 + index * 156 : 35 + index * 385; }
int buttonWidth() { return hid ? 148 : 345; }
void button(int index, const char *label, uint16_t background, uint16_t foreground = WHITE) {
  int x = buttonX(index);
  int width = buttonWidth();
  gfx->fillRoundRect(x, 375, width, 85, 8, background);
  gfx->drawRoundRect(x, 375, width, 85, 8, WHITE);
  text(label, x + (width - strlen(label) * 18) / 2, 399, 3, foreground);
}
void frame(const char *headline, uint16_t background) {
  gfx->fillScreen(background);
  text("WITS DEPLOY", 24, 18, 3);
  String version = String("FW ") + Firmware::VERSION;
  text(version.c_str(), 800 - 24 - version.length() * 12, 22, 2, MUTED);
  text(headline, 24, 78, 5);
}

constexpr char PAIRING_HINT[] = "Enter on computer - ";
void pairingCountdown(uint32_t seconds, uint16_t background) {
  char countdown[8];
  snprintf(countdown, sizeof(countdown), "%2lus", static_cast<unsigned long>(seconds));
  gfx->setTextColor(MUTED, background);
  gfx->setTextSize(3);
  gfx->setCursor(24 + (sizeof(PAIRING_HINT) - 1) * 18, 222);
  gfx->print(countdown);
}

int hit(uint16_t x, uint16_t y) {
  if (y < 375 || y >= 460) return -1;
  for (int i = 0; i < (hid ? 5 : 2); ++i)
    if (x >= buttonX(i) && x < buttonX(i) + buttonWidth()) return i;
  return -1;
}
Action actionFor(int index) {
  if (!hid) return index == 0 ? Action::Flash : Action::Hid;
  switch (index) {
    case 0: return Action::Pair;
    case 1: return Action::Stop;
    case 2: return authenticated ? Action::Arm : Action::None;
    case 3: return Action::Clear;
    case 4: return Action::Program;
    default: return Action::None;
  }
}
uint32_t holdDuration(Action action) {
  if (action == Action::Clear) return 5000;
  if (action == Action::Pair || action == Action::Flash || action == Action::Hid || action == Action::Program) return 2000;
  return 0;
}
void progress(int pixels) {
  if (heldButton < 0 || previousProgress == pixels) return;
  int width = buttonWidth() - 20;
  gfx->fillRect(buttonX(heldButton) + 10, 445, width, 6, GRAY);
  if (pixels > 0) gfx->fillRect(buttonX(heldButton) + 10, 445, pixels, 6, WHITE);
  previousProgress = pixels;
}
} // namespace

void begin() {
  initialized = gfx->begin();
  if (!initialized) return;
  gfx->setTextWrap(false);
  gfx->fillScreen(BLUE);
  BoardHardware::backlightOn();
}

bool prepareRestart() {
  if (activeRgbPanel == nullptr) return true;
  StartupTrace::mark("Stopping RGB display before restart");
  // Stop the continuously running LCD/GDMA path while the scheduler, caches
  // and PSRAM are still available. esp_restart disables caches later.
  esp_err_t error = esp_lcd_panel_del(activeRgbPanel);
  if (error != ESP_OK) {
    esp_rom_printf("[WITS] RGB cleanup failed: %s\n", esp_err_to_name(error));
    return false;
  }
  activeRgbPanel = nullptr;
  initialized = false; // gfx's framebuffer is freed; never draw again this boot.
  BoardHardware::backlightOff();
  StartupTrace::mark("RGB display stopped");
  return true;
}

Action pollAction() {
  if (!initialized || bootloader) return Action::None;
  bool pressed = false;
  uint16_t x = 0, y = 0;
  bool fresh = BoardHardware::readTouch(pressed, x, y);
  if (fresh) lastTouchAt = millis();
  else if (millis() - lastTouchAt <= 200) {
    // Keep the last sample only briefly; a failed touch link cannot finish a hold.
    pressed = touchDown;
    if (touchDown) { x = buttonX(heldButton < 0 ? 0 : heldButton) + 20; y = 400; }
  }
  if (noticeUntil) {
    touchDown = pressed;
    waitForRelease = pressed;
    return Action::None;
  }
  if (waitForRelease) {
    if (!pressed) { waitForRelease = false; touchDown = false; }
    return Action::None;
  }
  if (pressed && !touchDown) {
    heldButton = hit(x, y);
    heldAction = heldButton < 0 ? Action::None : actionFor(heldButton);
    heldAt = millis();
    handled = false;
    canceled = false;
    previousProgress = -1;
    touchDown = true;
    if (heldAction == Action::Stop) { handled = true; return heldAction; }
  }
  if (pressed && touchDown) {
    if (hit(x, y) != heldButton) canceled = true;
    uint32_t duration = holdDuration(heldAction);
    if (!handled && !canceled && duration > 0) {
      uint32_t elapsed = millis() - heldAt;
      progress(min(elapsed, duration) * (buttonWidth() - 20) / duration);
      if (elapsed >= duration) { handled = true; return heldAction; }
    } else if (canceled) progress(0);
  }
  if (!pressed && touchDown) {
    touchDown = false;
    progress(0);
    Action action = !handled && !canceled && heldAction == Action::Arm ? heldAction : Action::None;
    heldButton = -1;
    return action;
  }
  return Action::None;
}

void showBootloader() {
  if (!initialized) return;
  bootloader = true;
  frame("BOOTLOADER MODE", BLUE);
  text("Press RESET to resume", 24, 180, 4);
}
void showPairingCleared() {
  if (!initialized) return;
  frame("BT PAIRINGS CLEARED", TEAL);
  noticeUntil = millis() + 3000;
  previous = "";
}
void showStorageBusy() {
  if (!initialized) return;
  frame("EJECT SD DRIVE FIRST", BLUE);
  text("Safely eject on the connected PC", 24, 180, 3);
  text("Then hold PROGRAM again", 24, 230, 3);
  noticeUntil = millis() + 3000;
  previous = "";
}
void showUpdate() {
  if (!initialized) return;
  frame("BLUETOOTH UPDATE", BLUE);
  text("Follow progress in the app", 24, 172, 3);
  text("Keep power connected", 24, 230, 3);
}
void updateHoldProgress(uint16_t, uint16_t) {}

void update(bool hidMode, bool connected, bool secured, bool pairing,
            bool isArmed, bool typing, bool identifying, uint32_t pairingSeconds) {
  if (!initialized || bootloader) return;
  if (noticeUntil && int32_t(millis() - noticeUntil) < 0) return;
  noticeUntil = 0;
  if ((hid != hidMode || authenticated != secured || armed != isArmed) && touchDown)
    waitForRelease = true;
  hid = hidMode;
  authenticated = secured;
  armed = isArmed;
  auto storage = Storage::snapshot();
  const auto &p = storage.policy;
  char alias[BleTransport::MAX_IDENTIFY_LABEL_BYTES + 1] = {};
  if (identifying) BleTransport::copyIdentifyLabel(alias, sizeof(alias));
  bool reconnecting = BleTransport::reconnecting();
  bool pinVisible = pairing || (connected && !secured && !reconnecting);
  uint16_t background = isArmed ? RED : secured ? TEAL : BLUE;
  String key = String(hid) + connected + secured + pairing + isArmed + typing + identifying +
               ":" + reconnecting + ":" + (pinVisible ? BleTransport::passkey() : 0) +
               ":" + alias + ":" + p.present + p.exported + p.writable + p.error;
  if (key == previous) {
    if (pairing && pairingSeconds != previousPairingSeconds)
      pairingCountdown(pairingSeconds, background);
    previousPairingSeconds = pairingSeconds;
    return;
  }
  previous = key;
  previousPairingSeconds = pairingSeconds;
  const char *state = !hid ? "PROGRAMMING MODE" :
      typing && isArmed ? "TYPING" : isArmed ? "ARMED" :
      pairing ? "PAIRING" : connected && !secured ? "CONNECTING" :
      connected ? "DISARMED" : "OFFLINE / DISARMED";
  frame(state, background);
  if (pinVisible) {
    char pin[40];
    snprintf(pin, sizeof(pin), "PIN %06lu", static_cast<unsigned long>(BleTransport::passkey()));
    text(pin, 24, 153, 7);
    text(pairing ? PAIRING_HINT : "Enter PIN on computer", 24, 222, 3, MUTED);
    if (pairing) pairingCountdown(pairingSeconds, background);
  } else if (identifying) {
    // Fixed-size ASCII font; at most 32 characters fit at scale 3.
    text(alias[0] ? alias : BleTransport::deviceId(), 24, 160, 3);
  } else {
    String identity = String("Device ") + BleTransport::deviceId();
    text(identity.c_str(), 24, 165, 4);
    text(!hid ? "Hold HID to start keyboard + storage" :
         secured ? "Use ARM to enable keyboard output" : "Hold PAIR to add a computer",
         24, 225, 2, MUTED);
  }
  String storageText = !hid ? "Storage available in HID mode" :
      p.error ? "SD ERROR - reset to retry" : !p.present ? "SD unavailable - insert card, then reset" :
      !p.exported ? "SD EJECTED - choose access in app to remount" :
      p.writable ? "SD: READ / WRITE" : "SD: READ ONLY";
  text(storageText.c_str(), 24, 289, 2);
  if (p.present) {
    String capacity = String(static_cast<unsigned long>(storage.bytes / (1024 * 1024))) + " MiB";
    text(capacity.c_str(), 24, 320, 2, MUTED);
  }
  if (!BoardHardware::touchAvailable()) text("TOUCH NOT DETECTED", 420, 320, 2);
  if (hid) {
    button(0, "PAIR", GRAY);
    button(1, "STOP", WHITE, RED);
    button(2, isArmed ? "DISARM" : "ARM", secured ? AMBER : GRAY, secured ? DARK : MUTED);
    button(3, "CLEAR", GRAY);
    button(4, "PROGRAM", GRAY);
  } else { button(0, "FLASH", GRAY); button(1, "HID", TEAL); }
  previousProgress = -1;
}
} // namespace StatusDisplay
#endif
