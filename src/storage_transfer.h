#pragma once
#include <stdint.h>

namespace Storage {
constexpr uint32_t SECTOR_BYTES = 512;
constexpr uint32_t IO_BUFFER_BYTES = 4096;
struct Chunk {
  uint32_t sector;
  uint32_t offset;
  uint32_t bytes;
  uint32_t sectors;
  bool partial;
};
constexpr bool validRange(uint64_t start, uint32_t length, uint64_t capacity) {
  return start <= capacity && length <= capacity - start;
}
constexpr Chunk planChunk(uint64_t position, uint32_t remaining) {
  uint32_t offset = position % SECTOR_BYTES;
  if (offset || remaining < SECTOR_BYTES) {
    uint32_t count = SECTOR_BYTES - offset;
    if (count > remaining) count = remaining;
    return {static_cast<uint32_t>(position / SECTOR_BYTES), offset, count, 1, true};
  }
  uint32_t sectors = remaining / SECTOR_BYTES;
  if (sectors > IO_BUFFER_BYTES / SECTOR_BYTES) sectors = IO_BUFFER_BYTES / SECTOR_BYTES;
  return {static_cast<uint32_t>(position / SECTOR_BYTES), 0, sectors * SECTOR_BYTES, sectors, false};
}
// Read pipeline. While the USB layer sends one 4 KiB piece to the host, a background task
// reads the next piece from the card, so the card read and the USB transfer overlap.
// All fields are touched only while holding the storage I/O mutex. A "generation"
// counter is bumped by every drop(), so data read before a write, eject, mode change,
// error or restart can never be served afterwards.
constexpr uint32_t PREFETCH_SECTORS = IO_BUFFER_BYTES / SECTOR_BYTES;  // 8 sectors, 4 KiB
struct Prefetch {
  uint32_t generation = 0;
  uint64_t lastEnd = UINT64_MAX;       // byte position after the previous read; never a valid position
  // Data waiting in the prefetch buffer.
  bool ready = false;
  uint32_t readySector = 0, readySectors = 0, readyGeneration = 0;
  // Work requested of the background task.
  bool requested = false;
  uint32_t requestSector = 0, requestSectors = 0, requestGeneration = 0;

  constexpr void drop() { ++generation; lastEnd = UINT64_MAX; ready = false; requested = false; }
  constexpr bool sequential(uint64_t position) const { return lastEnd == position; }
  // True if the prefetch buffer holds exactly what this chunk needs and is still current.
  constexpr bool hit(uint32_t sector, uint32_t sectors) const {
    return ready && readyGeneration == generation && sector == readySector && sectors <= readySectors;
  }
  // Ask for the PREFETCH_SECTORS after a read, if they exist on the card.
  constexpr bool request(uint32_t nextSector, uint64_t capacitySectors) {
    if (uint64_t(nextSector) + PREFETCH_SECTORS > capacitySectors) return false;
    requested = true;
    requestSector = nextSector;
    requestSectors = PREFETCH_SECTORS;
    requestGeneration = generation;
    return true;
  }
  constexpr bool shouldRun() const { return requested && requestGeneration == generation; }
  constexpr void completed() {
    ready = true;
    readySector = requestSector;
    readySectors = requestSectors;
    readyGeneration = requestGeneration;
    requested = false;
  }
  // A read finished at byte position `position + bytes`; whatever was prefetched is used up.
  constexpr void consumed(uint64_t position, uint32_t bytes) { ready = false; lastEnd = position + bytes; }
};
} // namespace Storage
