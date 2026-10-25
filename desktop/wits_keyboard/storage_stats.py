"""Turn two cumulative storage counter samples into a short throughput summary."""

MIB = 1024 * 1024


def _rate(megabytes, seconds):
    return megabytes / seconds if seconds > 0 else 0.0


def summarize(previous: dict | None, current: dict | None) -> str | None:
    """Describe the traffic between two samples, or None if there was none.

    The counters only count up while the board runs, so a smaller value means
    the board restarted and the comparison is meaningless.
    """
    if not previous or not current:
        return None
    if any(current[key] < previous[key] for key in ("rb", "wb", "rc", "wc", "rt", "wt", "ru", "wu")):
        return None
    parts = []
    for label, bytes_key, calls_key, callback_key, sd_key in (
        ("read", "rb", "rc", "rt", "ru"), ("write", "wb", "wc", "wt", "wu"),
    ):
        moved = current[bytes_key] - previous[bytes_key]
        calls = current[calls_key] - previous[calls_key]
        if moved <= 0 or calls <= 0:
            continue
        busy_s = (current[callback_key] - previous[callback_key]) / 1_000_000
        sd_s = (current[sd_key] - previous[sd_key]) / 1_000_000
        share = f", {100 * sd_s / busy_s:.0f}% in the SD card" if busy_s > 0 else ""
        parts.append(
            f"{label} {_rate(moved / MIB, busy_s):.2f} MB/s while busy "
            f"({moved / MIB:.1f} MiB, avg {moved / calls / 1024:.1f} KiB per request{share})"
        )
    if not parts:
        return None
    parts.append(f"largest request {current['mx'] / 1024:.1f} KiB, slowest {current['sl']} ms")
    if current["er"] > previous["er"]:
        parts.append(f"{current['er'] - previous['er']} I/O error(s)")
    return "Since last refresh: " + "; ".join(parts)
