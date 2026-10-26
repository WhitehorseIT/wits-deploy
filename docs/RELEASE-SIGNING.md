# Release signing

The app and the firmware are released separately. **App releases** are tagged `v<version>` and carry
the Linux app; **firmware releases** are tagged `fw-v<version>` and carry the firmware ZIP. Every release
carries a `release-manifest.json` and a detached signature `release-manifest.json.sig`, and the manifest
records its `kind` (`app` or `firmware`), which the app checks against the tag it was served under. The manifest lists the release version, an optional
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

**Firmware** (only when the firmware changes): set the version in `src/firmware_version.h`, write
`docs/release-notes/firmware-<version>.md`, and push the tag `fw-v<version>` (for example
`fw-v1.0.0-rc1`). The **Firmware release** workflow builds the three board images, writes and signs the
manifest and publishes the release (a prerelease for `-dev` and `-rc` versions).

**App:** set the version in `desktop/wits_keyboard/__init__.py`, write `docs/release-notes/<version>.md`,
and push the tag `v<version>`. The **Release** workflow builds the Linux app with the firmware release
named in `desktop/packaging/firmware-release.txt` (it downloads and verifies that published firmware, so
publish the firmware release first), signs the manifest and publishes the release.

To flag a critical update, put the minimum safe version in `docs/release-notes/critical-below-app.txt` or
`critical-below-firmware.txt` before tagging; versions below it turn red.

Manual signing is also possible: `scripts/release-signing.py manifest ...` then `... sign ...`.

## App self-update (packaged Linux build)

When a newer release has a verified signature, the board list shows **Update app to X…** (hidden for
source installs and when the install folder is not writable). The app downloads the signed Linux
archive, checks its size and SHA-256 against the manifest, unpacks it beside the running copy
(in the same parent folder, for example `~/Apps`) and restarts into it. The running copy is never
modified. If the new version exits within 25 seconds of starting, a small wrapper starts the previous
version instead. After the new version has run for 15 seconds it moves the menu and sign-in shortcuts
to itself, and notes where the previous copy is so you can delete it. Updates need a confirmation and
are blocked while a board is armed or typing.

## Manifest compatibility

Installed apps validate every manifest they see, and one they reject is treated as unsigned (no
critical flag, no downloads, no app update). From 0.2.0-dev22 apps ignore file labels they do not know,
but older apps do not. A release may only add a new file label once the versions that matter can
tolerate it, so never add one in a release that older apps must still update to.
