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
// Sequential-read window. When a read starts exactly where the previous one ended, the
// firmware reads READ_AHEAD_SECTORS from the card in one command and serves the next
// USB callbacks from RAM. The window is dropped on every write, eject, mode change,
// error and restart, so it can never return stale data. Used only while holding the
// storage I/O mutex.
constexpr uint32_t READ_AHEAD_SECTORS = 64;  // 32 KiB
struct ReadAhead {
  uint32_t start = 0;
  uint32_t count = 0;                 // 0 means the window holds nothing
  uint64_t lastEnd = UINT64_MAX;      // byte position after the previous read; never a valid position
  constexpr void drop() { count = 0; lastEnd = UINT64_MAX; }
  constexpr bool covers(uint32_t sector, uint32_t sectors) const {
    return count != 0 && sector >= start && uint64_t(sector) + sectors <= uint64_t(start) + count;
  }
  constexpr bool sequential(uint64_t position) const { return lastEnd == position; }
  // Sectors to fetch for a window beginning at `sector`, or 0 if even one request would not fit.
  constexpr uint32_t window(uint32_t sector, uint32_t needed, uint64_t capacitySectors) const {
    if (sector >= capacitySectors) return 0;
    uint64_t left = capacitySectors - sector;
    uint32_t n = left < READ_AHEAD_SECTORS ? static_cast<uint32_t>(left) : READ_AHEAD_SECTORS;
    return n >= needed ? n : 0;
  }
  constexpr void filled(uint32_t sector, uint32_t sectors) { start = sector; count = sectors; }
  constexpr void served(uint64_t position, uint32_t bytes) { lastEnd = position + bytes; }
};
} // namespace Storage
