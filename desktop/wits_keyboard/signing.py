"""Ed25519 signatures for release manifests, and checks of downloaded files against them."""
from __future__ import annotations

import base64
import binascii
import hashlib
import json
import re
from pathlib import Path

from .release_check import parse_version

MAX_MANIFEST_BYTES = 64 * 1024
ASSET_NAME = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]{0,120}")
ASSET_LABEL = re.compile(r"[a-z0-9][a-z0-9_-]{0,31}")  # unknown labels are tolerated so releases can add files later


class SignatureError(ValueError):
    """The manifest is unsigned, wrongly signed, malformed or otherwise untrustworthy."""


def _b64(text: str, length: int, what: str) -> bytes:
    try:
        raw = base64.b64decode(text.strip(), validate=True)
    except (binascii.Error, ValueError, AttributeError) as error:
        raise SignatureError(f"{what} is not valid base64") from error
    if len(raw) != length:
        raise SignatureError(f"{what} has the wrong length")
    return raw


def generate_keypair() -> tuple[str, str]:
    """Return (private, public) as base64 raw bytes."""
    from cryptography.hazmat.primitives import serialization
    from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
    private = Ed25519PrivateKey.generate()
    raw = dict(encoding=serialization.Encoding.Raw)
    return (base64.b64encode(private.private_bytes(**raw, format=serialization.PrivateFormat.Raw,
                                                    encryption_algorithm=serialization.NoEncryption())).decode(),
            base64.b64encode(private.public_key().public_bytes(**raw, format=serialization.PublicFormat.Raw)).decode())


def public_from_private(private_b64: str) -> str:
    from cryptography.hazmat.primitives import serialization
    from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
    private = Ed25519PrivateKey.from_private_bytes(_b64(private_b64, 32, "Private key"))
    return base64.b64encode(private.public_key().public_bytes(
        serialization.Encoding.Raw, serialization.PublicFormat.Raw)).decode()


def sign(private_b64: str, data: bytes) -> str:
    from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
    private = Ed25519PrivateKey.from_private_bytes(_b64(private_b64, 32, "Private key"))
    return base64.b64encode(private.sign(data)).decode()


def verify_signature(data: bytes, signature_text: str, keys) -> str:
    """Return the trusted key that signed ``data``; raise SignatureError otherwise."""
    from cryptography.exceptions import InvalidSignature
    from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey
    if not keys:
        raise SignatureError("No trusted signing keys are built into this app")
    signature = _b64(signature_text, 64, "Signature")
    for key in keys:
        try:
            Ed25519PublicKey.from_public_bytes(_b64(key, 32, "Trusted key")).verify(signature, data)
            return key
        except (InvalidSignature, SignatureError):
            continue
    raise SignatureError("The signature does not match any trusted key")


def validate_manifest(data) -> dict:
    if not isinstance(data, dict) or data.get("schema") != 1 or data.get("product") != "wits-deploy":
        raise SignatureError("Unsupported release manifest")
    version = data.get("version")
    if not isinstance(version, str) or parse_version(version) is None:
        raise SignatureError("Invalid release version")
    floor = data.get("critical_below")
    if floor is not None and (not isinstance(floor, str) or parse_version(floor) is None):
        raise SignatureError("Invalid critical-update threshold")
    assets = data.get("assets")
    if not isinstance(assets, dict) or not assets:
        raise SignatureError("The manifest lists no files")
    for label, entry in assets.items():
        if (not isinstance(label, str) or not ASSET_LABEL.fullmatch(label) or not isinstance(entry, dict)
                or not isinstance(entry.get("name"), str) or not ASSET_NAME.fullmatch(entry["name"])
                or type(entry.get("size")) is not int or not 0 < entry["size"] <= 1 << 30
                or not isinstance(entry.get("sha256"), str) or not re.fullmatch(r"[0-9a-f]{64}", entry["sha256"])):
            raise SignatureError(f"Invalid entry for {label}")
    for key in data.get("add_keys", []):
        _b64(key, 32, "Added key")
    return data


def verify_manifest(manifest_bytes: bytes, signature_text: str, keys) -> dict:
    if len(manifest_bytes) > MAX_MANIFEST_BYTES:
        raise SignatureError("The manifest is too large")
    verify_signature(manifest_bytes, signature_text, keys)  # check the signature before parsing anything
    try:
        data = json.loads(manifest_bytes)
    except ValueError as error:
        raise SignatureError("The manifest is not valid JSON") from error
    return validate_manifest(data)


def check_file(path: str | Path, entry: dict) -> None:
    """Raise SignatureError unless the file has exactly the size and SHA-256 the manifest lists."""
    path = Path(path)
    if path.stat().st_size != entry["size"]:
        raise SignatureError(f"{entry['name']} has an unexpected size")
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1 << 20), b""):
            digest.update(block)
    if digest.hexdigest() != entry["sha256"]:
        raise SignatureError(f"{entry['name']} does not match its signed checksum")
