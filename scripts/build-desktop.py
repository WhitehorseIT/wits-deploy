#!/usr/bin/env python3
"""Build and check a native standalone desktop package on Windows or Linux."""
import argparse
import ast
import hashlib
import importlib.metadata
import json
import os
from pathlib import Path
import platform
import shutil
import subprocess
import sys
import tarfile
from zipfile import ZIP_DEFLATED, ZipFile

PROJECT = Path(__file__).resolve().parents[1]
SOURCE = PROJECT / "desktop"
sys.path.insert(0, str(SOURCE))
from wits_keyboard.firmware_bundle import stage_release


def run(command, **kwargs):
    print("Running:", " ".join(map(str, command)), flush=True)
    subprocess.run(list(map(str, command)), check=True, **kwargs)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, help="artifact directory (defaults to releases/desktop/VERSION)")
    parser.add_argument("--firmware", type=Path, help="complete common firmware manifest to include")
    args = parser.parse_args()
    if sys.platform not in ("linux", "win32") or platform.machine().lower() not in ("amd64", "x86_64"):
        parser.error("this first native build supports Windows/Linux x86-64")
    module = ast.parse((SOURCE / "wits_keyboard/__init__.py").read_text())
    version = next(ast.literal_eval(node.value) for node in module.body if isinstance(node, ast.Assign)
                   and any(isinstance(target, ast.Name) and target.id == "__version__" for target in node.targets))
    target = "Windows-x64" if sys.platform == "win32" else "Linux-x86_64"
    output = (args.output or PROJECT / "releases" / "desktop" / version).resolve()
    output.mkdir(parents=True, exist_ok=True)
    base = f"WITS-Deploy-{version}-{target}"
    archive = output / (base + (".zip" if sys.platform == "win32" else ".tar.gz"))
    if archive.exists():
        parser.error("existing binary archive is immutable; use another output directory or app version")
    for dependency in ("PyInstaller", "esptool", "pyserial", "bleak", "PySide6"):
        try:
            print(dependency, importlib.metadata.version(dependency))
        except importlib.metadata.PackageNotFoundError:
            parser.error("missing build dependencies; install desktop/requirements-build.txt")
    build = PROJECT / "build" / "desktop" / target
    if build.exists():
        shutil.rmtree(build)
    build.mkdir(parents=True)
    firmware_version = (SOURCE / "packaging" / "firmware-release.txt").read_text().strip()
    manifest = args.firmware or (PROJECT / "releases" / "firmware" / firmware_version /
                                 f"WITS-Keyboard-Release-{firmware_version}.ota.json")
    try:
        firmware = stage_release(manifest, build / "firmware")
    except (ValueError, OSError) as error:
        parser.error(f"Cannot include firmware: {error}. Extract a complete firmware ZIP and pass --firmware PATH_TO_COMMON_JSON.")
    environment = dict(os.environ, QT_QPA_PLATFORM="offscreen", PYTHONPATH=str(SOURCE))
    run([sys.executable, "-m", "unittest", "discover", "-s", "tests"],
        cwd=SOURCE, env=environment, timeout=120)
    common = [sys.executable, "-m", "PyInstaller", "--noconfirm", "--clean", "--onedir", "--noupx",
              "--paths", SOURCE, "--specpath", build,
              "--workpath", build / "work", "--distpath", build / "dist"]
    run(common + ["--name", "WITS-Deploy", "--windowed", "--collect-submodules", "bleak",
                  "--add-data", f"{build / 'firmware'}{os.pathsep}firmware",
                  "--recursive-copy-metadata", "bleak",
                  "--hidden-import", "PySide6.QtSerialPort", SOURCE / "run.py"], cwd=PROJECT)
    run(common + ["--name", "WITS-Deploy-Worker", "--console", "--collect-all", "esptool",
                  "--recursive-copy-metadata", "esptool",
                  "--collect-submodules", "serial", "--exclude-module", "PySide6",
                  SOURCE / "worker.py"], cwd=PROJECT)
    bundle = build / "dist" / "WITS-Deploy"
    helper = build / "dist" / "WITS-Deploy-Worker"
    shutil.copytree(helper, bundle / "helpers" / helper.name)
    if sys.platform == "linux":
        installer = bundle / "INSTALL-LAUNCHER.sh"
        installer.write_text('#!/usr/bin/env bash\nset -euo pipefail\ncd -- "$(dirname -- "${BASH_SOURCE[0]}")"\n'
                             'exec ./helpers/WITS-Deploy-Worker/WITS-Deploy-Worker install-launcher "$@"\n')
        installer.chmod(0o755)
    else:
        shutil.copyfile(SOURCE / "packaging" / "INSTALL-SHORTCUT.cmd", bundle / "INSTALL-SHORTCUT.cmd")
    readme = (SOURCE / "packaging" / "README-NATIVE.txt").read_text()
    (bundle / "README-FIRST.txt").write_text(readme.replace("@VERSION@", version), encoding="utf-8")
    # Retain package metadata, including license declarations, with the artifact.
    dependencies = []
    for distribution in importlib.metadata.distributions():
        dependencies.append(dict(name=distribution.metadata["Name"], version=distribution.version,
                                 license=distribution.metadata.get("License-Expression") or distribution.metadata.get("License"),
                                 project_urls=distribution.metadata.get_all("Project-URL")))
        for item in distribution.files or ():
            if item.name.lower().startswith(("license", "copying", "notice")) and ".." not in item.parts:
                source = Path(distribution.locate_file(item))
                if source.is_file():
                    destination = bundle / "licenses" / distribution.metadata["Name"] / item
                    destination.parent.mkdir(parents=True, exist_ok=True)
                    shutil.copyfile(source, destination)
    (bundle / "DEPENDENCIES.json").write_text(json.dumps(dependencies, indent=2) + "\n")
    executable = bundle / ("WITS-Deploy.exe" if sys.platform == "win32" else "WITS-Deploy")
    report = build / "smoke-test.json"
    # The standalone check must not fall back to this checkout's Python modules.
    clean_environment = dict(os.environ, QT_QPA_PLATFORM="offscreen")
    clean_environment.pop("PYTHONPATH", None)
    clean_environment.pop("PYTHONHOME", None)
    try:
        run([executable, "--smoke-test", report], cwd=build, env=clean_environment, timeout=90)
    except subprocess.CalledProcessError:
        # The check records its own failure reason; show it in the build log.
        print(report.read_text() if report.is_file() else "The startup check wrote no report.", file=sys.stderr)
        raise
    checked = json.loads(report.read_text())
    if not checked.get("ok") or not checked.get("frozen"):
        raise RuntimeError(f"Standalone startup check failed: {checked}")
    (bundle / "BUILD-INFO.json").write_text(json.dumps(dict(
        app_version=version, firmware_version=firmware.version, target=target, python=platform.python_version(),
        build_platform=platform.platform(), smoke_test=checked), indent=2) + "\n")
    (bundle / "SHA256SUMS.txt").write_text("".join(
        f"{hashlib.sha256(path.read_bytes()).hexdigest()}  {path.relative_to(bundle).as_posix()}\n"
        for path in sorted(bundle.rglob("*")) if path.is_file() and path.name != "SHA256SUMS.txt"))
    if sys.platform == "win32":
        with ZipFile(archive, "x", compression=ZIP_DEFLATED) as stream:
            for path in sorted(bundle.rglob("*")):
                if path.is_file():
                    stream.write(path, Path(base) / path.relative_to(bundle))
    else:
        with tarfile.open(archive, "x:gz", dereference=True) as stream:
            stream.add(bundle, arcname=base)
    digest = hashlib.sha256(archive.read_bytes()).hexdigest()
    Path(str(archive) + ".sha256").write_text(f"{digest}  {archive.name}\n")
    print(f"Verified standalone artifact: {archive}\nSHA-256: {digest}")


if __name__ == "__main__":
    main()
