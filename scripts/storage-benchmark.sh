#!/usr/bin/env bash
# Host-side throughput check for the board's USB drive. Safe: it only writes one
# temporary file inside the mounted volume (deleted afterwards) and reads the raw
# device without writing to it. Needs no root. See docs/STORAGE-BENCHMARK.md.
#
# Usage: bash scripts/storage-benchmark.sh [MOUNT_DIR] [DEVICE]
#   MOUNT_DIR  mounted read/write volume, default /run/media/$USER/WITS-Deploy
#   DEVICE     whole block device for the raw read test, default autodetected,
#              pass "none" to skip the raw read test
set -euo pipefail

MOUNT_DIR="${1:-/run/media/$USER/WITS-Deploy}"
DEVICE="${2:-}"
SIZE_MIB="${BENCH_SIZE_MIB:-32}"

[[ -d "$MOUNT_DIR" ]] || { echo "Mount directory not found: $MOUNT_DIR" >&2; exit 1; }
[[ -w "$MOUNT_DIR" ]] || { echo "Volume is not writable. Mount it read/write first: $MOUNT_DIR" >&2; exit 1; }

dirty_mb() { awk '/^Dirty:/{printf "%.0f", $2/1024}' /proc/meminfo; }
rate() { awk -v b="$1" -v s="$2" 'BEGIN{ if (s<=0) s=0.001; printf "%.2f MB/s (%d MiB in %.1f s)", b/1048576/s, b/1048576, s }'; }
now() { date +%s.%N; }

if [[ "$(dirty_mb)" -gt 64 ]]; then
  echo "Warning: $(dirty_mb) MB of unwritten data is already queued on this machine; numbers may be skewed." >&2
fi

echo "Mount:  $MOUNT_DIR"
findmnt -n -o SOURCE,FSTYPE,OPTIONS "$MOUNT_DIR" | cut -c1-110 || true
USB_LINE=$(for d in /sys/bus/usb/devices/*; do
  if [[ -f "$d/idVendor" && "$(cat "$d/idVendor")" == "303a" ]]; then
    echo "$(cat "$d/product" 2>/dev/null) at $(cat "$d/speed") Mbps"
  fi
done | head -1 || true)
echo "USB:    ${USB_LINE:-Espressif device not found}"
echo

# 1) Raw read of the first 64 MiB of the device, direct I/O, three request sizes.
if [[ -z "$DEVICE" ]]; then
  SRC=$(findmnt -n -o SOURCE "$MOUNT_DIR" || true)
  DEVICE=$(lsblk -no PKNAME "$SRC" 2>/dev/null | head -1 || true)
  [[ -n "$DEVICE" ]] && DEVICE="/dev/$DEVICE" || DEVICE="none"
fi
if [[ "$DEVICE" != "none" && -r "$DEVICE" ]]; then
  echo "== Raw read, direct I/O, 64 MiB from $DEVICE (non-destructive)"
  for bs in 4096 65536 524288; do
    count=$((64 * 1048576 / bs))
    start=$(now)
    dd if="$DEVICE" of=/dev/null bs="$bs" count="$count" iflag=direct status=none
    end=$(now)
    printf "   block %7d bytes: %s\n" "$bs" "$(rate $((64 * 1048576)) "$(awk -v a="$start" -v b="$end" 'BEGIN{print b-a}')")"
  done
else
  echo "== Raw read skipped (no readable device; run with sudo, add yourself to the disk group, or pass the device)"
fi
echo

# 2) File write with flush, 3) cold read.
FILE="$MOUNT_DIR/.wits-benchmark-$$.bin"
trap 'rm -f "$FILE"' EXIT
BYTES=$((SIZE_MIB * 1048576))
echo "== File write, $SIZE_MIB MiB random data, flushed to the card"
head -c "$BYTES" /dev/urandom > "/tmp/wits-benchmark-source-$$.bin"
trap 'rm -f "$FILE" "/tmp/wits-benchmark-source-$$.bin"' EXIT
start=$(now)
dd if="/tmp/wits-benchmark-source-$$.bin" of="$FILE" bs=1M conv=fsync status=none
end=$(now)
echo "   write: $(rate "$BYTES" "$(awk -v a="$start" -v b="$end" 'BEGIN{print b-a}')")"
echo "   Dirty after flush: $(dirty_mb) MB"

echo "== File read, cold cache"
# Drop this file's cached pages (works without root once its data is written).
dd of="$FILE" oflag=nocache conv=notrunc,fdatasync count=0 status=none
start=$(now)
dd if="$FILE" of=/dev/null bs=1M iflag=nocache status=none
end=$(now)
echo "   read:  $(rate "$BYTES" "$(awk -v a="$start" -v b="$end" 'BEGIN{print b-a}')")"

echo "== Integrity"
if cmp -s "/tmp/wits-benchmark-source-$$.bin" "$FILE"; then echo "   readback matches the source"; else echo "   MISMATCH: readback differs from the source" >&2; exit 2; fi

echo
echo "Partition start sector (alignment check): $(cat /sys/class/block/"$(basename "$(findmnt -n -o SOURCE "$MOUNT_DIR")")"/start 2>/dev/null || echo unknown)"
echo "Temporary files removed. Delete nothing else on the card to keep the comparison fair."
