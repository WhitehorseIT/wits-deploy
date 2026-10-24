#pragma once
#include <stdint.h>

namespace Storage {
enum class FlushResult { Ok, Busy, NoMedia, IoError };

// Generic (non-built-in) SCSI requests. Keep the result signed: unsupported
// requests must be -1, never a wrapped uint16 byte count. TinyUSB handles
// READ/WRITE, START STOP, MODE SENSE and PREVENT/ALLOW through other callbacks.
template<class Flush, class Sense>
constexpr int32_t handleScsi(uint8_t lun, const uint8_t command[16], uint16_t dataBytes,
                              Flush flush, Sense sense) {
  if (lun != 0) { sense(0x05, 0x25, 0); return -1; }
  if (command[0] != 0x35 && command[0] != 0x91) {
    sense(0x05, 0x20, 0); // Illegal request / unsupported opcode.
    return -1;
  }
  if (dataBytes != 0 || (command[1] & ~uint8_t(0x02))) {
    sense(0x05, 0x24, 0); // Invalid CDB; IMMED may still complete synchronously.
    return -1;
  }
  switch (flush()) {
    case FlushResult::Ok: return 0; // Correct no-data success for SYNCHRONIZE CACHE.
    case FlushResult::Busy: sense(0x02, 0x04, 0x01); return -1;
    case FlushResult::NoMedia: sense(0x02, 0x3a, 0); return -1;
    case FlushResult::IoError: sense(0x03, 0x0c, 0); return -1;
  }
  return -1;
}
} // namespace Storage
