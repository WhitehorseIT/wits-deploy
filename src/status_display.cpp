#include "status_display.h"

#include "ble_transport.h"
#include "firmware_version.h"

#include <Arduino_GFX_Library.h>

namespace StatusDisplay {
namespace {

constexpr int BACKLIGHT_PIN = 10;
constexpr int DISPLAY_WIDTH = 128;
constexpr int DISPLAY_HEIGHT = 128;
constexpr uint32_t PAIRING_CLEARED_NOTICE_MS = 3000;
constexpr int HOLD_BAR_Y = 101;
constexpr int HOLD_BAR_HEIGHT = 6;
constexpr int HOLD_BAR_WIDTH = 54;
constexpr int LEFT_HOLD_BAR_X = 6;
constexpr int RIGHT_HOLD_BAR_X = 68;

constexpr uint16_t rgb565(uint8_t red, uint8_t green, uint8_t blue) {
  return static_cast<uint16_t>(((red & 0xf8) << 8) |
                               ((green & 0xfc) << 3) |
                               (blue >> 3));
}

constexpr uint16_t COLOR_BLACK = rgb565(0, 0, 0);
constexpr uint16_t COLOR_WHITE = rgb565(255, 255, 255);
constexpr uint16_t COLOR_MUTED = rgb565(178, 198, 208);
constexpr uint16_t COLOR_PROGRAM = rgb565(16, 63, 102);
constexpr uint16_t COLOR_BOOTLOADER = rgb565(65, 35, 112);
constexpr uint16_t COLOR_PAIRING = rgb565(151, 86, 0);
constexpr uint16_t COLOR_DISCONNECTED = rgb565(47, 55, 61);
constexpr uint16_t COLOR_SECURING = rgb565(89, 64, 10);
constexpr uint16_t COLOR_READY = rgb565(0, 91, 83);
constexpr uint16_t COLOR_ARMED = rgb565(174, 25, 35);

Arduino_DataBus *bus =
    new Arduino_ESP32SPI(6, 5, 3, 2, GFX_NOT_DEFINED);
Arduino_GFX *gfx = new Arduino_GC9107(bus, 1, 0, true);

enum class ScreenState : uint8_t {
  Unknown,
  Program,
  Disconnected,
  Pairing,
  Securing,
  Ready,
  Armed,
  Typing,
  Identify,
};

bool initialized = false;
ScreenState previousState = ScreenState::Unknown;
uint32_t previousPairingSeconds = UINT32_MAX;
uint32_t previousPasskey = UINT32_MAX;
uint32_t previousIdentifyRevision = 0;
bool previousReconnecting = false;
bool pairingClearedNoticeActive = false;
uint32_t pairingClearedNoticeStartedAt = 0;
ScreenState holdBarsState = ScreenState::Unknown;
int previousLeftHoldPixels = -1;
int previousRightHoldPixels = -1;
uint16_t currentBackground = COLOR_BLACK;

void centeredText(const char *text,
                  int y,
                  uint8_t size,
                  uint16_t color) {
  int width = static_cast<int>(strlen(text)) * 6 * size;
  int x = max(0, (DISPLAY_WIDTH - width) / 2);
  gfx->setTextSize(size);
  gfx->setTextColor(color);
  gfx->setCursor(x, y);
  gfx->print(text);
}

void centeredPasskey(int y, uint8_t size, uint16_t color) {
  char passkey[7];
  snprintf(passkey, sizeof(passkey), "%06lu",
           static_cast<unsigned long>(BleTransport::passkey()));
  centeredText(passkey, y, size, color);
}

void drawFrame(uint16_t background, uint16_t accent) {
  currentBackground = background;
  gfx->fillScreen(background);
  gfx->fillRect(0, 0, DISPLAY_WIDTH, 5, accent);
}

void drawPairingCountdown(uint32_t seconds) {
  // The pairing window is at most 60 seconds. Keep a fixed three-character
  // field so the 10s -> 9s transition overwrites the previous leading digit.
  char countdown[8];
  snprintf(countdown, sizeof(countdown), "%2lus", static_cast<unsigned long>(seconds));
  gfx->setTextSize(2);
  gfx->setTextColor(COLOR_WHITE, COLOR_PAIRING);
  gfx->setCursor((DISPLAY_WIDTH - 3 * 6 * 2) / 2, 38);
  gfx->print(countdown);
}

bool leftActionNeedsHold(ScreenState state) {
  return state == ScreenState::Program ||
         state == ScreenState::Disconnected ||
         state == ScreenState::Pairing ||
         state == ScreenState::Securing ||
         state == ScreenState::Ready ||
         state == ScreenState::Identify;
}

bool rightActionNeedsHold(ScreenState state) {
  return state == ScreenState::Program ||
         state == ScreenState::Disconnected ||
         state == ScreenState::Pairing ||
         state == ScreenState::Securing;
}

int holdPixels(uint16_t permille) {
  constexpr int innerWidth = HOLD_BAR_WIDTH - 2;
  uint16_t bounded = permille > 1000 ? 1000 : permille;
  return static_cast<int>((static_cast<uint32_t>(bounded) * innerWidth) /
                          1000);
}

void drawHoldBar(int x, int filledPixels, bool visible) {
  gfx->fillRect(x, HOLD_BAR_Y, HOLD_BAR_WIDTH, HOLD_BAR_HEIGHT,
                currentBackground);
  if (!visible) {
    return;
  }

  gfx->drawRect(x, HOLD_BAR_Y, HOLD_BAR_WIDTH, HOLD_BAR_HEIGHT, COLOR_MUTED);
  if (filledPixels > 0) {
    gfx->fillRect(x + 1, HOLD_BAR_Y + 1, filledPixels,
                  HOLD_BAR_HEIGHT - 2, COLOR_WHITE);
  }
}

void drawButtonHints(const char *leftAction,
                     const char *rightAction,
                     uint16_t color = COLOR_WHITE) {
  constexpr int y = 110;
  constexpr int preferredInset = 6;
  constexpr int minimumGap = 4;
  constexpr int textScale = 2;
  int leftWidth = leftAction == nullptr ? 0 : strlen(leftAction) * 6 * textScale;
  int rightWidth = rightAction == nullptr ? 0 : strlen(rightAction) * 6 * textScale;
  // Keep long action names readable at scale 2 without overlapping STOP.
  int horizontalInset = min(preferredInset,
      max(0, (DISPLAY_WIDTH - leftWidth - rightWidth - minimumGap) / 2));
  gfx->setTextSize(textScale);
  gfx->setTextColor(color);

  if (leftAction != nullptr && leftAction[0] != '\0') {
    gfx->setCursor(horizontalInset, y);
    gfx->print(leftAction);
  }

  if (rightAction != nullptr && rightAction[0] != '\0') {
    int textWidth = static_cast<int>(strlen(rightAction)) * 6 * textScale;
    int x = DISPLAY_WIDTH - horizontalInset - textWidth;
    gfx->setCursor(max(0, x), y);
    gfx->print(rightAction);
  }
}

ScreenState selectState(bool hidMode,
                        bool connected,
                        bool authenticated,
                        bool pairing,
                        bool armed,
                        bool typing,
                        bool identifying) {
  if (!hidMode) return ScreenState::Program;
  if (typing && armed && connected && authenticated) return ScreenState::Typing;
  if (armed && connected && authenticated) return ScreenState::Armed;
  if (identifying && connected && authenticated) return ScreenState::Identify;
  if (pairing) return ScreenState::Pairing;
  if (!connected) return ScreenState::Disconnected;
  if (!authenticated) return ScreenState::Securing;
  return ScreenState::Ready;
}

void render(ScreenState state, uint32_t pairingSeconds, const char *identifyLabel) {
  holdBarsState = ScreenState::Unknown;
  previousLeftHoldPixels = -1;
  previousRightHoldPixels = -1;

  switch (state) {
    case ScreenState::Program:
      drawFrame(COLOR_PROGRAM, rgb565(67, 171, 255));
      centeredText("PROGRAM", 12, 3, COLOR_WHITE);
      centeredText("USB CDC", 45, 2, COLOR_MUTED);
      centeredText("FIRMWARE", 65, 1, COLOR_MUTED);
      centeredText(Firmware::VERSION, 78, 2, COLOR_WHITE);
      drawButtonHints("FLASH", "HID");
      break;

    case ScreenState::Disconnected:
      drawFrame(COLOR_DISCONNECTED, rgb565(123, 141, 151));
      centeredText("SAFE", 10, 3, COLOR_WHITE);
      centeredText("OFFLINE", 44, 2, COLOR_MUTED);
      centeredText("DISARMED", 75, 2, COLOR_WHITE);
      drawButtonHints("PAIR", "CLEAR");
      break;

    case ScreenState::Pairing: {
      drawFrame(COLOR_PAIRING, rgb565(255, 184, 64));
      centeredText("PAIR", 8, 3, COLOR_WHITE);
      drawPairingCountdown(pairingSeconds);
      centeredText("ENTER PIN", 58, 1, COLOR_WHITE);
      centeredPasskey(72, 3, COLOR_WHITE);
      drawButtonHints("PAIR", "CLEAR");
      break;
    }

    case ScreenState::Securing:
      drawFrame(COLOR_SECURING, rgb565(255, 194, 61));
      if (BleTransport::reconnecting()) {
        centeredText("CONNECTING", 15, 2, COLOR_WHITE);
        centeredText("SAVED", 48, 2, COLOR_WHITE);
        centeredText("PAIRING", 72, 2, COLOR_MUTED);
      } else {
        centeredText("PAIRING", 10, 2, COLOR_WHITE);
        centeredText("ENTER PIN", 42, 1, COLOR_MUTED);
        centeredPasskey(58, 3, COLOR_WHITE);
        centeredText("ON COMPUTER", 91, 1, COLOR_WHITE);
      }
      drawButtonHints("PAIR", "CLEAR");
      break;

    case ScreenState::Ready:
      drawFrame(COLOR_READY, rgb565(50, 220, 194));
      centeredText("READY", 10, 3, COLOR_WHITE);
      centeredText("DISARMED", 49, 2, COLOR_MUTED);
      centeredText(BleTransport::deviceId(), 76, 3, COLOR_WHITE);
      drawButtonHints("PAIR", "ARM");
      break;

    case ScreenState::Armed:
      drawFrame(COLOR_ARMED, rgb565(255, 171, 176));
      centeredText("ARMED", 10, 3, COLOR_WHITE);
      centeredText("READY", 50, 3, COLOR_WHITE);
      drawButtonHints("STOP", "DISARM");
      break;

    case ScreenState::Typing:
      drawFrame(COLOR_ARMED, rgb565(255, 214, 92));
      centeredText("TYPING", 12, 3, COLOR_WHITE);
      centeredText("LIVE", 55, 3, COLOR_WHITE);
      drawButtonHints("STOP", "DISARM");
      break;

    case ScreenState::Identify:
      drawFrame(COLOR_PROGRAM, rgb565(67, 171, 255));
      if (identifyLabel[0] == '\0') {
        centeredText("DEVICE", 10, 3, COLOR_WHITE);
        centeredText(BleTransport::deviceId(), 51, 3, COLOR_WHITE);
        centeredText("SELECTED", 84, 1, COLOR_MUTED);
      } else {
        centeredText("IDENTIFY", 10, 2, COLOR_WHITE);
        size_t length = strlen(identifyLabel);
        if (length <= 10) {
          centeredText(identifyLabel, 49, 2, COLOR_WHITE);
        } else {
          size_t columns = length <= 20 ? 10 : 16;
          uint8_t size = length <= 20 ? 2 : 1;
          char first[17] = {};
          memcpy(first, identifyLabel, columns);
          centeredText(first, 40, size, COLOR_WHITE);
          centeredText(identifyLabel + columns, 62, size, COLOR_WHITE);
        }
        char identity[12];
        snprintf(identity, sizeof(identity), "ID %s", BleTransport::deviceId());
        centeredText(identity, 85, 1, COLOR_MUTED);
      }
      drawButtonHints("PAIR", "ARM");
      break;

    case ScreenState::Unknown:
      break;
  }
}

} // namespace

Action pollAction() { return Action::None; }
bool prepareRestart() { return true; } // SPI LCD has no continuous DMA stream.
void showStorageBusy() {} // Storage UI is only present on the Waveshare target.
void showUpdate() {
  if (!initialized) return;
  drawFrame(COLOR_PROGRAM, rgb565(67, 171, 255));
  centeredText("BLUETOOTH", 12, 2, COLOR_WHITE);
  centeredText("UPDATE", 39, 3, COLOR_WHITE);
  centeredText("SEE APP", 78, 2, COLOR_MUTED);
  centeredText("KEEP POWER ON", 107, 1, COLOR_WHITE);
}

void begin() {
  pinMode(BACKLIGHT_PIN, OUTPUT);
  digitalWrite(BACKLIGHT_PIN, HIGH);

  initialized = gfx->begin(40000000);
  if (!initialized) {
    return;
  }

  gfx->fillScreen(COLOR_BLACK);
  digitalWrite(BACKLIGHT_PIN, LOW);
}

void showBootloader() {
  if (!initialized) {
    return;
  }

  drawFrame(COLOR_BOOTLOADER, rgb565(190, 139, 255));
  centeredText("BOOTLOADER", 8, 2, COLOR_WHITE);
  centeredText("MODE", 32, 3, COLOR_WHITE);
  centeredText("PRESS", 64, 2, COLOR_MUTED);
  centeredText("RESET", 83, 2, COLOR_WHITE);
  centeredText("TO RESUME", 107, 1, COLOR_MUTED);
  holdBarsState = ScreenState::Unknown;
}

void showPairingCleared() {
  if (!initialized) {
    return;
  }

  drawFrame(COLOR_READY, rgb565(50, 220, 194));
  centeredText("BT", 10, 3, COLOR_WHITE);
  centeredText("PAIRINGS", 45, 2, COLOR_MUTED);
  centeredText("CLEARED", 70, 2, COLOR_WHITE);
  pairingClearedNoticeActive = true;
  pairingClearedNoticeStartedAt = millis();
  previousState = ScreenState::Unknown;
  holdBarsState = ScreenState::Unknown;
}

void updateHoldProgress(uint16_t leftPermille, uint16_t rightPermille) {
  if (!initialized || pairingClearedNoticeActive ||
      previousState == ScreenState::Unknown) {
    return;
  }

  bool stateChanged = holdBarsState != previousState;
  bool leftVisible = leftActionNeedsHold(previousState);
  bool rightVisible = rightActionNeedsHold(previousState);
  int leftPixels = leftVisible ? holdPixels(leftPermille) : 0;
  int rightPixels = rightVisible ? holdPixels(rightPermille) : 0;

  if (stateChanged || leftPixels != previousLeftHoldPixels) {
    drawHoldBar(LEFT_HOLD_BAR_X, leftPixels, leftVisible);
  }
  if (stateChanged || rightPixels != previousRightHoldPixels) {
    drawHoldBar(RIGHT_HOLD_BAR_X, rightPixels, rightVisible);
  }

  holdBarsState = previousState;
  previousLeftHoldPixels = leftPixels;
  previousRightHoldPixels = rightPixels;
}

void update(bool hidMode,
            bool connected,
            bool authenticated,
            bool pairing,
            bool armed,
            bool typing,
            bool identifying,
            uint32_t pairingSeconds) {
  if (!initialized) {
    return;
  }

  if (pairingClearedNoticeActive) {
    if (millis() - pairingClearedNoticeStartedAt <
        PAIRING_CLEARED_NOTICE_MS) {
      return;
    }
    pairingClearedNoticeActive = false;
    previousState = ScreenState::Unknown;
  }

  ScreenState state =
      selectState(hidMode, connected, authenticated, pairing, armed, typing,
                  identifying);
  bool countdownChanged =
      state == ScreenState::Pairing && pairingSeconds != previousPairingSeconds;
  char identifyLabel[BleTransport::MAX_IDENTIFY_LABEL_BYTES + 1] = {};
  uint32_t identifyRevision = state == ScreenState::Identify
      ? BleTransport::copyIdentifyLabel(identifyLabel, sizeof(identifyLabel)) : 0;
  bool identifyChanged = state == ScreenState::Identify &&
                         identifyRevision != previousIdentifyRevision;
  bool reconnecting = BleTransport::reconnecting();
  bool reconnectChanged = state == ScreenState::Securing &&
                          reconnecting != previousReconnecting;
  uint32_t passkey = BleTransport::passkey();
  bool pinVisible = state == ScreenState::Pairing ||
                    (state == ScreenState::Securing && !reconnecting);
  bool pinChanged = pinVisible && passkey != previousPasskey;
  if (state == previousState && !identifyChanged && !reconnectChanged && !pinChanged) {
    if (countdownChanged) drawPairingCountdown(pairingSeconds);
    previousPairingSeconds = pairingSeconds;
    return;
  }

  render(state, pairingSeconds, identifyLabel);
  previousState = state;
  previousPairingSeconds = pairingSeconds;
  previousPasskey = passkey;
  previousIdentifyRevision = identifyRevision;
  previousReconnecting = reconnecting;
}

} // namespace StatusDisplay
