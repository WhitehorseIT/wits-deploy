#pragma once
#include <Arduino.h>
namespace FirmwareUpdate {
using Notify = void (*)(const uint8_t *, size_t);
void begin(Notify notify);
void loop();
void confirmBoot(bool hardwareReady);
bool active();
void disconnected();
void control(const uint8_t *, size_t);
void data(const uint8_t *, size_t);
} // namespace FirmwareUpdate
