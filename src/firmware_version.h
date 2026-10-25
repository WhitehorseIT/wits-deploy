#pragma once

namespace Firmware {

// Keep the on-device label and release artifact version in agreement.
// scripts/build-release.sh checks this before producing a named release.
constexpr char VERSION[] = "0.2.0-dev17";

} // namespace Firmware
