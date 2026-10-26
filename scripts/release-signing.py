#!/usr/bin/env python3
"""Create the release signing key, and build and sign a release manifest.

  keygen    make a new key pair (run once, on your own machine)
  manifest  write release-manifest.json for a set of release files
  sign      sign a manifest with the key in $WITS_RELEASE_SIGNING_KEY (or --key-file)

See docs/RELEASE-SIGNING.md.
"""
import argparse
import hashlib
import json
import os
import stat
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "desktop"))
from wits_keyboard import signing
from wits_keyboard.release_keys import RELEASE_PUBLIC_KEYS

DEFAULT_KEY = Path.home() / ".wits-deploy-signing" / "release-signing.key"


def keygen(args):
    path = Path(args.key_file).expanduser()
    if path.exists():
        sys.exit(f"{path} already exists; refusing to overwrite a signing key.")
    private, public = signing.generate_keypair()
    path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, stat.S_IRUSR | stat.S_IWUSR)
    with os.fdopen(descriptor, "w") as stream:
        stream.write(private + "\n")
    print(f"Private key written to {path} (owner read/write only). Back it up offline and never share it.")
    print(f"\nPublic key (safe to share; it goes into desktop/wits_keyboard/release_keys.py):\n{public}")
    print(f"\nNext, store the private key as the GitHub secret RELEASE_SIGNING_KEY without printing it:\n"
          f"  gh secret set RELEASE_SIGNING_KEY --repo WhitehorseIT/wits-deploy < {path}")


def manifest(args):
    assets = {}
    for item in args.asset:
        label, _, name = item.partition("=")
        path = Path(name)
        if not signing.ASSET_LABEL.fullmatch(label) or not path.is_file():
            sys.exit(f"Bad --asset {item!r}; use LABEL=FILE with a lowercase label and an existing file.")
        assets[label] = {"name": path.name, "size": path.stat().st_size,
                         "sha256": hashlib.sha256(path.read_bytes()).hexdigest()}
    data = {"schema": 1, "product": "wits-deploy", "version": args.version,
            "critical_below": args.critical_below or None, "assets": assets}
    if args.add_key:
        data["add_keys"] = args.add_key
    signing.validate_manifest(data)
    out = Path(args.out)
    out.write_text(json.dumps(data, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(f"Wrote {out}")


def sign(args):
    private = os.environ.get("WITS_RELEASE_SIGNING_KEY")
    if not private:
        private = Path(args.key_file).expanduser().read_text()
    private = private.strip()
    public = signing.public_from_private(private)
    if RELEASE_PUBLIC_KEYS and public not in RELEASE_PUBLIC_KEYS:
        sys.exit("This key is not one of the public keys built into the app; refusing to sign.")
    path = Path(args.manifest)
    data = path.read_bytes()
    signing.validate_manifest(json.loads(data))
    signature = signing.sign(private, data)
    signing.verify_manifest(data, signature, [public])
    Path(str(path) + ".sig").write_text(signature + "\n", encoding="ascii")
    print(f"Signed {path.name}")


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    commands = parser.add_subparsers(dest="command", required=True)
    p = commands.add_parser("keygen")
    p.add_argument("--key-file", default=str(DEFAULT_KEY))
    p.set_defaults(run=keygen)
    p = commands.add_parser("manifest")
    p.add_argument("--version", required=True)
    p.add_argument("--critical-below")
    p.add_argument("--add-key", action="append")
    p.add_argument("--asset", action="append", required=True, metavar="LABEL=FILE")
    p.add_argument("--out", default="release-manifest.json")
    p.set_defaults(run=manifest)
    p = commands.add_parser("sign")
    p.add_argument("manifest")
    p.add_argument("--key-file", default=str(DEFAULT_KEY))
    p.set_defaults(run=sign)
    args = parser.parse_args()
    args.run(args)


if __name__ == "__main__":
    main()
