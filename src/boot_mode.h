#pragma once
#include <stdint.h>

namespace BootMode {
// Which USB personality to start. Hardware independent and tested with a native compiler.
//
// The board starts as a keyboard (HID) by default. Programming mode is entered only when
// it is asked for from the HID screen (the request survives one software restart in
// uninitialized RTC memory), or after a crash or hang: a faulted reset must never put the
// board in a boot loop as a keyboard, so it comes up in the keyboard-free programming mode
// where it can be reflashed. The request is honored only after a software reset, so stale
// RTC memory after a power loss can never trigger it.
enum class Reset : uint8_t { PowerOn, External, Software, Fault, Other };

constexpr bool programMode(Reset reason, uint32_t requestMarker, uint32_t programMarker) {
  if (reason == Reset::Fault) return true;
  return reason == Reset::Software && requestMarker == programMarker;
}
} // namespace BootMode
