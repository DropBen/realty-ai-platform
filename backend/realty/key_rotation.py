"""Quiesced, transactional rotation of application-encrypted database values."""

import argparse
import json
import os

from cryptography.fernet import Fernet, InvalidToken, MultiFernet
from sqlalchemy import select, update
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from realty.config import settings
from realty.db import SessionLocal
from realty.models import AccountMail, Integration, User


def rotate_key(
    db: Session, old_key: str, new_key: str, *, apply: bool = False, quiesced: bool = False
) -> dict[str, int | str]:
    """Own the transaction so any corrupt value or racing writer rolls back all changes."""
    if db.in_transaction() or db.info.get("org_id"):
        raise ValueError("Rotation requires a fresh, unscoped maintenance session.")
    if apply and not quiesced:
        raise ValueError("Stop the API and worker before applying key rotation.")
    if old_key == new_key:
        raise ValueError("Provide distinct current and replacement keys.")
    try:
        replacement = Fernet(new_key.encode())
        ring = MultiFernet([replacement, Fernet(old_key.encode())])
    except (ValueError, UnicodeError):
        raise ValueError("Configure valid current and replacement Fernet keys.") from None
    changed, unchanged = 0, 0
    with db.begin():
        for model, identifier, field in [
            (User, User.id, User.mfa_ciphertext),
            (User, User.id, User.mfa_pending_ciphertext),
            (Integration, Integration.id, Integration.token_ciphertext),
            (AccountMail, AccountMail.id, AccountMail.body_ciphertext),
        ]:
            for record_id, ciphertext in db.execute(
                select(identifier, field).where(field.is_not(None)).execution_options(yield_per=250)
            ):
                token = ciphertext.encode()
                try:
                    replacement.decrypt(token)
                    unchanged += 1
                    continue
                except InvalidToken:
                    pass
                try:
                    rotated = ring.rotate(token).decode()
                except (InvalidToken, ValueError):
                    raise ValueError(
                        "A stored value cannot be decrypted; rotation was rolled back."
                    ) from None
                changed += 1
                if apply:
                    result = db.execute(
                        update(model)
                        .where(identifier == record_id, field == ciphertext)
                        .values({field.key: rotated})
                        .execution_options(synchronize_session=False)
                    )
                    if result.rowcount != 1:  # type: ignore[attr-defined]
                        raise ValueError(
                            "A writer changed data during maintenance; rotation was rolled back."
                        )
    return {
        "mode": "applied" if apply else "dry_run",
        "values_to_rotate": changed,
        "already_current": unchanged,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--apply", action="store_true")
    parser.add_argument(
        "--quiesced", action="store_true", help="Confirm all API/worker processes are stopped"
    )
    args = parser.parse_args()
    try:
        with SessionLocal() as db:
            result = rotate_key(
                db,
                settings.encryption_key,
                os.environ.get("ROTATION_NEW_KEY", ""),
                apply=args.apply,
                quiesced=args.quiesced,
            )
    except (ValueError, SQLAlchemyError):
        print(
            json.dumps(
                {
                    "error": "rotation_failed",
                    "message": "No changes committed. Check keys, database access, ciphertext integrity and maintenance preconditions.",
                }
            )
        )
        return 2
    print(json.dumps(result))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
