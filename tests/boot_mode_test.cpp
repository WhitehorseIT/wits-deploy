#include "../src/boot_mode.h"
#include <initializer_list>
using BootMode::Reset;
using BootMode::programMode;

constexpr uint32_t PROGRAM = 0x57495450;

constexpr bool bootDecisions() {
  // Default: every normal start is HID, whatever the leftover marker memory holds.
  for (uint32_t marker : {uint32_t(0), PROGRAM, uint32_t(0xdeadbeef)}) {
    if (programMode(Reset::PowerOn, marker, PROGRAM)) return false;   // power loss: stale memory is ignored
    if (programMode(Reset::External, marker, PROGRAM)) return false;  // RESET button
    if (programMode(Reset::Other, marker, PROGRAM)) return false;     // brownout and the rest
  }
  // A software restart is HID unless the exact program marker is present. This is what OTA does.
  if (programMode(Reset::Software, 0, PROGRAM) || programMode(Reset::Software, 0xdeadbeef, PROGRAM)) return false;
  // Asked for from the HID screen: software restart plus the marker.
  if (!programMode(Reset::Software, PROGRAM, PROGRAM)) return false;
  // A crash or hang always comes up in programming mode, with or without a marker.
  return programMode(Reset::Fault, 0, PROGRAM) && programMode(Reset::Fault, PROGRAM, PROGRAM);
}
static_assert(bootDecisions(), "Boot defaults to HID; programming mode only on request or after a fault");

int main() { return 0; }
