#pragma once

#include <Arduino.h>

namespace BoardHardware {
bool begin();
bool selectCard();
bool readTouch(bool &pressed, uint16_t &x, uint16_t &y);
bool touchAvailable();
void backlightOn();
void backlightOff();
} // namespace BoardHardware
