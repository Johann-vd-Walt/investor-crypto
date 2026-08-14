"""One-time TOTP enrollment for the app's login gate.

Run once, in your own terminal:

    cd backend
    .\\.venv\\Scripts\\python.exe -m app.auth_setup

It generates a secret, prints a QR code + the manual key for Google
Authenticator, and writes ``TOTP_SECRET`` into ``backend/.env`` so login turns
on next time the backend starts. Run with ``--reset`` to replace an existing
secret. Keep the secret private — anyone with it can log in.
"""

from __future__ import annotations

import io
import sys
from pathlib import Path

import pyotp
import qrcode

from app.config import get_settings

_ENV_PATH = Path(__file__).resolve().parent.parent / ".env"


def _write_env_secret(secret: str) -> None:
    """Set/replace TOTP_SECRET in backend/.env (create the file if missing)."""
    lines: list[str] = []
    if _ENV_PATH.exists():
        lines = _ENV_PATH.read_text(encoding="utf-8").splitlines()
    out, found = [], False
    for line in lines:
        if line.strip().startswith("TOTP_SECRET="):
            out.append(f"TOTP_SECRET={secret}")
            found = True
        else:
            out.append(line)
    if not found:
        out.append(f"TOTP_SECRET={secret}")
    _ENV_PATH.write_text("\n".join(out) + "\n", encoding="utf-8")


def _ascii_qr(uri: str) -> str:
    qr = qrcode.QRCode(border=1)
    qr.add_data(uri)
    qr.make(fit=True)
    buf = io.StringIO()
    qr.print_ascii(out=buf, invert=True)
    return buf.getvalue()


def main() -> None:
    settings = get_settings()
    reset = "--reset" in sys.argv
    if settings.totp_secret and not reset:
        print("TOTP_SECRET is already set. Re-run with --reset to replace it.")
        return

    secret = pyotp.random_base32()
    uri = pyotp.TOTP(secret).provisioning_uri(
        name=settings.totp_account, issuer_name=settings.totp_issuer
    )
    _write_env_secret(secret)

    print("\n=== Crypto Swing-Trader — TOTP login enrolment ===\n")
    print("1) Open Google Authenticator -> + -> Scan a QR code, and scan this:\n")
    print(_ascii_qr(uri))
    print("   ...or choose 'Enter a setup key' and type this secret:\n")
    print(f"       {secret}\n")
    print("   (account: %s, issuer: %s)\n" % (settings.totp_account, settings.totp_issuer))
    print("2) The secret was written to backend/.env (TOTP_SECRET).")
    print("3) Restart the backend. Login is now required — enter the 6-digit code.\n")
    print("Keep this secret private. To turn login OFF, blank TOTP_SECRET in .env.\n")


if __name__ == "__main__":
    main()
