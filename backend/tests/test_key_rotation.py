import pytest
from cryptography.fernet import Fernet, InvalidToken
from realty.key_rotation import rotate_key
from realty.models import AccountMail, Integration, User
from sqlalchemy import select


@pytest.fixture
def encrypted_records(account, factory):
    old, new = Fernet.generate_key().decode(), Fernet.generate_key().decode()
    cipher = Fernet(old.encode())
    with factory() as db:
        user = db.get(User, account["user"]["id"])
        user.mfa_ciphertext = cipher.encrypt(b"active-authenticator").decode()
        user.mfa_pending_ciphertext = cipher.encrypt(b"pending-authenticator").decode()
        db.add(
            Integration(
                org_id=account["organization"]["id"],
                user_id=user.id,
                token_ciphertext=cipher.encrypt(b"google-token").decode(),
            )
        )
        db.add(
            AccountMail(
                user_id=user.id,
                purpose="verify",
                body_ciphertext=cipher.encrypt(b"verification-link").decode(),
            )
        )
        db.commit()
    return old, new


def ciphertexts(factory):
    with factory() as db:
        user = db.scalar(select(User))
        return [
            user.mfa_ciphertext,
            user.mfa_pending_ciphertext,
            db.scalar(select(Integration)).token_ciphertext,
            db.scalar(select(AccountMail)).body_ciphertext,
        ]


def test_rotation_dry_run_apply_and_repeat_preserve_values(factory, encrypted_records):
    old, new = encrypted_records
    before = ciphertexts(factory)
    with factory() as db:
        assert rotate_key(db, old, new)["values_to_rotate"] == 4
    assert ciphertexts(factory) == before
    with factory() as db:
        assert rotate_key(db, old, new, apply=True, quiesced=True)["values_to_rotate"] == 4
    for original, rotated in zip(before, ciphertexts(factory), strict=True):
        assert Fernet(new.encode()).decrypt(rotated.encode()) == Fernet(old.encode()).decrypt(
            original.encode()
        )
        assert Fernet(new.encode()).extract_timestamp(rotated.encode()) == Fernet(
            old.encode()
        ).extract_timestamp(original.encode())
        with pytest.raises(InvalidToken):
            Fernet(old.encode()).decrypt(rotated.encode())
    with factory() as db:
        assert rotate_key(db, old, new, apply=True, quiesced=True)["already_current"] == 4


def test_corrupt_ciphertext_rolls_back_preceding_rotations(factory, encrypted_records):
    old, new = encrypted_records
    with factory() as db:
        db.scalar(select(AccountMail)).body_ciphertext = "invalid-encrypted-record"
        db.commit()
    before = ciphertexts(factory)
    with factory() as db:
        with pytest.raises(ValueError, match="rolled back"):
            rotate_key(db, old, new, apply=True, quiesced=True)
        db.commit()  # Even a caller committing after the failure cannot preserve partial writes.
    assert ciphertexts(factory) == before


def test_rotation_requires_quiescence_and_a_global_transaction(factory, encrypted_records):
    old, new = encrypted_records
    with factory() as db:
        with pytest.raises(ValueError, match="Stop the API"):
            rotate_key(db, old, new, apply=True)
        db.info["org_id"] = "not-a-global-maintenance-session"
        with pytest.raises(ValueError, match="unscoped"):
            rotate_key(db, old, new)
