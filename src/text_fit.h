#pragma once
#include <stddef.h>
#include <stdint.h>

namespace TextFit {
// Hardware-independent helpers for the 6x8 pixel built-in font, tested with a
// native C++ compiler. A character is 6 * size pixels wide.
constexpr int GLYPH_WIDTH = 6;

constexpr size_t charsPerLine(uint8_t size, int displayWidth, int margin = 4) {
  return size == 0 ? 0 : static_cast<size_t>((displayWidth - margin) / (GLYPH_WIDTH * size));
}

// Largest size not above `requested` at which `length` characters fit the display
// width. Never returns less than 1: text that still cannot fit is for the caller to wrap.
constexpr uint8_t fitSize(size_t length, uint8_t requested, int displayWidth, int margin = 4) {
  uint8_t size = requested == 0 ? 1 : requested;
  while (size > 1 && length > charsPerLine(size, displayWidth, margin)) --size;
  return size;
}

// Where to split a label that must wrap onto two lines of at most `columns`
// characters. Prefers the last space or hyphen so words are not cut.
struct Split {
  size_t firstLength;  // characters on the first line
  size_t secondStart;  // index where the second line begins
};

constexpr Split splitLabel(const char *text, size_t length, size_t columns) {
  if (length <= columns) return {length, length};
  size_t best = 0;
  for (size_t i = 1; i <= columns && i < length; ++i) {
    if (text[i - 1] == '-') best = i;           // keep the hyphen on the first line
    else if (text[i] == ' ') best = i;          // drop the space between the lines
  }
  if (best == 0) return {columns, columns};      // no break point: hard split
  size_t start = best;
  while (start < length && text[start] == ' ') ++start;
  return {best, start};
}
} // namespace TextFit
