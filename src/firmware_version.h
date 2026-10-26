#pragma once

namespace Firmware {

// Keep the on-device label and release artifact version in agreement.
// scripts/build-release.sh checks this before producing a named release.
constexpr char VERSION[] = "1.0.0-rc1";

} // namespace Firmware
