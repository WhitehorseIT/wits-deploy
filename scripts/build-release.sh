#!/usr/bin/env bash
set -euo pipefail

project_dir=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)
version=${1:-dev}
target=${2:-tqtpro}
if [[ ! "$version" =~ ^[0-9A-Za-z][0-9A-Za-z.-]*$ ]]; then
  echo "Invalid release version." >&2
  exit 1
fi
case "$target" in
  tqtpro) image_name="WITS-Deploy-TQTPro-$version" ;;
  waveshare7) image_name="WITS-Deploy-Waveshare7-$version" ;;
  waveshare147) image_name="WITS-Deploy-Waveshare147-$version" ;;
  *) echo "Unknown board target: $target" >&2; exit 1 ;;
esac
build_dir="$project_dir/.pio/build/$target"
release_root=${WITS_RELEASE_ROOT:-$project_dir/releases/firmware}
release_dir="$release_root/$version/$target"
pio="$project_dir/.venv-pio/bin/pio"
esptool=${ESPTOOL:-$HOME/.platformio/packages/tool-esptool/esptool}
boot_app0=${BOOT_APP0:-$HOME/.platformio/packages/framework-arduinoespressif32/tools/partitions/boot_app0.bin}

firmware_version=$(sed -n 's/^constexpr char VERSION\[\] = "\([^"]*\)";$/\1/p' "$project_dir/src/firmware_version.h")
if [[ -z "$firmware_version" || ( "$version" != dev && "$version" != "$firmware_version" ) ]]; then
  echo "Release version '$version' must match src/firmware_version.h ('$firmware_version')." >&2
  exit 1
fi
if [[ -e "$release_dir/$image_name.factory.bin" || -e "$release_dir/$image_name.app.bin" ]]; then
  echo "Refusing to overwrite existing firmware release $version." >&2
  exit 1
fi

if [[ ! -x "$pio" ]]; then
  echo "PlatformIO virtual environment not found at $pio" >&2
  exit 1
fi

"$pio" run -e "$target"
mkdir -p "$release_dir"

output="$release_dir/$image_name.factory.bin"
"$esptool" --chip esp32s3 merge-bin \
  --flash-mode keep \
  --flash-freq keep \
  --flash-size keep \
  --output "$output" \
  0x0000 "$build_dir/bootloader.bin" \
  0x8000 "$build_dir/partitions.bin" \
  0xe000 "$boot_app0" \
  0x10000 "$build_dir/firmware.bin"

# The T-QT Pro's compiled bootloader uses DIO. Overriding the merged image to
# QIO makes affected boards reset before the application can start.
image_info=$($esptool image-info "$output")
if ! grep -q '^Flash mode: DIO$' <<<"$image_info"; then
  echo "Refusing release: merged bootloader did not retain DIO flash mode." >&2
  exit 1
fi

cp "$project_dir/scripts/flash-windows.cmd" "$release_dir/"
cp "$project_dir/scripts/FLASHING-INSTRUCTIONS.txt" "$release_dir/"
cp "$build_dir/firmware.bin" "$release_dir/$image_name.app.bin"
python3 "$project_dir/scripts/make-ota-manifest.py" "$release_dir/$image_name.app.bin" "$target" "$version"
(
  cd "$release_dir"
  sha256sum "$(basename "$output")" "$image_name.app.bin" > SHA256SUMS.txt
)

echo "Release bundle created in $release_dir"

catalog_dir="$release_root/$version"
if [[ -f "$catalog_dir/tqtpro/WITS-Deploy-TQTPro-$version.ota.json" &&
      -f "$catalog_dir/waveshare7/WITS-Deploy-Waveshare7-$version.ota.json" &&
      -f "$catalog_dir/waveshare147/WITS-Deploy-Waveshare147-$version.ota.json" ]]; then
  python3 "$project_dir/scripts/make-ota-catalog.py" "$catalog_dir"
fi
