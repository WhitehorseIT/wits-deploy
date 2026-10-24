#pragma once

#include <Arduino.h>

#ifdef WITS_BOARD_WAVESHARE7
#include <esp_rom_sys.h>
#include <esp_rom_uart.h>
#include <esp_heap_caps.h>
#endif

namespace StartupTrace {
inline void mark(const char *stage) {
#ifdef WITS_BOARD_WAVESHARE7
  // ROM UART0 output reaches the dedicated UART connector even when native
  // USB is absent or changes personality. No PINs or command payloads.
  esp_rom_printf("[WITS %lu ms] %s; internal_heap=%u\n",
                 static_cast<unsigned long>(millis()), stage,
                 static_cast<unsigned>(heap_caps_get_free_size(MALLOC_CAP_INTERNAL | MALLOC_CAP_8BIT)));
  esp_rom_output_tx_wait_idle(0);
#endif
}
} // namespace StartupTrace
