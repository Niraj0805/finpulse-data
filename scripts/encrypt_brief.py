#!/usr/bin/env python3
"""Encrypt the FinPulse Desk morning brief so it can live in the public repo.

Usage:  FP_BRIEF_KEY=<base64 32-byte key> python3 scripts/encrypt_brief.py brief.json data/desk-brief.enc.json

The site (after its password unlock) holds the same key and decrypts the file in the
browser with AES-256-GCM. Only the ciphertext is ever committed.
"""
import base64, json, os, secrets, sys
from cryptography.hazmat.primitives.ciphers.aead import AESGCM

def main():
    if len(sys.argv) != 3:
        sys.exit(__doc__)
    key_b64 = os.environ.get("FP_BRIEF_KEY", "").strip()
    if not key_b64:
        sys.exit("FP_BRIEF_KEY is not set")
    key = base64.b64decode(key_b64)
    if len(key) != 32:
        sys.exit("FP_BRIEF_KEY must decode to 32 bytes")
    with open(sys.argv[1], encoding="utf-8") as f:
        brief = json.load(f)                      # validates the JSON
    plain = json.dumps(brief, ensure_ascii=False, separators=(",", ":")).encode()
    iv = secrets.token_bytes(12)
    ct = AESGCM(key).encrypt(iv, plain, None)     # ciphertext || 16-byte tag (WebCrypto format)
    out = {"v": 1, "alg": "AES-256-GCM", "date": brief.get("date"),
           "iv": base64.b64encode(iv).decode(), "ct": base64.b64encode(ct).decode()}
    with open(sys.argv[2], "w", encoding="utf-8") as f:
        json.dump(out, f)
    print(f"encrypted {len(plain)} bytes -> {sys.argv[2]} (date {out['date']})")

if __name__ == "__main__":
    main()
