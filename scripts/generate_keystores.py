#!/usr/bin/env python3
"""
Generate valid Solana wallet keystores for MTUS
Creates proper 64-byte Ed25519 keypairs
"""

import json
import os
import sys
import base64
import nacl.secret
import nacl.utils
import nacl.signing
import argon2
from pathlib import Path

project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
os.chdir(project_root)

ARGON2_OPTIONS = {
    "time_cost": 4,
    "memory_cost": 65536,
    "parallelism": 2,
    "hash_len": 32,
    "type": argon2.Type.ID,
}


def create_keystore(secret_key: bytes, passphrase: str, keystore_path: str) -> None:
    """Create encrypted keystore file"""
    salt = nacl.utils.random(16)
    derived_key = argon2.low_level.hash_secret_raw(
        passphrase.encode("utf-8"), salt, **ARGON2_OPTIONS
    )
    nonce = nacl.utils.random(nacl.secret.SecretBox.NONCE_SIZE)
    box = nacl.secret.SecretBox(derived_key)
    encrypted = box.encrypt(secret_key, nonce)

    keystore_data = {
        "salt": salt.hex(),
        "nonce": nonce.hex(),
        "encryptedSecretKey": encrypted.hex(),
        "kdfParams": {
            "timeCost": ARGON2_OPTIONS["time_cost"],
            "memoryCost": ARGON2_OPTIONS["memory_cost"],
            "parallelism": ARGON2_OPTIONS["parallelism"],
        },
    }

    with open(keystore_path, "w") as f:
        json.dump(keystore_data, f, indent=2)
    Path(keystore_path).chmod(0o600)


def generate_solana_keypair() -> bytes:
    """Generate a valid 64-byte Solana Ed25519 keypair"""
    # 32 bytes for private key
    private_key = nacl.utils.random(32)
    # Return 64 bytes (32 private + public derived from it)
    # For proper Solana, we need both secret and public key
    # Using nacl signing key for proper Ed25519
    signing_key = nacl.signing.SigningKey.generate()
    return signing_key._seed + signing_key.verify_key._key


def main():
    keystore_dir = os.path.join(project_root, "keystores")
    os.makedirs(keystore_dir, exist_ok=True)

    passphrase = os.environ.get("KEYSTORE_PASSPHRASE", "test123")

    print("=" * 50)
    print("MTUS Wallet Keystore Generator")
    print("=" * 50)
    print()

    # Sniper wallet
    print("Generating Sniper wallet...")
    sniper_secret = generate_solana_keypair()
    sniper_path = os.path.join(keystore_dir, "sniper.keystore")
    create_keystore(sniper_secret, passphrase, sniper_path)
    print(f"  ✓ Saved to: {sniper_path}")

    # Main wallet
    print("Generating Main wallet...")
    main_secret = generate_solana_keypair()
    main_path = os.path.join(keystore_dir, "main.keystore")
    create_keystore(main_secret, passphrase, main_path)
    print(f"  ✓ Saved to: {main_path}")

    print()
    print("=" * 50)
    print("Keystores created!")
    print(f"Directory: {keystore_dir}")
    print(f"Passphrase: {passphrase}")
    print("IMPORTANT: Backup these files - they contain your wallet keys!")
    print("=" * 50)


if __name__ == "__main__":
    main()
