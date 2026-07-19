import os
from pathlib import Path

import pytest

from src.utils import credential_store
from src.utils.credential_store import CredentialStore


def test_linux_store_uses_user_only_permissions(tmp_path, monkeypatch):
    monkeypatch.setattr(credential_store.sys, "platform", "linux")
    store = CredentialStore(data_dir=tmp_path)
    token = "lma_abcdefghijklmnopqrstuvwxyz1234567890"

    store.save(token)

    assert store.load() == token
    if os.name != "nt":
        assert (tmp_path / "device-credential.dat").stat().st_mode & 0o777 == 0o600


def test_windows_store_never_writes_plain_token(tmp_path, monkeypatch):
    monkeypatch.setattr(credential_store.sys, "platform", "win32")
    monkeypatch.setattr(credential_store, "_windows_protect", lambda value: b"protected")
    monkeypatch.setattr(credential_store, "_windows_unprotect", lambda value: token.encode())
    store = CredentialStore(data_dir=tmp_path)
    token = "lma_abcdefghijklmnopqrstuvwxyz1234567890"

    store.save(token)

    assert token.encode() not in (tmp_path / "device-credential.dat").read_bytes()
    assert store.load() == token


def test_invalid_token_is_rejected(tmp_path):
    with pytest.raises(ValueError, match="Invalid device credential"):
        CredentialStore(data_dir=tmp_path).save("not-a-device-token")


def test_delete_removes_credential_file(tmp_path, monkeypatch):
    monkeypatch.setattr(credential_store.sys, "platform", "linux")
    path = Path(tmp_path) / "device-credential.dat"
    path.write_text("lma_abcdefghijklmnopqrstuvwxyz1234567890", encoding="utf-8")

    CredentialStore(data_dir=tmp_path).delete()

    assert not path.exists()
