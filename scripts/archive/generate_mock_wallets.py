#!/usr/bin/env python3
"""
Generate mock wallet keystores for testing
Uses nacl for keypair generation
"""

import os
import sys
import json
import nacl.secret
import nacl.utils
import argon2
from pathlib import Path

project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
os.chdir(project_root)

# Add src to path for solana keypair
sys.path.insert(0, project_root)
sys.path.insert(0, os.path.join(project_root, "src", "python"))

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
        "encryptedSecretKey": encrypted.ciphertext.hex(),
        "kdfParams": {
            "timeCost": ARGON2_OPTIONS["time_cost"],
            "memoryCost": ARGON2_OPTIONS["memory_cost"],
            "parallelism": ARGON2_OPTIONS["parallelism"],
        },
    }

    with open(keystore_path, "w") as f:
        json.dump(keystore_data, f, indent=2)
    Path(keystore_path).chmod(0o600)


def load_keypair(passphrase: str, keystore_path: str) -> bytes:
    """Load keypair from keystore"""
    with open(keystore_path, "r") as f:
        data = json.load(f)

    salt = bytes.fromhex(data["salt"])
    nonce = bytes.fromhex(data["nonce"])
    encrypted_secret = bytes.fromhex(data["encryptedSecretKey"])

    derived_key = argon2.low_level.hash_secret_raw(
        passphrase.encode("utf-8"), salt, **ARGON2_OPTIONS
    )

    box = nacl.secret.SecretBox(derived_key)
    return box.decrypt(encrypted_secret, nonce)


def bytes_to_base58(bytes_key: bytes) -> str:
    """Convert secret key bytes to base58 (simplified)"""
    # Simple encoding for display - not full base58
    import base64

    return base64.b64encode(bytes_key[:32]).decode("utf-8")[:44]


if __name__ == "__main__":
    # Create keystores directory
    keystore_dir = os.path.join(project_root, "keystores")
    os.makedirs(keystore_dir, exist_ok=True)

    passphrase = "test123"

    # Generate random keypairs (using nacl random)
    print("Generating mock wallet keystores...")
    print("(These are test wallets - DO NOT use with real SOL)")
    print()

    # Sniper wallet
    sniper_secret = nacl.utils.random(32)
    sniper_path = os.path.join(keystore_dir, "sniper.keystore")
    create_keystore(sniper_secret, passphrase, sniper_path)
    sniper_pub = bytes_to_base58(sniper_secret)
    print(f"1. Sniper Wallet: {sniper_pub}")

    # Main wallet
    main_secret = nacl.utils.random(32)
    main_path = os.path.join(keystore_dir, "main.keystore")
    create_keystore(main_secret, passphrase, main_path)
    main_pub = bytes_to_base58(main_secret)
    print(f"2. Main Wallet:   {main_pub}")

    print()
    print("=" * 50)
    print("Keystores created successfully!")
    print(f"Location: {keystore_dir}")
    print(f"Passphrase: {passphrase}")
    print("=" * 50)
