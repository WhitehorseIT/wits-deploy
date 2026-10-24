#!/usr/bin/env python3
"""Read WITS drive mounts/UDisks jobs without changing storage or opening UART."""
import asyncio
from datetime import datetime
import json
from pathlib import Path
import subprocess
import time

from dbus_fast import BusType, Message, MessageType, Variant
from dbus_fast.aio import MessageBus


def unwrap(value):
    if isinstance(value, Variant):
        return unwrap(value.value)
    if isinstance(value, dict):
        return {key: unwrap(item) for key, item in value.items()}
    if isinstance(value, (bytes, bytearray)):
        return bytes(value).rstrip(b"\0").decode(errors="replace")
    if isinstance(value, (list, tuple)):
        return [unwrap(item) for item in value]
    return value


async def inspect():
    bus = await MessageBus(bus_type=BusType.SYSTEM).connect()
    try:
        async with asyncio.timeout(10):
            reply = await bus.call(Message(destination="org.freedesktop.UDisks2",
                path="/org/freedesktop/UDisks2", interface="org.freedesktop.DBus.ObjectManager",
                member="GetManagedObjects"))
        if reply.message_type == MessageType.ERROR:
            raise RuntimeError(f"{reply.error_name}: {reply.body}")
        objects = unwrap(reply.body[0])
        drive_interface = "org.freedesktop.UDisks2.Drive"
        block_interface = "org.freedesktop.UDisks2.Block"
        fs_interface = "org.freedesktop.UDisks2.Filesystem"
        job_interface = "org.freedesktop.UDisks2.Job"
        drives = {path for path, interfaces in objects.items()
                  if "WITS" in interfaces.get(drive_interface, {}).get("Vendor", "").upper()
                  or "DEPLOYMENT SD" in interfaces.get(drive_interface, {}).get("Model", "").upper()}
        selected = set(drives)
        selected.update(path for path, interfaces in objects.items()
                        if interfaces.get(block_interface, {}).get("Drive") in drives)
        result = {"drives": [], "blocks": [], "jobs": []}
        for path in sorted(selected):
            interfaces = objects[path]
            if drive_interface in interfaces:
                fields = ("Vendor", "Model", "Serial", "ConnectionBus", "Ejectable", "MediaAvailable")
                result["drives"].append({"path": path, **{k: v for k, v in interfaces[drive_interface].items() if k in fields}})
            if block_interface in interfaces:
                fields = ("Device", "ReadOnly", "Size", "IdLabel", "IdType", "Drive")
                block = {"path": path, **{k: v for k, v in interfaces[block_interface].items() if k in fields}}
                block["MountPoints"] = interfaces.get(fs_interface, {}).get("MountPoints", [])
                for mount in block["MountPoints"]:
                    if isinstance(mount, list):
                        mount = bytes(mount).rstrip(b"\0").decode(errors="replace")
                    if isinstance(mount, str) and mount.startswith(("/run/media/", "/media/")):
                        try:
                            check = subprocess.run(["fuser", "-vm", "--", mount], text=True,
                                capture_output=True, timeout=5)
                            block.setdefault("open_processes", []).append({"mount": mount,
                                "output": check.stdout + check.stderr})
                        except (OSError, subprocess.TimeoutExpired) as error:
                            block["open_processes_error"] = str(error)
                result["blocks"].append(block)
        for path, interfaces in objects.items():
            job = interfaces.get(job_interface)
            if job and selected.intersection(job.get("Objects", [])):
                fields = ("Operation", "Objects", "Progress", "ProgressValid", "Cancelable", "StartedByUID")
                result["jobs"].append({"path": path, **{k: v for k, v in job.items() if k in fields}})
        return result
    finally:
        bus.disconnect()


def main():
    try:
        result = asyncio.run(inspect())
    except Exception as error:
        result = {"error": str(error)}
    try:
        processes = subprocess.run(["ps", "-eo", "pid,ppid,stat,wchan:32,comm"],
            capture_output=True, text=True, timeout=5).stdout.splitlines()
        relevant = [line for line in processes if any(name in line for name in
                    ("udisksd", "umount", "mount.exfat", "fusermount"))]
        result["unmount_processes"] = relevant
        # UDisks mount paths may already be gone while an unmount worker waits.
        # A pair of host disk counters helps distinguish disk I/O from job waits.
        devices = {Path(block.get("Device", "")).name for block in result.get("blocks", [])}
        samples = []
        for _ in range(2):
            samples.append([line.strip() for line in Path("/proc/diskstats").read_text().splitlines()
                            if len(line.split()) > 2 and line.split()[2] in devices])
            if len(samples) == 1:
                time.sleep(1)
        result["diskstats_one_second_apart"] = samples
    except (OSError, subprocess.TimeoutExpired) as error:
        result["process_diagnostic_error"] = str(error)
    output = json.dumps(result, indent=2)
    path = Path(__file__).resolve().parents[1] / "desktop/logs" / f"wits-storage-diagnostic-{datetime.now():%Y%m%d-%H%M%S}.json"
    path.parent.mkdir(exist_ok=True)
    path.write_text(output + "\n")
    print(output)
    print(f"Saved: {path}")


if __name__ == "__main__":
    main()
