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
  if (p.configure(true) != Result::EjectFirst || p.writable) return false;
  p.eject();
  if (p.canRead() || p.canWrite() || !p.ejected) return false;
  if (p.configure(true) != Result::Ok || !p.canWrite() || p.ejected) return false;
  if (p.configure(false) != Result::EjectFirst || !p.writable) return false;
  p.revoke(); // BLE disconnect revokes writes without falsely claiming safe eject.
  if (p.canWrite() || !p.canRead() || p.ejected || !p.needsEject) return false;
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
