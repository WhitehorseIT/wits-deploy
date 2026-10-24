#pragma once
#include <stdint.h>

namespace Touch147 {
// AXS5106L reports portrait coordinates with X reversed. An invalid contact
// cancels the gesture; it must never be interpreted as a normal ARM release.
struct Contact { bool pressed, canceled; uint16_t x, y; };
constexpr Contact decode(uint8_t count, uint16_t rawX, uint16_t rawY) {
  return count == 0 ? Contact{false, false, 0, 0} :
         count != 1 || rawX >= 172 || rawY >= 320 ? Contact{false, true, 0xffff, 0xffff} :
         Contact{true, false, uint16_t(171 - rawX), rawY};
}
struct Rect { int16_t x, y, width, height; };
constexpr Rect button(int index, bool hid) {
  if (index < 0 || index >= (hid ? 5 : 2)) return {0, 0, 0, 0};
  return {int16_t(8 + (index % 2) * 82), int16_t(hid ? 196 + (index / 2) * 40 : 252),
          74, int16_t(hid ? 36 : 52)};
}
constexpr int hit(uint16_t x, uint16_t y, bool hid) {
  for (int index = 0; index < (hid ? 5 : 2); ++index) {
    Rect r = button(index, hid);
    if (x >= r.x && x < r.x + r.width && y >= r.y && y < r.y + r.height) return index;
  }
  return -1;
}
constexpr int progress(uint32_t elapsed, uint32_t duration, int width) {
  return duration == 0 || width <= 0 ? 0 : int((elapsed < duration ? elapsed : duration) * width / duration);
}
} // namespace Touch147
