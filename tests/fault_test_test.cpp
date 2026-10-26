// Compile-time checks for the crash-test cycle (no hardware needed).
#include "../src/fault_test.h"

static_assert(FaultTest::kindForRun(0) == FaultTest::Kind::NullStore, "first run: bad store");
static_assert(FaultTest::kindForRun(1) == FaultTest::Kind::InterruptHang, "second run: interrupt watchdog");
static_assert(FaultTest::kindForRun(2) == FaultTest::Kind::Abort, "third run: abort");
static_assert(FaultTest::kindForRun(3) == FaultTest::Kind::NullStore, "the cycle repeats");
static_assert(FaultTest::DELAY_MS >= 10000, "leave time to connect and see the board in HID before it crashes");

int main() { return 0; }
