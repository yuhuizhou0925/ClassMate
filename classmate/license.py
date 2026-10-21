"""Authorization codes (offline, Ed25519 signatures).

* The master code is the owner's signing key ("CM-MASTER-..."). It never expires and is the only code that
  can issue new codes. It is not in this repository: only the matching public key is.
* An issued code ("CM-...") carries its expiry date signed with that key. The app checks the signature with
  PUBLIC_KEY, so nobody can forge a code or extend its date, and an issued code cannot issue others.
* The code that unlocked the app is remembered in license.txt next to the app (git-ignored) and checked again
  at every start.
"""
from __future__ import annotations

import base64
import json
import os
import struct
import time
from dataclasses import dataclass
from pathlib import Path

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey, Ed25519PublicKey

from . import config

PUBLIC_KEY = "VfE0on91pQVLH+skg+FWE2d9ifh77GfBw3n46pVGKQo="     # verifies codes; cannot create them
MASTER_PREFIX, CODE_PREFIX, VERSION = "CM-MASTER-", "CM-", 1
CLOCK_SLACK = 24 * 3600         # the system clock may go back this much before a code counts as tampered


@dataclass
class License:
    kind: str                   # "master" | "user"
    expires: float | None       # unix time; None = never
    code: str
    signer: Ed25519PrivateKey | None = None    # only the master code can sign new codes

    @property
    def can_issue(self) -> bool:
        return self.signer is not None

    def info(self) -> dict:
        return {"kind": self.kind, "expires": self.expires, "can_issue": self.can_issue}


def license_file() -> Path:
    return config.APP_DIR / "license.txt"


def _b32decode(text: str) -> bytes:
    return base64.b32decode(text + "=" * (-len(text) % 8))


def _public_key() -> Ed25519PublicKey:
    return Ed25519PublicKey.from_public_bytes(base64.b64decode(PUBLIC_KEY))


def _raw_public(key) -> bytes:
    return key.public_bytes(serialization.Encoding.Raw, serialization.PublicFormat.Raw)


def parse(code: str, now: float | None = None) -> License:
    """Check a code; raises ValueError with a message for the user."""
    now = time.time() if now is None else now
    code = "".join((code or "").split()).upper()
    if code.startswith(MASTER_PREFIX):
        try:
            signer = Ed25519PrivateKey.from_private_bytes(_b32decode(code[len(MASTER_PREFIX):]))
        except Exception:
            raise ValueError("授权码无效") from None
        if _raw_public(signer.public_key()) != base64.b64decode(PUBLIC_KEY):
            raise ValueError("授权码无效")
        return License("master", None, code, signer)
    if not code.startswith(CODE_PREFIX):
        raise ValueError("授权码格式不对：应以 CM- 开头")
    try:
        raw = _b32decode(code[len(CODE_PREFIX):].replace("-", ""))
        payload, signature = raw[:13], raw[13:]
        version, issued, expires, _nonce = struct.unpack(">BIII", payload)
        _public_key().verify(signature, payload)
    except (InvalidSignature, ValueError, struct.error, base64.binascii.Error):
        raise ValueError("授权码无效") from None
    if version != VERSION:
        raise ValueError("授权码版本不支持，请更新软件")
    if now > expires:
        raise ValueError(f"授权码已于 {time.strftime('%Y-%m-%d %H:%M', time.localtime(expires))} 过期")
    return License("user", float(expires), code)


def issue(master: License, days: float, now: float | None = None) -> str:
    """A new code valid for `days` days (master code only)."""
    if not master.can_issue:
        raise PermissionError("只有主授权码可以生成授权码")
    if not 0 < days <= 3650:
        raise ValueError("有效期要在 1 分钟到 10 年之间")
    now = time.time() if now is None else now
    payload = struct.pack(">BIII", VERSION, int(now), int(now + days * 86400), int.from_bytes(os.urandom(4), "big"))
    body = base64.b32encode(payload + master.signer.sign(payload)).decode().rstrip("=")
    return CODE_PREFIX + "-".join(body[i:i + 6] for i in range(0, len(body), 6))


def load(now: float | None = None) -> License | None:
    """The remembered code, if it is still valid."""
    now = time.time() if now is None else now
    try:
        data = json.loads(license_file().read_text(encoding="utf-8"))
        lic = parse(data["code"], now)
    except Exception:
        return None
    if lic.kind == "user" and now < float(data.get("last_seen", 0)) - CLOCK_SLACK:
        return None                     # clock turned back to stretch an expiring code
    _write(lic.code, max(now, float(data.get("last_seen", 0))))
    return lic


def save(lic: License):
    _write(lic.code, time.time())


def forget():
    license_file().unlink(missing_ok=True)


def _write(code: str, last_seen: float):
    path = license_file()
    path.write_text(json.dumps({"code": code, "last_seen": last_seen}), encoding="utf-8")
    path.chmod(0o600)
