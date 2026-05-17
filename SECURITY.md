# Security Policy

## Supported Versions

| Version | Supported          |
| ------- | ------------------ |
| 1.0.x   | Yes                |

## Reporting a Vulnerability

We take the security of MTUS seriously. If you believe you have found a security vulnerability, please report it to us as described below.

**Please do NOT report security vulnerabilities through public GitHub issues.**

### How to Report

1. **Email** the maintainers with a detailed description of the vulnerability
2. Include **steps to reproduce** the issue
3. Include the **potential impact** (what could an attacker do?)
4. If possible, include a **proof of concept**
5. We will acknowledge receipt within **48 hours**

### What to Expect

- **Within 48 hours**: Acknowledgment of your report
- **Within 7 days**: Initial assessment and severity classification
- **Within 30 days**: Fix deployed or mitigation plan communicated
- **After fix**: Public disclosure with credit (if you wish)

### Severity Classification

| Severity | Response Time | Examples |
|----------|---------------|----------|
| Critical | 24 hours | Private key exposure, fund theft vector |
| High | 7 days | Authentication bypass, data leak |
| Medium | 14 days | Rate limit bypass, DoS vector |
| Low | 30 days | Information disclosure, minor bypass |

---

## Security Architecture

### Wallet Key Protection

Wallet keys are **never stored in plaintext**. They are encrypted using:

- **Key Derivation**: Argon2id (OWF 2022 winner)
  - `time_cost`: 4 iterations
  - `memory_cost`: 65,536 KB (64 MB)
  - `parallelism`: 2 threads
  - `hash_length`: 32 bytes

- **Encryption**: XSalsa20-Poly1305 (authenticated encryption)
  - Provides confidentiality and integrity
  - Nonce is randomly generated per keystore

### What Is Secure

| Component | Protection |
|-----------|------------|
| Wallet keystores | Argon2id + XSalsa20-Poly1305 |
| Environment variables | `.env` excluded from git |
| Telegram commands | HMAC-SHA256 OTP verification |
| Redis communication | Localhost-only (not exposed) |
| Audit trail | PostgreSQL append-only ledger |

### What Requires Attention

| Concern | Mitigation |
|---------|------------|
| Passphrase strength | Use strong, unique passphrases for keystores |
| Redis exposure | Bind to localhost only; do not expose to network |
| `.env` file | Never commit; use `.env.example` as template |
| Keystore files | Never commit; store securely offline |
| Production mode | Thoroughly test in paper mode first |

---

## Best Practices for Operators

### Before Going Live

1. **Test extensively in paper mode** — Run at least 50+ simulated trades
2. **Verify all safety gates** — Confirm G1–G11 are functioning correctly
3. **Set conservative limits** — Start with small position sizes
4. **Monitor agent health** — Ensure HeraclesAgent is running and alerting
5. **Secure your environment** — Verify `.env` and keystores are not accessible

### Operational Security

1. **Never share** your `.env` file or keystore passphrases
2. **Rotate** Telegram OTP seeds periodically
3. **Monitor** the audit ledger for unexpected activity
4. **Use separate wallets** for testing and production
5. **Back up** your keystores securely (encrypted external storage)

### What NOT to Do

- **NEVER** commit `.env`, `.keystore`, or any file containing secrets
- **NEVER** run production mode without thorough paper mode testing
- **NEVER** expose Redis to the public internet
- **NEVER** share your Telegram OTP seed
- **NEVER** hardcode API keys or passphrases in source code

---

## Known Security Considerations

### Paper Mode vs Production

In paper mode, the safety gates G3–G9 are skipped. These include LP burn verification, holder concentration checks, and duplicate detection. **Always run in paper mode first** to verify the system works correctly, but understand that the safety pipeline is not fully active.

### RPC Provider Trust

The system relies on third-party RPC providers (Helius, QuickNode, Alchemy). A compromised RPC could return false data. The circuit breaker provides some protection against individual provider failures but does not verify data correctness.

### Telegram Bot Security

The Telegram bot requires OTP verification for destructive commands. However, the bot token itself is a sensitive credential stored in `.env`. If compromised, an attacker could attempt to brute-force OTPs (though the time window makes this difficult).

---

## Changelog

| Date | Change |
|------|--------|
| 2026-05-17 | Initial security policy |
