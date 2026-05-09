import * as argon2 from 'argon2';
import * as nacl from 'tweetnacl';
import { readFileSync, writeFileSync } from 'fs';
import { resolve } from 'path';
import { Keypair } from '@solana/web3.js';

const ARGON2_OPTIONS = {
  type: argon2.argon2id,
  timeCost: 4,
  memoryCost: 65536,
  parallelism: 2,
  hashLength: 32,
  raw: true, // Get raw bytes instead of formatted string
};

export interface KeystoreData {
  salt: string;
  nonce: string;
  encryptedSecretKey: string;
  kdfParams: {
    timeCost: number;
    memoryCost: number;
    parallelism: number;
  };
}

export const createKeystore = async (
  secretKey: Uint8Array,
  passphrase: string,
  keystorePath: string
): Promise<void> => {
  const salt = Buffer.from(nacl.randomBytes(16));
  const derivedKey = await argon2.hash(passphrase, { ...ARGON2_OPTIONS, salt });
  // derivedKey is already a Buffer, use it directly
  const key = Buffer.from(derivedKey);
  const nonce = nacl.randomBytes(nacl.secretbox.nonceLength);
  const encrypted = nacl.secretbox(secretKey, nonce, key);

  const keystoreData: KeystoreData = {
    salt: Buffer.from(salt).toString('hex'),
    nonce: Buffer.from(nonce).toString('hex'),
    encryptedSecretKey: Buffer.from(encrypted).toString('hex'),
    kdfParams: {
      timeCost: ARGON2_OPTIONS.timeCost,
      memoryCost: ARGON2_OPTIONS.memoryCost,
      parallelism: ARGON2_OPTIONS.parallelism,
    },
  };

  writeFileSync(keystorePath, JSON.stringify(keystoreData, null, 2), { mode: 0o600 });
};

export const loadKeypairFromKeystore = async (
  keystorePath: string,
  passphrase: string
): Promise<Keypair> => {
  const keystoreData: KeystoreData = JSON.parse(readFileSync(keystorePath, 'utf-8'));
  const salt = Buffer.from(keystoreData.salt, 'hex');
  const derivedKey = await argon2.hash(passphrase, { ...ARGON2_OPTIONS, salt });
  const key = Buffer.from(derivedKey); // Already a Buffer
  const nonce = Buffer.from(keystoreData.nonce, 'hex');
  const encrypted = Buffer.from(keystoreData.encryptedSecretKey, 'hex');

  const secretKey = nacl.secretbox.open(encrypted, nonce, key);
  if (!secretKey) throw new Error('Invalid passphrase or corrupted keystore');

  // FIX: Create a hard copy of the secret key bytes before passing to Keypair
  // This breaks the memory reference so fill(0) won't destroy the Keypair's secret
  const secretKeyCopy = new Uint8Array(secretKey);
  const keypair = Keypair.fromSecretKey(secretKeyCopy);
  
  // Now it is safe to clear the original decrypted buffer
  secretKey.fill(0);
  return keypair;
};
