#pragma once
// Test-only fault injection for checking the crash fallback on real boards. It exists only in the
// "-faulttest" PlatformIO environments (WITS_FAULT_TEST); release builds do not contain it.
//
// Twenty seconds after the board reaches HID mode it crashes on purpose, using a different kind of
// fault on each run (cycling through the list below). Every crash must come back in PROGRAM mode and
// stay there: the board then needs a USB update (or "hold HID" to run the next case).
#include <stdint.h>

namespace FaultTest {
enum class Kind : uint8_t { NullStore, InterruptHang, Abort };

constexpr uint32_t DELAY_MS = 20000;
constexpr uint32_t KINDS = 3;

constexpr Kind kindForRun(uint32_t run) { return static_cast<Kind>(run % KINDS); }
} // namespace FaultTest

#ifdef WITS_FAULT_TEST
#include <Arduino.h>
#include <esp_rom_sys.h>
#include <freertos/FreeRTOS.h>
#include <stdlib.h>

namespace FaultTest {
constexpr uint32_t MAGIC = 0x46544553; // "FTES"
RTC_NOINIT_ATTR static uint32_t storedMagic;
RTC_NOINIT_ATTR static uint32_t completedRuns;

// Call from loop(); does nothing outside HID mode or before the delay has passed.
inline void poll(bool hidMode) {
  static uint32_t hidSince = 0;
  if (!hidMode) return;
  if (hidSince == 0) hidSince = millis();
  if (millis() - hidSince < DELAY_MS) return;
  if (storedMagic != MAGIC) {  // first boot after power was applied
    storedMagic = MAGIC;
    completedRuns = 0;
  }
  const Kind kind = kindForRun(completedRuns);
  esp_rom_printf("[WITS] FAULT TEST run %u: crashing now (kind %u)\n", static_cast<unsigned>(completedRuns),
                 static_cast<unsigned>(kind));
  completedRuns = completedRuns + 1;
  switch (kind) {
    case Kind::NullStore:
      *reinterpret_cast<volatile int *>(0) = 1;  // store to an unmapped address: panic
      break;
    case Kind::InterruptHang:
      portDISABLE_INTERRUPTS();  // nothing can run, so the interrupt watchdog fires
      for (;;) {}
    case Kind::Abort:
      abort();
  }
}
} // namespace FaultTest
#endif
