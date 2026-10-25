#pragma once
#include <Arduino.h>
#include "storage_policy.h"

namespace Storage {
// Cumulative since boot; the desktop app reads two snapshots and takes the
// difference. Times are microseconds. "Callback" time is the whole USB request
// (mutex held); "SD" time is only the part spent inside the SD driver calls.
struct IoStats {
  uint64_t readBytes = 0, writeBytes = 0;
  uint64_t readCallbackUs = 0, writeCallbackUs = 0;
  uint64_t readSdUs = 0, writeSdUs = 0;
  uint32_t readCalls = 0, writeCalls = 0;
  uint32_t largestRequestBytes = 0;
  uint32_t slowestRequestMs = 0;
  uint32_t errors = 0;
};
struct Snapshot {
  Policy policy;
  uint64_t bytes = 0;
  IoStats io;
};
void begin(); // Construct MSC before USB.begin(); card is never mounted locally.
void loop();
bool prepareRestart();
Result configure(bool allowWrites);
Snapshot snapshot();
} // namespace Storage
