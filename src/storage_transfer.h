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
} // namespace Storage
