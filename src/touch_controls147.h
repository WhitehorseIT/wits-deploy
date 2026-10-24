#pragma once
#include <stdint.h>

namespace Touch147 {
constexpr uint8_t ROTATION = 1; // Landscape, USB-C at the right; verify on the first case fit.
constexpr int WIDTH = 320, HEIGHT = 172, CONTENT_WIDTH = 148;
// AXS5106L supplies native portrait coordinates. Apply the same rotation as
// the LCD before hit testing. Invalid contacts cancel rather than release ARM.
struct Contact { bool pressed, canceled; uint16_t x, y; };
constexpr Contact decode(uint8_t count, uint16_t rawX, uint16_t rawY, uint8_t rotation = ROTATION) {
  return count == 0 ? Contact{false, false, 0, 0} :
         count != 1 || rawX >= 172 || rawY >= 320 ? Contact{false, true, 0xffff, 0xffff} :
         rotation == 1 ? Contact{true, false, rawY, rawX} :
         rotation == 3 ? Contact{true, false, uint16_t(319 - rawY), uint16_t(171 - rawX)} :
         rotation == 2 ? Contact{true, false, rawX, uint16_t(319 - rawY)} :
         Contact{true, false, uint16_t(171 - rawX), rawY};
}
struct Rect { int16_t x, y, width, height; };
constexpr Rect button(int index, bool hid) {
  if (index < 0 || index >= (hid ? 5 : 2)) return {0, 0, 0, 0};
  if (!hid) return {156, int16_t(40 + index * 64), 158, 52};
  return {int16_t(156 + (index % 2) * 82), int16_t(32 + (index / 2) * 46),
          int16_t(index == 4 ? 158 : 76), 40};
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
