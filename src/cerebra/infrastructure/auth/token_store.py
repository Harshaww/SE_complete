"""Token storage backends (FR-5.2, NFR-SE-2, NFR-SE-3, ADR-D §3).

Preference order:
  1. OS keyring (``keyring``)               - KeyringTokenStore
  2. Owner-only file (mode 0o600)           - FileTokenStore
  3. In-memory                              - InMemoryTokenStore (tests only)

Tokens are NEVER written to source, fixtures, logs or the SQLite database.
"""

from __future__ import annotations

import contextlib
import json
import os
import stat
import sys
import tempfile
from pathlib import Path

from cerebra.ports.interfaces import TokenStore

KEYRING_SERVICE = "cerebra"
KEYRING_USERNAME = "youtube-oauth-token"


class InMemoryTokenStore:
    """Non-persistent store for tests and the fixture adapter."""

    def __init__(self) -> None:
        self._data: dict[str, object] | None = None

    def save_token(self, token_data: dict[str, object]) -> None:
        self._data = json.loads(json.dumps(token_data))

    def load_token(self) -> dict[str, object] | None:
        return None if self._data is None else json.loads(json.dumps(self._data))

    def delete_token(self) -> None:
        self._data = None

    @property
    def backend_name(self) -> str:
        return "memory"


class FileTokenStore:
    """Owner-only JSON file (``0o600``) inside an owner-only directory (``0o700``).

    Writes are atomic (temp file created 0o600 → ``os.replace``) so the token is never
    readable by other users, even briefly.
    """

    def __init__(self, path: Path) -> None:
        self._path = path

    @property
    def path(self) -> Path:
        return self._path

    @property
    def backend_name(self) -> str:
        return f"file:{self._path}"

    def save_token(self, token_data: dict[str, object]) -> None:
        self._path.parent.mkdir(parents=True, exist_ok=True)
        with contextlib.suppress(OSError):  # best effort on non-POSIX filesystems
            os.chmod(self._path.parent, 0o700)
        fd, tmp = tempfile.mkstemp(dir=str(self._path.parent), prefix=".token-", suffix=".tmp")
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as fh:
                json.dump(token_data, fh)
            os.chmod(tmp, 0o600)
            os.replace(tmp, self._path)
        except BaseException:
            with contextlib.suppress(OSError):
                os.unlink(tmp)
            raise

    def load_token(self) -> dict[str, object] | None:
        if not self._path.exists():
            return None
        mode = stat.S_IMODE(self._path.stat().st_mode)
        if mode & 0o077:
            # Someone loosened the permissions: tighten before reading, tell the human.
            os.chmod(self._path, 0o600)
            sys.stderr.write(
                f"cerebra: tightened permissions on {self._path} to 0600 "
                "(it was readable by other users).\n"
            )
        try:
            data = json.loads(self._path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return None
        return data if isinstance(data, dict) else None

    def delete_token(self) -> None:
        with contextlib.suppress(FileNotFoundError):
            self._path.unlink()


class KeyringTokenStore:
    """OS keyring backed store (macOS Keychain, Windows Credential Locker, Secret Service)."""

    def __init__(
        self,
        service: str = KEYRING_SERVICE,
        username: str = KEYRING_USERNAME,
        keyring_module: object | None = None,
    ) -> None:
        if keyring_module is None:
            import keyring as keyring_module  # type: ignore[no-redef]
        self._kr = keyring_module
        self._service = service
        self._username = username

    @property
    def backend_name(self) -> str:
        return "keyring"

    def save_token(self, token_data: dict[str, object]) -> None:
        self._kr.set_password(self._service, self._username, json.dumps(token_data))  # type: ignore[attr-defined]

    def load_token(self) -> dict[str, object] | None:
        raw = self._kr.get_password(self._service, self._username)  # type: ignore[attr-defined]
        if not raw:
            return None
        try:
            data = json.loads(raw)
        except ValueError:
            return None
        return data if isinstance(data, dict) else None

    def delete_token(self) -> None:
        try:
            self._kr.delete_password(self._service, self._username)  # type: ignore[attr-defined]
        except Exception:
            return


class FallbackTokenStore:
    """Use ``primary`` (keyring); if it errors at runtime, transparently use ``fallback`` (file)."""

    def __init__(self, primary: TokenStore, fallback: TokenStore) -> None:
        self._primary = primary
        self._fallback = fallback
        self._active: TokenStore = primary

    @property
    def backend_name(self) -> str:
        return getattr(self._active, "backend_name", "unknown")

    def save_token(self, token_data: dict[str, object]) -> None:
        try:
            self._primary.save_token(token_data)
            self._active = self._primary
            self._fallback.delete_token()  # never leave a stale second copy around
        except Exception:
            self._fallback.save_token(token_data)
            self._active = self._fallback

    def load_token(self) -> dict[str, object] | None:
        try:
            data = self._primary.load_token()
            if data is not None:
                self._active = self._primary
                return data
        except Exception:  # noqa: S110 - keyring unavailable: fall through to the file store
            pass
        data = self._fallback.load_token()
        if data is not None:
            self._active = self._fallback
        return data

    def delete_token(self) -> None:
        for store in (self._primary, self._fallback):
            try:
                store.delete_token()
            except Exception:  # noqa: S112 - best-effort cleanup of both stores
                continue


def keyring_available() -> bool:
    """True if a real (non-null, non-fail) keyring backend is installed."""
    try:
        import keyring
        from keyring.backends import fail

        backend = keyring.get_keyring()
        if isinstance(backend, fail.Keyring):
            return False
        return getattr(backend, "priority", 1) > 0
    except Exception:
        return False


def build_token_store(token_file: Path, use_keyring: bool = True) -> TokenStore:
    """Select the storage backend per ADR-D §3 (keyring → owner-only file)."""
    file_store = FileTokenStore(token_file)
    if use_keyring and keyring_available():
        return FallbackTokenStore(KeyringTokenStore(), file_store)
    return file_store
