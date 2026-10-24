#include "../src/touch_controls147.h"
#include "../src/board_profile.h"
#include <initializer_list>
using namespace Touch147;

constexpr bool hitBounds() {
  for (bool hid : {false, true}) {
    for (int i=0; i<(hid?5:2); ++i) {
      auto r=button(i,hid);
      if (r.x<CONTENT_WIDTH || r.y<24 || r.x+r.width>WIDTH || r.y+r.height>HEIGHT) return false;
      if (hit(r.x,r.y,hid)!=i || hit(r.x+r.width-1,r.y+r.height-1,hid)!=i) return false;
      if (hit(r.x+r.width,r.y,hid)!=-1 || hit(r.x,r.y+r.height,hid)!=-1) return false;
      // A real touch at each drawn button's center must select that button
      // after the panel's landscape coordinate transform.
      auto point=decode(1,r.y+r.height/2,r.x+r.width/2,1);
      if (point.canceled || hit(point.x,point.y,hid)!=i) return false;
    }
  }
  return hit(120,90,true)==-1 && hit(0,0,true)==-1 && hit(WIDTH,HEIGHT,false)==-1;
}
static_assert(hitBounds(), "buttons stay on-screen and gaps never select an action");
static_assert(progress(1000,2000,66)==33 && progress(8000,5000,66)==66);
static_assert(progress(1,0,66)==0 && progress(1,2,0)==0);
static_assert(decode(1,0,0,1).x==0 && decode(1,0,0,1).y==0);
static_assert(decode(1,171,319,1).x==319 && decode(1,171,319,1).y==171);
static_assert(decode(1,171,0,1).x==0 && decode(1,171,0,1).y==171);
static_assert(decode(1,0,319,1).x==319 && decode(1,0,319,1).y==0);
static_assert(decode(1,0,0,3).x==319 && decode(1,0,0,3).y==171);
static_assert(decode(1,171,319,3).x==0 && decode(1,171,319,3).y==0);
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
