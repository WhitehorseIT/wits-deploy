#include "../src/touch_controls147.h"
#include "../src/board_profile.h"
#include <initializer_list>
using namespace Touch147;

constexpr bool hitBounds() {
  for (bool hid : {false, true}) {
    for (int i=0; i<(hid?5:2); ++i) {
      auto r=button(i,hid);
      if (r.x<0 || r.y<0 || r.x+r.width>172 || r.y+r.height>320) return false;
      if (hit(r.x,r.y,hid)!=i || hit(r.x+r.width-1,r.y+r.height-1,hid)!=i) return false;
      if (hit(r.x+r.width,r.y,hid)!=-1 || hit(r.x,r.y+r.height,hid)!=-1) return false;
    }
  }
  return hit(120,290,true)==-1 && hit(0,0,true)==-1 && hit(171,319,false)==-1;
}
static_assert(hitBounds(), "buttons stay on-screen and gaps never select an action");
static_assert(progress(1000,2000,66)==33 && progress(8000,5000,66)==66);
static_assert(progress(1,0,66)==0 && progress(1,2,0)==0);
static_assert(decode(1,0,0).x==171 && decode(1,171,319).x==0 && decode(1,171,319).y==319);
static_assert(decode(1,172,0).canceled && decode(1,0,320).canceled && decode(2,30,40).canceled);
static_assert(!decode(0,4095,4095).pressed && !decode(0,4095,4095).canceled);
#ifdef WITS_BOARD_WAVESHARE147
static_assert(BoardProfile::OTA_CODE==3 && BoardProfile::LCD_RST==40 && BoardProfile::TOUCH_RST==47);
static_assert(BoardProfile::SD_CS==14 && BoardProfile::SD_SCK==16 && BoardProfile::LCD_SCK==38);
static_assert(WITS_HAS_STORAGE && WITS_HAS_TOUCHSCREEN);
#elif defined(WITS_BOARD_WAVESHARE7)
static_assert(BoardProfile::OTA_CODE==1 && BoardProfile::SD_CS==-1 && BoardProfile::SD_SCK==12);
#else
static_assert(BoardProfile::OTA_CODE==2 && !WITS_HAS_STORAGE && !WITS_HAS_TOUCHSCREEN);
#endif
