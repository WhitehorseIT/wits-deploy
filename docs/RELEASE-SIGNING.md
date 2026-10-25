# Release signing

Every release carries a `release-manifest.json` and a detached signature
`release-manifest.json.sig`. The manifest lists the release version, an optional
`critical_below` threshold, and the name, size and SHA-256 of each downloadable file. The app
trusts a download only if its manifest verifies against a public key built into the app and the
file matches the manifest.

## What this protects

A tampered or substituted firmware image or app archive, a wrong or truncated download, and a
manifest replayed from an older release (the app refuses to go back to an older version than one
it has already seen). It does not protect against a compromised signing key or GitHub account, and
it is separate from on-chip secure boot, which is not used.

## How it works

- Signatures are Ed25519 over the exact bytes of `release-manifest.json`.
- Download URLs are built by the app from the release tag and the file names in the signed
  manifest; the manifest cannot point the app at another host.
- Public keys live in `desktop/wits_keyboard/release_keys.py`. A signed manifest may list
  `add_keys`; the app remembers those after verifying the signature, so keys can be rotated
  without shipping a new app first.
- The private key is only the GitHub Actions secret `RELEASE_SIGNING_KEY`, plus an offline backup.

## One-time setup (maintainer)

```bash
python3 scripts/release-signing.py keygen
gh secret set RELEASE_SIGNING_KEY --repo WhitehorseIT/wits-deploy < ~/.wits-deploy-signing/release-signing.key
```

`keygen` writes the private key with owner-only permissions and prints the public key, which is
then committed in `release_keys.py`. Keep an offline backup of the private key; losing it means
shipping a new key inside a manually installed app.

## Publishing a release

1. Set the version in `src/firmware_version.h`, `desktop/wits_keyboard/__init__.py` and
   `desktop/packaging/firmware-release.txt`; optionally add `docs/release-notes/<version>.md`.
2. Push a tag `v<version>` (for example `v0.2.0-dev19`). The **Release** workflow builds the
   firmware and Linux app, writes and signs the manifest, and publishes a GitHub release
   (a prerelease for `-dev` and `-rc` versions).
3. To flag a critical update, put the minimum safe version in `docs/release-notes/critical-below.txt`
   before tagging; boards below it turn red.

Manual signing is also possible: `scripts/release-signing.py manifest ...` then `... sign ...`.
