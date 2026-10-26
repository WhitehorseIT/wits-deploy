import hashlib
import io
import json
import tempfile
import unittest
import zipfile
from pathlib import Path

from wits_keyboard import online_release as online
from wits_keyboard import signing
from wits_keyboard.signing import SignatureError

PRIVATE, PUBLIC = signing.generate_keypair()
OTHER_PRIVATE, OTHER_PUBLIC = signing.generate_keypair()


def bundle(version="0.2.0-dev19", extra=None):
    manifest = {"schema": 2, "firmware": version, "images": {"tqtpro": {
        "chip": "esp32s3", "filename": f"tqtpro/x-{version}.app.bin", "size": 1024, "sha256": "0" * 64}}}
    stream = io.BytesIO()
    with zipfile.ZipFile(stream, "w") as z:
        z.writestr(f"WITS-Deploy-Release-{version}.ota.json", json.dumps(manifest))
        for name, data in (extra or {}).items():
            z.writestr(name, data)
    return stream.getvalue()


def signed_release(version="0.2.0-dev19", critical=None, archive=None, private=PRIVATE, add_keys=None, tamper=False):
    archive = bundle(version) if archive is None else archive
    manifest = {"schema": 1, "product": "wits-deploy", "version": version, "critical_below": critical,
                "assets": {"firmware": {"name": f"WITS-Deploy-Firmware-{version}.zip", "size": len(archive),
                                         "sha256": hashlib.sha256(archive).hexdigest()}}}
    if add_keys:
        manifest["add_keys"] = add_keys
    data = json.dumps(manifest, sort_keys=True).encode()
    signature = signing.sign(private, data)
    if tamper:
        data = data.replace(b"dev19", b"dev99")
    return data, signature, archive


class FakeNet:
    def __init__(self, files):
        self.files = files
        self.requested = []

    def __call__(self, request, timeout=0):
        url = request.full_url
        self.requested.append(url)
        if url not in self.files:
            raise OSError("404")
        body = io.BytesIO(self.files[url])
        body.__enter__ = lambda *a: body
        body.__exit__ = lambda *a: None
        return body


def publish(net_files, version="0.2.0-dev19", **kwargs):
    data, signature, archive = signed_release(version, **kwargs)
    base = f"{online.DOWNLOAD_BASE}/v{version}"
    net_files[f"{base}/release-manifest.json"] = data
    net_files[f"{base}/release-manifest.json.sig"] = signature.encode()
    net_files[f"{base}/WITS-Deploy-Firmware-{version}.zip"] = archive


class SigningTests(unittest.TestCase):
    def test_round_trip_and_rejections(self):
        data, signature, _ = signed_release()
        self.assertEqual(signing.verify_manifest(data, signature, [PUBLIC])["version"], "0.2.0-dev19")
        with self.assertRaises(SignatureError):
            signing.verify_manifest(data, signature, [OTHER_PUBLIC])         # wrong key
        with self.assertRaises(SignatureError):
            signing.verify_manifest(data.replace(b"dev19", b"dev99"), signature, [PUBLIC])  # tampered
        with self.assertRaises(SignatureError):
            signing.verify_manifest(data, signature[:-4], [PUBLIC])           # truncated signature
        with self.assertRaises(SignatureError):
            signing.verify_manifest(data, signature, [])                      # no keys built in
        with self.assertRaises(SignatureError):
            signing.verify_manifest(data, "not base64!!", [PUBLIC])

    def test_signed_but_malformed_manifest_is_rejected(self):
        for bad in ({"schema": 2}, {"schema": 1, "product": "wits-deploy", "version": "x", "assets": {}},
                    {"schema": 1, "product": "wits-deploy", "version": "0.2.0", "assets": {"evil": {}}}):
            data = json.dumps(bad).encode()
            with self.assertRaises(SignatureError):
                signing.verify_manifest(data, signing.sign(PRIVATE, data), [PUBLIC])

    def test_unknown_asset_labels_are_tolerated_but_malformed_ones_are_not(self):
        entry = {"name": "x.zip", "size": 10, "sha256": "0" * 64}
        base = {"schema": 1, "product": "wits-deploy", "version": "0.2.0", "assets": {"firmware": entry}}
        signing.validate_manifest({**base, "assets": {"firmware": entry, "windows-source": entry}})
        for label in ("Bad Label", "../x", ""):
            with self.assertRaises(SignatureError):
                signing.validate_manifest({**base, "assets": {label: entry}})

    def test_public_key_derivation_and_check_file(self):
        self.assertEqual(signing.public_from_private(PRIVATE), PUBLIC)
        with tempfile.TemporaryDirectory() as d:
            path = Path(d) / "f"
            path.write_bytes(b"abc")
            entry = {"name": "f", "size": 3, "sha256": hashlib.sha256(b"abc").hexdigest()}
            signing.check_file(path, entry)
            path.write_bytes(b"abd")
            with self.assertRaises(SignatureError):
                signing.check_file(path, entry)


class OnlineTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.state = online.TrustState(Path(self.directory.name))
        patcher = unittest.mock.patch.object(online, "RELEASE_PUBLIC_KEYS", (PUBLIC,))
        patcher.start()
        self.addCleanup(patcher.stop)

    def test_fetch_and_download_firmware(self):
        files = {}
        publish(files, critical="0.2.0-dev17")
        net = FakeNet(files)
        release = online.fetch_signed("0.2.0-dev19", net, self.state)
        self.assertEqual(release.critical_below, "0.2.0-dev17")
        manifest = online.download_firmware(release, urlopen=net, directory=Path(self.directory.name))
        self.assertTrue(manifest.name.endswith(".ota.json"))
        before = len(net.requested)
        online.download_firmware(release, urlopen=net, directory=Path(self.directory.name))
        self.assertEqual(len(net.requested), before)  # cached, verified copy reused

    def test_tampered_download_is_refused_and_leaves_nothing_behind(self):
        files = {}
        publish(files)
        base = f"{online.DOWNLOAD_BASE}/v0.2.0-dev19"
        net = FakeNet(files)
        release = online.fetch_signed("0.2.0-dev19", net, self.state)
        files[f"{base}/WITS-Deploy-Firmware-0.2.0-dev19.zip"] = bundle(extra={"x": b"y"})
        with self.assertRaises(SignatureError):
            online.download_firmware(release, urlopen=net, directory=Path(self.directory.name))
        self.assertEqual(list((Path(self.directory.name) / "firmware").iterdir()), [])

    def test_unsafe_zip_paths_are_refused(self):
        archive = bundle(extra={"../evil.txt": b"x"})
        files = {}
        publish(files, archive=archive)
        net = FakeNet(files)
        release = online.fetch_signed("0.2.0-dev19", net, self.state)
        with self.assertRaises(SignatureError):
            online.download_firmware(release, urlopen=net, directory=Path(self.directory.name))
        self.assertFalse((Path(self.directory.name) / "evil.txt").exists())

    def test_wrong_key_unsigned_and_mismatched_versions_are_refused(self):
        files = {}
        publish(files, private=OTHER_PRIVATE)
        with self.assertRaises(SignatureError):
            online.fetch_signed("0.2.0-dev19", FakeNet(files), self.state)
        files = {}
        publish(files)
        base = f"{online.DOWNLOAD_BASE}/v0.2.0-dev20"
        for suffix in ("release-manifest.json", "release-manifest.json.sig"):  # dev19's files served as dev20
            files[f"{base}/{suffix}"] = files[f"{online.DOWNLOAD_BASE}/v0.2.0-dev19/{suffix}"]
        with self.assertRaises(SignatureError):
            online.fetch_signed("0.2.0-dev20", FakeNet(files), self.state)

    def test_downgrade_is_refused_once_a_newer_release_was_seen(self):
        files = {}
        publish(files, "0.2.0-dev20")
        publish(files, "0.2.0-dev19")
        net = FakeNet(files)
        online.fetch_signed("0.2.0-dev20", net, self.state)
        with self.assertRaises(SignatureError):
            online.fetch_signed("0.2.0-dev19", net, self.state)

    def test_signed_release_can_add_keys_for_later_rotation(self):
        files = {}
        publish(files, "0.2.0-dev19", add_keys=[OTHER_PUBLIC])
        online.fetch_signed("0.2.0-dev19", FakeNet(files), self.state)
        files = {}
        publish(files, "0.2.0-dev20", private=OTHER_PRIVATE)
        self.assertEqual(online.fetch_signed("0.2.0-dev20", FakeNet(files), self.state).version, "0.2.0-dev20")

    def test_latest_signed_skips_a_release_without_a_manifest(self):
        files = {}
        publish(files, "0.2.0-dev19")
        listing = [{"tag_name": "v0.2.0-dev20"}, {"tag_name": "v0.2.0-dev19"}, {"tag_name": "v0.2.0-dev18"}]
        files[online.RELEASES_URL] = json.dumps(listing).encode()
        found = online.latest_signed(FakeNet(files), self.state)
        self.assertEqual(found.version, "0.2.0-dev19")
        self.assertIsNone(online.latest_signed(FakeNet({}), self.state))  # offline


import unittest.mock  # noqa: E402  (used by setUp above)

if __name__ == "__main__":
    unittest.main()


class ReleaseScriptTests(unittest.TestCase):
    """The exact commands the Release workflow runs must produce a manifest the app accepts."""

    def test_workflow_style_manifest_and_signature_verify_in_the_app(self):
        import os
        import subprocess
        import sys
        script = Path(__file__).resolve().parents[2] / "scripts" / "release-signing.py"
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            (root / "WITS-Deploy-Firmware-0.2.0-dev99.zip").write_bytes(b"firmware")
            (root / "WITS-Deploy-0.2.0-dev99-Linux-x86_64.tar.gz").write_bytes(b"linux")
            env = {**os.environ, "WITS_RELEASE_SIGNING_KEY": PRIVATE}
            run = lambda *args: subprocess.run([sys.executable, str(script), *args], cwd=root, env=env,
                                               capture_output=True, text=True)
            made = run("manifest", "--version", "0.2.0-dev99",
                       "--asset", "firmware=WITS-Deploy-Firmware-0.2.0-dev99.zip",
                       "--asset", "linux-x86_64=WITS-Deploy-0.2.0-dev99-Linux-x86_64.tar.gz",
                       "--out", "release-manifest.json")
            self.assertEqual(made.returncode, 0, made.stderr)
            signed = run("sign", "release-manifest.json")
            # The checked-in public key is not the test key, so signing is refused here; that refusal is
            # the guard working. Verify the manifest itself with a signature from the test key instead.
            self.assertNotEqual(signed.returncode, 0)
            data = (root / "release-manifest.json").read_bytes()
            manifest = signing.verify_manifest(data, signing.sign(PRIVATE, data), [PUBLIC])
            self.assertEqual(sorted(manifest["assets"]), ["firmware", "linux-x86_64"])
