#pragma once
#include <stddef.h>
#include <stdint.h>

#if defined(WITS_BOARD_WAVESHARE7) && defined(WITS_BOARD_WAVESHARE147)
#error Select exactly one Waveshare board target
#endif

#if defined(WITS_BOARD_WAVESHARE7) || defined(WITS_BOARD_WAVESHARE147)
#define WITS_HAS_TOUCHSCREEN 1
#define WITS_HAS_STORAGE 1
#else
#define WITS_HAS_TOUCHSCREEN 0
#define WITS_HAS_STORAGE 0
#endif

namespace BoardProfile {
#if defined(WITS_BOARD_WAVESHARE147)
constexpr char ID[] = "waveshare147";
constexpr uint8_t OTA_CODE = 3;
constexpr size_t MIN_PSRAM = 4 * 1024 * 1024;
constexpr int SD_MOSI = 15, SD_MISO = 17, SD_SCK = 16, SD_CS = 14;
constexpr int LCD_DC = 45, LCD_CS = 21, LCD_SCK = 38, LCD_MOSI = 39;
constexpr int LCD_RST = 40, LCD_BL = 46;
constexpr int TOUCH_SDA = 42, TOUCH_SCL = 41, TOUCH_RST = 47, TOUCH_INT = 48;
#elif defined(WITS_BOARD_WAVESHARE7)
constexpr char ID[] = "waveshare7";
constexpr uint8_t OTA_CODE = 1;
constexpr size_t MIN_PSRAM = 4 * 1024 * 1024;
constexpr int SD_MOSI = 11, SD_MISO = 13, SD_SCK = 12, SD_CS = -1;
#else
constexpr char ID[] = "tqtpro";
constexpr uint8_t OTA_CODE = 2;
constexpr size_t MIN_PSRAM = 1024 * 1024;
#endif
} // namespace BoardProfile
