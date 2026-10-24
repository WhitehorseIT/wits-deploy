#pragma once
#include <stdint.h>

namespace Storage {
// Hardware-independent policy, tested with a native C++ compiler.
enum class Result : uint8_t { Ok = 0, Busy = 5, Unsupported = 11, NoCard = 12, EjectFirst = 13 };
struct Policy {
  bool supported = false;
  bool present = false;
  bool exported = false;
  bool writable = false;
  bool ejected = false;
  bool error = false;
  // A write grant lasts for this USB export, independently of BLE connect,
  // disconnect, pairing and bond changes. Only confirmed host eject releases
  // ownership; changing protection mid-mount can reject dirty cached writes.
  bool needsEject = false;

  constexpr Result configure(bool allowWrites) {
    if (!supported) return Result::Unsupported;
    if (!present || error) return Result::NoCard;
    if (exported) return Result::EjectFirst;
    writable = allowWrites;
    needsEject = needsEject || allowWrites;
    ejected = false;
    exported = true;
    return Result::Ok;
  }
  constexpr void eject() {
    exported = false;
    ejected = true;
    writable = false;
    needsEject = false;
  }
  constexpr void fail() {
    writable = false;
    exported = false;
    error = true;
  }
  constexpr bool canRead() const { return present && exported && !error; }
  constexpr bool canWrite() const { return canRead() && writable; }
};
} // namespace Storage
