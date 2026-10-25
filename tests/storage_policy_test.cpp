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

// Sequential read-ahead: how many SD commands a pattern of 4 KiB USB callbacks needs.
constexpr uint32_t sdCommandsForReads(const uint64_t *positions, int count, uint64_t capacitySectors,
                                      Storage::ReadAhead &window) {
  uint32_t commands = 0;
  for (int i = 0; i < count; ++i) {
    uint64_t position = positions[i];
    auto chunk = Storage::planChunk(position, 4096);
    bool covered = window.covers(chunk.sector, chunk.sectors);
    if (!covered && window.sequential(position)) {
      uint32_t n = window.window(chunk.sector, chunk.sectors, capacitySectors);
      if (n) { ++commands; window.filled(chunk.sector, n); covered = true; }
    }
    if (!covered) ++commands;  // plain single request
    window.served(position, chunk.bytes);
  }
  return commands;
}

constexpr bool readAheadBehavior() {
  constexpr uint64_t capacity = 1000000;
  Storage::ReadAhead w;
  uint64_t seq[16] = {};
  for (int i = 0; i < 16; ++i) seq[i] = 8192 + uint64_t(i) * 4096;
  // 16 sequential 4 KiB callbacks: the first is a plain read, then one 32 KiB window per
  // 8 callbacks (2 windows). That is 3 SD commands instead of 16.
  if (sdCommandsForReads(seq, 16, capacity, w) != 3) return false;
  // Random 4 KiB reads never trigger read-ahead: one SD command each.
  Storage::ReadAhead r;
  uint64_t jumps[6] = {0, 409600, 4096, 819200, 40960, 2048000};
  if (sdCommandsForReads(jumps, 6, capacity, r) != 6) return false;
  // A window never fetches past the end of the card, and tiny remainders fall back to plain reads.
  if (w.window(capacity - 10, 8, capacity) != 10 || w.window(capacity - 4, 8, capacity) != 0) return false;
  if (w.window(capacity, 1, capacity) != 0 || w.window(0, 8, capacity) != Storage::READ_AHEAD_SECTORS) return false;
  // covers() is exact: inside the window yes, one sector past the end no, before the start no.
  Storage::ReadAhead c;
  c.filled(100, 64);
  if (!c.covers(100, 8) || !c.covers(156, 8) || c.covers(157, 8) || c.covers(99, 8) || c.covers(163, 2)) return false;
  // drop() forgets the data and the sequence, so the next read is a plain read again.
  c.served(51200, 4096);
  if (!c.sequential(55296)) return false;
  c.drop();
  return !c.covers(100, 8) && !c.sequential(55296) && !c.sequential(0);
}
static_assert(readAheadBehavior(), "Read-ahead must serve sequential reads from RAM and never return stale or out-of-range data");
