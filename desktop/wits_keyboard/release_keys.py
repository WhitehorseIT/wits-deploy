"""Public keys that may sign releases (base64, raw 32-byte Ed25519).

The matching private key lives only in the project's release secret. Releases can add
further keys through a signed manifest, so this list rarely changes.
"""
RELEASE_PUBLIC_KEYS: tuple[str, ...] = ()
