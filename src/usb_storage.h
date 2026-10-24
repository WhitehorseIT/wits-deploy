#pragma once
#include <Arduino.h>
#include "storage_policy.h"

namespace Storage {
struct Snapshot {
  Policy policy;
  uint64_t bytes = 0;
};
void begin(); // Construct MSC before USB.begin(); card is never mounted locally.
void loop();
void revokeWrites();
bool prepareRestart();
Result configure(bool allowWrites);
Snapshot snapshot();
} // namespace Storage
