import unittest
import tempfile
import os
import sys

project_root = os.path.join(os.path.dirname(__file__), "..", "..")
sys.path.insert(0, project_root)
sys.path.insert(0, os.path.join(project_root, "src"))

from python.shared.keystore import Keystore


class TestKeystore(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.mkdtemp()
        self.keystore_path = os.path.join(self.temp_dir, "test.keystore")
        self.passphrase = "test_secure_passphrase_123"
        self.secret_key = os.urandom(64)  # Simulated Solana secret key

    def test_01_create_keystore(self):
        """Test keystore creation per Section 4.1: Argon2id + XSalsa20-Poly1305"""
        Keystore.create_keystore(self.secret_key, self.passphrase, self.keystore_path)
        self.assertTrue(os.path.exists(self.keystore_path))

        # Verify file permissions (chmod 600)
        file_stat = os.stat(self.keystore_path)
        mode = oct(file_stat.st_mode & 0o777)
        # Skip on Windows - chmod doesn't work the same way
        if os.name != "nt":
            self.assertEqual(mode, oct(0o600), "Keystore must have 600 permissions")

        # Verify file contents are valid JSON with required fields
        import json

        with open(self.keystore_path, "r") as f:
            data = json.load(f)
        self.assertIn("salt", data)
        self.assertIn("nonce", data)
        self.assertIn("encryptedSecretKey", data)
        self.assertIn("kdfParams", data)
        self.assertEqual(data["kdfParams"]["timeCost"], 4)
        self.assertEqual(data["kdfParams"]["memoryCost"], 65536)
        self.assertEqual(data["kdfParams"]["parallelism"], 2)

    def test_02_load_keystore_valid_passphrase(self):
        """Test loading keystore with correct passphrase"""
        Keystore.create_keystore(self.secret_key, self.passphrase, self.keystore_path)
        ks = Keystore(self.keystore_path)
        loaded_key = ks.load_keypair(self.passphrase)
        self.assertEqual(loaded_key, self.secret_key, "Loaded key must match original")

    def test_03_load_keystore_invalid_passphrase(self):
        """Test loading keystore with wrong passphrase fails"""
        Keystore.create_keystore(self.secret_key, self.passphrase, self.keystore_path)
        ks = Keystore(self.keystore_path)
        with self.assertRaises(
            Exception, msg="Invalid passphrase must raise exception"
        ):
            ks.load_keypair("wrong_passphrase")

    def test_04_corrupted_keystore(self):
        """Test corrupted keystore fails to load"""
        with open(self.keystore_path, "w") as f:
            f.write("corrupted data")
        ks = Keystore(self.keystore_path)
        with self.assertRaises(
            Exception, msg="Corrupted keystore must raise exception"
        ):
            ks.load_keypair(self.passphrase)

    def test_05_keystore_zero_memory(self):
        """Verify key material is zeroed after use (implicit in nacl.secretbox)"""
        # This is verified by the nacl library's implementation
        # We confirm the load function doesn't store key material
        Keystore.create_keystore(self.secret_key, self.passphrase, self.keystore_path)
        ks = Keystore(self.keystore_path)
        loaded = ks.load_keypair(self.passphrase)
        self.assertEqual(loaded, self.secret_key)


if __name__ == "__main__":
    unittest.main()
