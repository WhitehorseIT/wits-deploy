#ifdef WITS_BOARD_WAVESHARE147
#include "status_display.h"
#include "board_hardware.h"
#include "board_profile.h"
#include "ble_transport.h"
#include "firmware_version.h"
#include "usb_storage.h"
#include "touch_controls147.h"
#include <Arduino_GFX_Library.h>

namespace StatusDisplay {
namespace {
// JD9853 register settings from the Waveshare example mirrored at:
// VolosR/Wave147moreExamples, 5c05f2e, TurboBlink/TurboBlink.ino.
// Use the schematic's LCD_RST=40, distinct from TOUCH_RST=47.
struct Register { uint8_t address, count, data[32]; uint16_t delayMs; };
constexpr Register panelRegisters[] = {
  {0x11, 0, {}, 120}, {0xdf, 2, {0x98,0x53}, 0}, {0xb2, 1, {0x23}, 0},
  {0xb7, 4, {0,0x47,0,0x6f}, 0}, {0xbb, 6, {0x1c,0x1a,0x55,0x73,0x63,0xf0}, 0},
  {0xc0, 2, {0x44,0xa4}, 0}, {0xc1, 1, {0x16}, 0},
  {0xc3, 8, {0x7d,7,0x14,6,0xcf,0x71,0x72,0x77}, 0},
  {0xc4,12, {0,0,0xa0,0x79,0x0b,0x0a,0x16,0x79,0x0b,0x0a,0x16,0x82}, 0},
  {0xc8,32, {0x3f,0x32,0x29,0x29,0x27,0x2b,0x27,0x28,0x28,0x26,0x25,0x17,0x12,0x0d,4,0,
             0x3f,0x32,0x29,0x29,0x27,0x2b,0x27,0x28,0x28,0x26,0x25,0x17,0x12,0x0d,4,0}, 0},
  {0xd0,5,{4,6,0x6b,0x0f,0},0}, {0xd7,2,{0,0x30},0}, {0xe6,1,{0x14},0},
  {0xde,1,{1},0}, {0xb7,5,{3,0x13,0xef,0x35,0x35},0}, {0xc1,3,{0x14,0x15,0xc0},0},
  {0xc2,2,{6,0x3a},0}, {0xc4,2,{0x72,0x12},0}, {0xbe,1,{0},0}, {0xde,1,{2},0},
  {0xe5,3,{0,2,0},0}, {0xe5,3,{1,2,0},0}, {0xde,1,{0},0}, {0x35,1,{0},0},
  {0x3a,1,{5},0}, {0x2a,4,{0,0x22,0,0xcd},0}, {0x2b,4,{0,0,1,0x3f},0},
  {0xde,1,{2},0}, {0xe5,3,{0,2,0},0}, {0xde,1,{0},0}, {0x36,1,{0},0},
  {0x21,0,{},10}, {0x29,0,{},20}
};
class JD9853 : public Arduino_ST7789 {
public:
  explicit JD9853(Arduino_DataBus *bus) : Arduino_ST7789(bus, BoardProfile::LCD_RST, Touch147::ROTATION,
      true, 172, 320, 34, 0, 34, 0) {}
protected:
  void tftInit() override {
    pinMode(_rst, OUTPUT);
    digitalWrite(_rst, LOW); delay(20);
    digitalWrite(_rst, HIGH); delay(120);
    for (const auto &reg : panelRegisters) {
      _bus->beginWrite();
      _bus->writeCommand(reg.address);
      for (uint8_t index = 0; index < reg.count; ++index) _bus->write(reg.data[index]);
      _bus->endWrite();
      if (reg.delayMs) delay(reg.delayMs);
    }
  }
};
// SD uses SPI2_HOST (FSPI). Keep the LCD on the separate HSPI/SPI3 peripheral.
Arduino_DataBus *bus = new Arduino_ESP32SPI(BoardProfile::LCD_DC, BoardProfile::LCD_CS,
    BoardProfile::LCD_SCK, BoardProfile::LCD_MOSI, GFX_NOT_DEFINED, HSPI);
Arduino_GFX *gfx = new JD9853(bus);
constexpr uint16_t WHITE=0xffff, MUTED=0xbdf7, BLUE=0x10e8, RED=0xa8c4;
constexpr uint16_t TEAL=0x02c9, GRAY=0x2965, AMBER=0xfea0, DARK=0x1082;
bool initialized=false, hid=false, secured=false, armed=false, bootloader=false;
bool down=false, handled=false, canceled=false, waitForRelease=true;
bool bootDown=false, bootHeld=false;
uint32_t bootAt=0, holdAt=0, lastFreshAt=0, noticeUntil=0;
uint32_t previousSeconds=UINT32_MAX;
int held=-1, oldPixels=-1;
Action heldAction=Action::None;
String previous;
uint16_t background=BLUE;

void text(const char *value, int y, int size=1, uint16_t color=WHITE,
          int center=Touch147::CONTENT_WIDTH/2) {
  gfx->setTextSize(size); gfx->setTextColor(color);
  gfx->setCursor(max(0,center-int(strlen(value))*3*size),y); gfx->print(value);
}
void frame(const char *headline, uint16_t color=BLUE, bool controls=false) {
  background=color; gfx->fillScreen(color);
  gfx->fillRect(0,0,Touch147::WIDTH,24,DARK);
  gfx->setTextSize(2); gfx->setTextColor(WHITE);
  gfx->setCursor(6,4); gfx->print("WITS DEPLOY");
  // The version uses the same readable 2x font as the title, flush right.
  constexpr int versionWidth=(sizeof(Firmware::VERSION)-1)*12;
  static_assert(versionWidth<=Touch147::WIDTH-156,"Firmware version overlaps the header title");
  text(Firmware::VERSION,4,2,WHITE,Touch147::WIDTH-6-versionWidth/2);
  text(headline,34,2,WHITE,controls?Touch147::CONTENT_WIDTH/2:Touch147::WIDTH/2);
}
uint32_t duration(Action action) {
  if (action==Action::Clear) return 5000;
  if (action==Action::Pair || action==Action::Hid || action==Action::Flash || action==Action::Program) return 2000;
  return 0;
}
Action actionFor(int index) {
  if (!hid) return index==0?Action::Flash:Action::Hid;
  switch(index) {
    case 0:return Action::Pair; case 1:return Action::Stop;
    case 2:return secured?Action::Arm:Action::None;
    case 3:return Action::Clear; case 4:return Action::Program;
    default:return Action::None;
  }
}
void progress(int pixels) {
  if (held<0 || pixels==oldPixels) return;
  auto r=Touch147::button(held,hid);
  gfx->fillRect(r.x+4,r.y+4,r.width-8,4,GRAY);
  if(pixels>0)gfx->fillRect(r.x+4,r.y+4,pixels,4,WHITE);
  oldPixels=pixels;
}
void button(int index,const char *label,uint16_t color,uint16_t ink=WHITE) {
  auto r=Touch147::button(index,hid);
  gfx->fillRoundRect(r.x,r.y,r.width,r.height,4,color);
  gfx->drawRoundRect(r.x,r.y,r.width,r.height,4,WHITE);
  gfx->setTextSize(2); gfx->setTextColor(ink);
  gfx->setCursor(r.x+(r.width-int(strlen(label))*12)/2,r.y+(hid?14:20)); gfx->print(label);
  if(duration(actionFor(index)))gfx->drawRect(r.x+4,r.y+4,r.width-8,4,MUTED);
}
void countdown(uint32_t seconds) {
  char value[8]; snprintf(value,sizeof(value),"%2lus",static_cast<unsigned long>(seconds));
  gfx->setTextSize(2); gfx->setTextColor(WHITE,background); gfx->setCursor(56,130); gfx->print(value);
}
Action physicalButton() {
  bool pressed=digitalRead(0)==LOW;
  if(pressed&&!bootDown){bootAt=millis();bootHeld=false;bootDown=true;if(hid)return Action::Stop;}
  if(pressed&&millis()-bootAt>=2000)bootHeld=true;
  if(!pressed&&bootDown){bootDown=false;if(bootHeld)return hid?Action::Pair:Action::Hid;}
  return Action::None;
}
} // namespace

void begin() {
  initialized=gfx->begin(40000000);
  if(!initialized)return;
  gfx->setTextWrap(false); gfx->fillScreen(BLUE); BoardHardware::backlightOn();
}
bool prepareRestart(){return true;} // SPI transactions finish synchronously; no continuous RGB DMA.
Action pollAction() {
  if(!initialized||bootloader)return Action::None;
  Action physical=physicalButton(); if(physical!=Action::None)return physical;
  bool pressed=false;uint16_t x=0,y=0;
  bool fresh=BoardHardware::readTouch(pressed,x,y);
  if (fresh && (x == 0xffff || y == 0xffff)) canceled = true;
  if(fresh)lastFreshAt=millis();
  else if(millis()-lastFreshAt<=200&&down&&held>=0){pressed=true;auto r=Touch147::button(held,hid);x=r.x+1;y=r.y+1;}
  else if(down)canceled=true;
  if(noticeUntil){waitForRelease=pressed;down=pressed;return Action::None;}
  if(waitForRelease){if(!pressed){waitForRelease=false;down=false;}return Action::None;}
  if(pressed&&!down){
    held=Touch147::hit(x,y,hid);heldAction=held<0?Action::None:actionFor(held);
    holdAt=millis();handled=canceled=false;oldPixels=-1;down=true;
    if(heldAction==Action::Stop){handled=true;return heldAction;}
  }
  if(pressed&&down){
    if(Touch147::hit(x,y,hid)!=held)canceled=true;
    uint32_t hold=duration(heldAction);
    if(!handled&&!canceled&&hold){
      progress(Touch147::progress(millis()-holdAt,hold,Touch147::button(held,hid).width-8));
      if(millis()-holdAt>=hold){handled=true;return heldAction;}
    }else if(canceled)progress(0);
  }
  if(!pressed&&down){
    down=false;progress(0);held=-1;
    return !handled&&!canceled&&heldAction==Action::Arm?Action::Arm:Action::None;
  }
  return Action::None;
}
void showBootloader(){if(initialized){bootloader=true;frame("BOOTLOADER");text("Press RESET",80,2,WHITE,160);text("to resume",110,2,WHITE,160);}}
void showPairingCleared(){if(initialized){frame("BT CLEARED",TEAL);text("Pairings removed",90,2,WHITE,160);noticeUntil=millis()+3000;previous="";}}
void showStorageBusy(){if(initialized){frame("EJECT SD");text("Safely eject on PC",80,2,WHITE,160);text("then try again",110,2,WHITE,160);noticeUntil=millis()+3000;previous="";}}
void showUpdate(){if(initialized){frame("OTA UPDATE");text("See app progress",80,2,WHITE,160);text("Keep power on",110,2,WHITE,160);}}
void updateHoldProgress(uint16_t,uint16_t){}
void update(bool hidMode,bool connected,bool authenticated,bool pairing,bool isArmed,
            bool typing,bool identifying,uint32_t seconds) {
  if(!initialized||bootloader)return;
  if(noticeUntil&&int32_t(millis()-noticeUntil)<0)return;
  noticeUntil=0;
  if((hid!=hidMode||secured!=authenticated||armed!=isArmed)&&down)waitForRelease=true;
  hid=hidMode;secured=authenticated;armed=isArmed;
  auto storage=Storage::snapshot();const auto&p=storage.policy;
  bool showPin=pairing||(connected&&!secured&&!BleTransport::reconnecting());
  char alias[BleTransport::MAX_IDENTIFY_LABEL_BYTES+1]={};
  if(identifying)BleTransport::copyIdentifyLabel(alias,sizeof(alias));
  String key=String(hid)+connected+secured+pairing+armed+typing+identifying+":"+alias+
      ":"+(showPin?BleTransport::passkey():0)+":"+p.present+p.exported+p.writable+p.error;
  if(key==previous){if(pairing&&seconds!=previousSeconds)countdown(seconds);previousSeconds=seconds;return;}
  previous=key;previousSeconds=seconds;oldPixels=-1;
  frame(!hid?"PROGRAM":typing&&armed?"TYPING":armed?"ARMED":pairing?"PAIRING":
        connected&&!secured?"CONNECTING":connected?"DISARMED":"OFFLINE",armed?RED:secured?TEAL:BLUE,true);
  if(showPin){
    char pin[7];snprintf(pin,sizeof(pin),"%06lu",static_cast<unsigned long>(BleTransport::passkey()));
    text(pin,62,3);text("Enter PIN",92,2);text("on PC",112,2);if(pairing)countdown(seconds);
  }else if(identifying){
    // Three readable lines fit the full 32-character alias in the left panel.
    const char *label=alias[0]?alias:BleTransport::deviceId();
    for(size_t offset=0;offset<strlen(label);offset+=12){
      char line[13]={};strncpy(line,label+offset,12);
      text(line,64+(offset/12)*22,2);
    }
  }else{
    String id=String("ID ")+BleTransport::deviceId();text(id.c_str(),67,2);
    const char *first=!BoardHardware::touchAvailable()?"Hold BOOT":!hid?"Hold HID":
        typing&&armed?"Tap STOP":armed?"Tap DISARM":secured?"Tap ARM":"Hold PAIR";
    const char *second=!BoardHardware::touchAvailable()?(hid?"to pair":"to start"):
        !hid?"to start":typing&&armed?"to cancel":armed?"to stop":secured?"to type":"to connect";
    text(first,96,2);text(second,116,2);
  }
  text(!BoardHardware::touchAvailable()?"NO TOUCH":!hid?"Hold FLASH":p.error?"SD ERROR":!p.present?"NO SD CARD":
       !p.exported?"SD EJECTED":p.writable?"SD WRITABLE":"SD READ ONLY",148,2,
       BoardHardware::touchAvailable()?WHITE:AMBER);
  if(hid){
    button(0,"PAIR",GRAY);button(1,"STOP",WHITE,RED);
    button(2,armed?"DISARM":"ARM",secured?AMBER:GRAY,secured?DARK:MUTED);
    button(3,"CLEAR",GRAY);button(4,"PROG",GRAY);
  }else{button(0,"FLASH",GRAY);button(1,"HID",TEAL);}
}
} // namespace StatusDisplay
#endif
