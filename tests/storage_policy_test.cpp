// Compile with a C++17 (or newer) compiler: all assertions execute at compile time.
#include "../src/storage_policy.h"
#include "../src/storage_transfer.h"
#include "../src/storage_scsi.h"
using Storage::Policy;
using Storage::Result;

constexpr bool policyTransitions() {
  Policy p;
  if (p.canRead() || p.canWrite() || p.configure(true) != Result::Unsupported) return false;
  p.supported = true;
  if (p.configure(true) != Result::NoCard) return false;
  p.present = true;
  p.exported = true; // Initial export is read-only.
  if (!p.canRead() || p.canWrite()) return false;
  // Read-only to read/write is allowed on a live export; the board then needs an eject
  // before any further change, and read-only requests are still refused.
  Policy live = p;
  if (live.configure(false) != Result::EjectFirst || live.writable || live.needsEject) return false;
  if (live.configure(true) != Result::Ok || !live.canWrite() || !live.needsEject || live.ejected) return false;
  if (!live.exported || live.configure(true) != Result::EjectFirst || live.configure(false) != Result::EjectFirst) return false;
  if (!live.canWrite() || !live.needsEject) return false;
  live.eject();
  if (live.canRead() || live.canWrite() || live.needsEject || !live.ejected) return false;
  if (live.configure(false) != Result::Ok || live.canWrite() || !live.canRead()) return false;
  p.eject();
  if (p.canRead() || p.canWrite() || !p.ejected) return false;
  if (p.configure(true) != Result::Ok || !p.canWrite() || p.ejected) return false;
  if (p.configure(false) != Result::EjectFirst || !p.writable) return false;
  // Once granted, writes remain available for the entire mounted export.
  // Neither another mode request nor a BLE control-session change releases
  // host ownership. Only confirmed USB eject permits a protection change.
  if (!p.canWrite() || !p.canRead() || p.ejected || !p.needsEject) return false;
  if (p.configure(false) != Result::EjectFirst || !p.canWrite() || !p.needsEject) return false;
  p.eject();
  if (p.needsEject) return false;
  if (p.configure(false) != Result::Ok || p.canWrite() || !p.canRead()) return false;
  p.fail();
  return !p.canRead() && !p.canWrite() && p.configure(true) == Result::NoCard;
}
static_assert(policyTransitions(), "Storage access transitions must preserve host ownership and write protection");

constexpr bool transferPlan() {
  auto full = Storage::planChunk(512 * 100, 4096);
  if (full.partial || full.sectors != 8 || full.bytes != 4096 || full.sector != 100) return false;
  auto large = Storage::planChunk(0, 100000);
  if (large.bytes != Storage::IO_BUFFER_BYTES) return false;
  auto head = Storage::planChunk(511, 1026);
  if (!head.partial || head.offset != 511 || head.bytes != 1) return false;
  auto middle = Storage::planChunk(512, 1025);
  if (middle.partial || middle.bytes != 1024 || middle.sectors != 2) return false;
  auto tail = Storage::planChunk(1536, 1);
  if (!tail.partial || tail.bytes != 1 || tail.offset != 0) return false;
  // Every chunk must fit its DMA buffer and exactly cover the requested range.
  for (uint32_t offset = 0; offset < 512; offset += 73) {
    uint32_t left = 20000, done = 0;
    while (left) {
      auto c = Storage::planChunk(2048 + offset + done, left);
      if (c.bytes == 0 || c.bytes > left || c.offset + c.bytes > Storage::IO_BUFFER_BYTES) return false;
      done += c.bytes;
      left -= c.bytes;
    }
    if (done != 20000) return false;
  }
  return Storage::validRange(1024, 512, 1536) && !Storage::validRange(1025, 512, 1536) &&
         !Storage::validRange(UINT64_MAX, 1, 1536) && Storage::validRange(1536, 0, 1536);
}
static_assert(transferPlan(), "Batched and partial USB transfers must preserve byte/sector bounds");

constexpr bool scsiFlushProtocol() {
  uint8_t command[16] = {};
  int flushes = 0, sense = 0;
  Storage::FlushResult outcome = Storage::FlushResult::Ok;
  auto flush = [&]() { ++flushes; return outcome; };
  auto setSense = [&](uint8_t key, uint8_t asc, uint8_t) { sense = (key << 8) | asc; };
  command[0] = 0xff;
  if (Storage::handleScsi(0, command, 4096, flush, setSense) != -1 || flushes || sense != 0x0520) return false;
  command[0] = 0x35;
  if (Storage::handleScsi(0, command, 0, flush, setSense) != 0 || flushes != 1) return false;
  command[0] = 0x91;
  command[1] = 2; // IMMED permitted; synchronous completion remains valid.
  if (Storage::handleScsi(0, command, 0, flush, setSense) != 0 || flushes != 2) return false;
  if (Storage::handleScsi(0, command, 1, flush, setSense) != -1 || flushes != 2 || sense != 0x0524) return false;
  constexpr Storage::FlushResult failures[] = {
      Storage::FlushResult::Busy, Storage::FlushResult::NoMedia, Storage::FlushResult::IoError};
  for (auto failure : failures) {
    outcome = failure;
    if (Storage::handleScsi(0, command, 0, flush, setSense) != -1) return false;
  }
  return Storage::handleScsi(1, command, 0, flush, setSense) == -1 && sense == 0x0525;
}
static_assert(scsiFlushProtocol(), "SCSI flush returns no-data success or a signed failure with correct sense");

// Read pipeline: sequence detection, overlap bookkeeping and invalidation.
constexpr bool prefetchBehavior() {
  constexpr uint64_t capacity = 1000;  // sectors
  Storage::Prefetch p;
  // A first read is never sequential, so nothing is requested for it.
  if (p.sequential(4096) || p.hit(8, 8)) return false;
  p.consumed(4096, 4096);
  // The next read starts exactly where the last ended: sequential, so request the following 8 sectors.
  if (!p.sequential(8192)) return false;
  if (!p.request(16, capacity) || !p.shouldRun()) return false;
  p.completed();
  if (p.requested || !p.hit(16, 8) || !p.hit(16, 1) || p.hit(17, 8) || p.hit(16, 9) || p.hit(8, 8)) return false;
  // Using it up clears the buffer and moves the sequence forward.
  p.consumed(8192, 4096);
  if (p.hit(16, 8) || !p.sequential(12288)) return false;
  // Never request past the end of the card.
  if (!p.request(992, capacity) || p.request(993, capacity) || p.request(1000, capacity)) return false;
  // A write, eject, mode change, error or restart (all call drop()) invalidates everything:
  // a request made before the drop must not run, and data read before it must not be served.
  Storage::Prefetch q;
  q.consumed(0, 4096);
  q.request(8, capacity);
  q.completed();
  if (!q.hit(8, 8)) return false;
  q.drop();
  if (q.hit(8, 8) || q.sequential(4096) || q.shouldRun()) return false;
  Storage::Prefetch r;
  r.request(8, capacity);
  r.drop();                                   // dropped while the background read was queued
  if (r.shouldRun()) return false;
  r.request(24, capacity);                    // a fresh request after the drop is current again
  if (!r.shouldRun()) return false;
  r.completed();
  r.drop();                                   // dropped after the read finished, before it was served
  return !r.hit(24, 8);
}
static_assert(prefetchBehavior(), "Prefetch must overlap sequential reads and never serve data from before a write, eject or mode change");
