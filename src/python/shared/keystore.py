import json
import nacl.secret
import nacl.utils
import argon2
from pathlib import Path
from typing import Dict, Any

ARGON2_OPTIONS = {
    "time_cost": 4,
    "memory_cost": 65536,
    "parallelism": 2,
    "hash_len": 32,
    "type": argon2.Type.ID,
}


class Keystore:
    def __init__(self, keystore_path: str):
        self.keystore_path = Path(keystore_path)
        if not self.keystore_path.exists():
            raise FileNotFoundError(f"Keystore not found at {keystore_path}")

    def load_keypair(self, passphrase: str) -> bytes:
        with open(self.keystore_path, "r") as f:
            data: Dict[str, Any] = json.load(f)

        salt = bytes.fromhex(data["salt"])
        nonce = bytes.fromhex(data["nonce"])
        encrypted_secret = bytes.fromhex(data["encryptedSecretKey"])

        derived_key = argon2.low_level.hash_secret_raw(
            passphrase.encode("utf-8"), salt, **ARGON2_OPTIONS
        )

        box = nacl.secret.SecretBox(derived_key)
        return box.decrypt(encrypted_secret, nonce)

    @staticmethod
    def create_keystore(secret_key: bytes, passphrase: str, keystore_path: str) -> None:
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
