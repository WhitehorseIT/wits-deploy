#pragma once

#include <Arduino.h>

namespace StatusDisplay {

enum class Action : uint8_t { None, Hid, Flash, Pair, Clear, Arm, Stop, Program };
Action pollAction();
void begin();
bool prepareRestart();
void showBootloader();
void showPairingCleared();
void showStorageBusy();
void showUpdate();
void updateHoldProgress(uint16_t leftPermille, uint16_t rightPermille);
void update(bool hidMode,
            bool connected,
            bool authenticated,
            bool pairing,
            bool armed,
            bool typing,
            bool identifying,
            uint32_t pairingSeconds);

} // namespace StatusDisplay
