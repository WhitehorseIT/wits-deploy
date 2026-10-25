#include "../src/text_fit.h"
using namespace TextFit;

// 128-pixel display with a 4-pixel margin:
// size 1 -> 20 columns, size 2 -> 10, size 3 -> 6.
static_assert(charsPerLine(1, 128) == 20 && charsPerLine(2, 128) == 10 && charsPerLine(3, 128) == 6);
static_assert(charsPerLine(0, 128) == 0);

// The firmware version "0.2.0-dev13" (11 characters) overflowed at size 2 and must shrink to 1.
static_assert(fitSize(11, 2, 128) == 1);
static_assert(fitSize(10, 2, 128) == 2);       // exactly fits, keep the requested size
static_assert(fitSize(7, 3, 128) == 2);        // shrinks one step only when needed
static_assert(fitSize(6, 3, 128) == 3);
static_assert(fitSize(40, 2, 128) == 1);       // never below 1; the caller wraps
static_assert(fitSize(5, 0, 128) == 1);

// Labels that fit are not split.
static_assert(splitLabel("ABC", 3, 20).firstLength == 3 && splitLabel("ABC", 3, 20).secondStart == 3);

constexpr bool splits() {
  // "WITS Keyboard-8428" is 18 characters and fits on one line at size 1.
  // A longer name breaks at the last separator that fits, not mid-word.
  constexpr const char *a = "WITS Keyboard front desk bench";   // 30 characters
  auto sa = splitLabel(a, 30, 20);
  if (sa.firstLength != 19 || a[sa.firstLength] != ' ' || a[sa.secondStart] != 'd') return false;
  constexpr const char *b = "WITS-Keyboard-Deployment-Bench";   // 30 characters, only hyphens
  auto sb = splitLabel(b, 30, 20);
  // The last hyphen that fits in 20 columns is after "WITS-Keyboard-" (14 characters).
  if (sb.firstLength != 14 || b[sb.firstLength - 1] != '-' || sb.secondStart != 14) return false;
  constexpr const char *c = "ABCDEFGHIJKLMNOPQRSTUVWXYZ012345"; // 32 characters, no separator
  auto sc = splitLabel(c, 32, 20);
  return sc.firstLength == 20 && sc.secondStart == 20;
}
static_assert(splits(), "labels break at separators and never exceed the line width");

int main() { return 0; }
