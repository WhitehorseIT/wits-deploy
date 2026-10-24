#include "board_hardware.h"
#include "board_profile.h"

#ifdef WITS_BOARD_WAVESHARE7
#include <Wire.h>

namespace BoardHardware {
namespace {
// Manufacturer base-model examples at commit bc51a84b30c0cea018fee6e0d7427ec10102060e:
// examples/Arduino/examples/03_SD_Test and supported board configuration.
uint8_t outputs = 0x1a; // TP_RST, LCD_RST, SD_CS high; BL and USB_SEL low.
uint8_t touchAddress = 0;
bool ready = false;

bool writeExpander(uint8_t address, uint8_t value) {
  Wire.beginTransmission(address);
  Wire.write(value);
  return Wire.endTransmission() == 0;
}

bool setOutput(uint8_t bit, bool high) {
  uint8_t next = high ? outputs | (1u << bit) : outputs & ~(1u << bit);
  if (!writeExpander(0x38, next)) return false;
  outputs = next;
  return true;
}

bool readRegister(uint16_t reg, uint8_t *data, size_t length) {
  if (!touchAddress) return false;
  Wire.beginTransmission(touchAddress);
  Wire.write(reg >> 8);
  Wire.write(reg & 0xff);
  if (Wire.endTransmission(false) != 0) return false;
  if (Wire.requestFrom(touchAddress, length) != length) return false;
  for (size_t i = 0; i < length; ++i) data[i] = Wire.read();
  return true;
}
} // namespace

bool begin() {
  Wire.begin(8, 9, 400000);
  Wire.setTimeOut(30);
  // Write the safe latch BEFORE enabling outputs: keep native USB selected.
  ready = writeExpander(0x38, outputs) && writeExpander(0x24, 0x01);
  if (!ready) return false;
  pinMode(4, OUTPUT);
  digitalWrite(4, LOW); // GT911 address selection at reset: 0x5d.
  setOutput(1, false);
  setOutput(3, false);
  delay(100);
  setOutput(3, true);
  setOutput(1, true);
  delay(200);
  pinMode(4, INPUT);
  for (uint8_t address : {uint8_t(0x5d), uint8_t(0x14)}) {
    touchAddress = address;
    uint8_t product[4];
    if (readRegister(0x8140, product, sizeof(product)) &&
        product[0] == '9' && product[1] == '1' && product[2] == '1') break;
    touchAddress = 0;
  }
  return true;
}

bool selectCard() {
  // Dedicated SD SPI bus, no other slaves. Vendor drives expander CS low
  // throughout use, with SPI hardware CS disabled (-1).
  return ready && setOutput(4, false);
}

bool touchAvailable() { return touchAddress != 0; }

bool readTouch(bool &pressed, uint16_t &x, uint16_t &y) {
  uint8_t status;
  if (!readRegister(0x814e, &status, 1) || !(status & 0x80)) return false;
  uint8_t point[8] = {};
  bool single = (status & 0x0f) == 1;
  bool valid = !single || readRegister(0x8150, point, sizeof(point));
  Wire.beginTransmission(touchAddress);
  Wire.write(0x81);
  Wire.write(0x4e);
  Wire.write(0);
  if (Wire.endTransmission() != 0 || !valid) return false;
  // First coordinate starts at 0x8150 (track ID is at 0x814f).
  x = point[0] | (uint16_t(point[1]) << 8);
  y = point[2] | (uint16_t(point[3]) << 8);
  pressed = single && x < 800 && y < 480;
  return true;
}

void backlightOn() { if (ready) setOutput(2, true); }
void backlightOff() { if (ready) setOutput(2, false); }
} // namespace BoardHardware
#elif defined(WITS_BOARD_WAVESHARE147)
#include <Wire.h>
#include "touch_controls147.h"

namespace BoardHardware {
namespace {
bool touchPresent = false;
constexpr uint8_t TOUCH_ADDRESS = 0x63;
}
bool begin() {
  pinMode(BoardProfile::SD_CS, OUTPUT);
  digitalWrite(BoardProfile::SD_CS, HIGH);
  pinMode(BoardProfile::LCD_CS, OUTPUT);
  digitalWrite(BoardProfile::LCD_CS, HIGH);
  pinMode(BoardProfile::LCD_BL, OUTPUT);
  digitalWrite(BoardProfile::LCD_BL, LOW);
  pinMode(BoardProfile::TOUCH_RST, OUTPUT);
  pinMode(BoardProfile::TOUCH_INT, INPUT_PULLUP);
  pinMode(0, INPUT_PULLUP);
  bool ready = Wire.begin(BoardProfile::TOUCH_SDA, BoardProfile::TOUCH_SCL, 400000);
  Wire.setTimeOut(30);
  digitalWrite(BoardProfile::TOUCH_RST, LOW);
  delay(200);
  digitalWrite(BoardProfile::TOUCH_RST, HIGH);
  delay(300);
  if (ready) {
    Wire.beginTransmission(TOUCH_ADDRESS);
    touchPresent = Wire.endTransmission() == 0;
  }
  return ready;
}
bool selectCard() { return true; } // Dedicated SPI2 bus; SD driver owns GPIO14 CS.
bool touchAvailable() { return touchPresent; }
bool readTouch(bool &pressed, uint16_t &x, uint16_t &y) {
  if (!touchPresent) return false;
  Wire.beginTransmission(TOUCH_ADDRESS);
  Wire.write(0x01); // AXS5106L touch report, count followed by 12-bit coordinates.
  if (Wire.endTransmission() != 0 || Wire.requestFrom(TOUCH_ADDRESS, uint8_t(14)) != 14) return false;
  uint8_t report[14];
  for (auto &byte : report) byte = Wire.read();
  uint16_t rawX = (uint16_t(report[2] & 0x0f) << 8) | report[3];
  uint16_t rawY = (uint16_t(report[4] & 0x0f) << 8) | report[5];
  auto contact = Touch147::decode(report[1] & 0x0f, rawX, rawY);
  pressed = contact.pressed;
  // Vendor portrait rotation zero mirrors X; display RAM has a 34-column offset.
  x = contact.x;
  y = contact.y;
  return true;
}
void backlightOn() { digitalWrite(BoardProfile::LCD_BL, HIGH); }
void backlightOff() { digitalWrite(BoardProfile::LCD_BL, LOW); }
} // namespace BoardHardware
#else
namespace BoardHardware {
bool begin() { return true; }
bool selectCard() { return false; }
bool readTouch(bool &, uint16_t &, uint16_t &) { return false; }
bool touchAvailable() { return false; }
void backlightOn() {}
void backlightOff() {}
} // namespace BoardHardware
#endif
