"""Credential storage for FedoRT.

Provides :class:`CredentialStore` for saving and retrieving connection
credentials (hostnames, usernames, passwords, key passphrases) –
mirroring SecureCRT's credential-management feature.

.. warning::

    This module uses **basic obfuscation** (Base64 + XOR with a
    machine-specific key), **not** true encryption.  It is designed to
    prevent casual shoulder-surfing, not to withstand a determined
    attacker with file-system access.  For production environments
    consider integrating a system keyring (e.g. GNOME Keyring, KWallet,
    or ``libsecret``).
"""

from __future__ import annotations

import base64
import hashlib
import json
import logging
import os
import platform
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

# ── XDG helpers ──────────────────────────────────────────────────────

_APP_NAME = "fedort"
_CRED_FILE = "credentials.json"


def _default_cred_dir() -> Path:
    """Return the default credential storage directory."""
    return Path(
        os.environ.get("XDG_CONFIG_HOME", Path.home() / ".config"),
    ) / _APP_NAME


# ── Obfuscation helpers ─────────────────────────────────────────────


def _machine_key() -> bytes:
    """Derive a repeatable, machine-specific key.

    Combines the hostname and the OS platform identifier into a
    SHA-256 digest.  This is **not** cryptographically secure – it
    merely adds a per-machine salt so that the stored file is not
    trivially portable.
    """
    raw = f"{platform.node()}-{platform.platform()}".encode()
    return hashlib.sha256(raw).digest()


def _xor_bytes(data: bytes, key: bytes) -> bytes:
    """XOR *data* against *key* (repeating the key as needed)."""
    key_len = len(key)
    return bytes(b ^ key[i % key_len] for i, b in enumerate(data))


def _obfuscate(plaintext: str) -> str:
    """Obfuscate *plaintext* with XOR + Base64.

    .. warning:: This is **not** encryption.
    """
    if not plaintext:
        return ""
    xored = _xor_bytes(plaintext.encode("utf-8"), _machine_key())
    return base64.b64encode(xored).decode("ascii")


def _deobfuscate(token: str) -> str:
    """Reverse :func:`_obfuscate`.

    .. warning:: This is **not** decryption.
    """
    if not token:
        return ""
    xored = base64.b64decode(token.encode("ascii"))
    return _xor_bytes(xored, _machine_key()).decode("utf-8")


# ── Dataclass ────────────────────────────────────────────────────────


@dataclass
class Credential:
    """A single set of connection credentials.

    Attributes
    ----------
    hostname:
        Target host (IP or FQDN).
    port:
        Port number (default 22 for SSH).
    username:
        Login user name.
    password:
        Password (stored obfuscated on disk).
    key_passphrase:
        SSH-key passphrase (stored obfuscated on disk).
    description:
        Free-form note.
    """

    hostname: str
    port: int = 22
    username: str = ""
    password: str = ""
    key_passphrase: str = ""
    description: str = ""


# ── Store ────────────────────────────────────────────────────────────


class CredentialStore:
    """Persist and retrieve connection credentials.

    Credentials are stored as JSON in
    ``~/.config/fedort/credentials.json``.  Sensitive fields
    (password, key_passphrase) are obfuscated with XOR + Base64 using a
    machine-specific key.

    .. warning::

        The obfuscation is **not** true encryption.  See the module
        docstring for details.
    """

    def __init__(self, cred_dir: Optional[Path] = None) -> None:
        self._dir: Path = cred_dir or _default_cred_dir()
        self._path: Path = self._dir / _CRED_FILE
        self._credentials: list[Credential] = []
        self._master_hash: str = ""

    # ── Persistence ──────────────────────────────────────────────

    def load(self) -> None:
        """Load credentials from disk.

        Silently starts with an empty list when the file is missing or
        corrupt.
        """
        if not self._path.is_file():
            self._credentials = []
            return

        try:
            raw = json.loads(self._path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            logger.warning("Corrupted credential file – starting empty.")
            self._credentials = []
            return

        self._master_hash = raw.get("master_hash", "")
        entries = raw.get("credentials", [])
        self._credentials = []
        for entry in entries:
            cred = Credential(
                hostname=entry.get("hostname", ""),
                port=entry.get("port", 22),
                username=entry.get("username", ""),
                password=_deobfuscate(entry.get("password", "")),
                key_passphrase=_deobfuscate(entry.get("key_passphrase", "")),
                description=entry.get("description", ""),
            )
            self._credentials.append(cred)
        logger.info("Loaded %d credentials from %s", len(self._credentials), self._path)

    def save(self) -> None:
        """Write all credentials to disk (obfuscating sensitive fields)."""
        self._dir.mkdir(parents=True, exist_ok=True)
        entries = []
        for cred in self._credentials:
            d = asdict(cred)
            d["password"] = _obfuscate(cred.password)
            d["key_passphrase"] = _obfuscate(cred.key_passphrase)
            entries.append(d)

        payload = {
            "master_hash": self._master_hash,
            "credentials": entries,
        }
        self._path.write_text(
            json.dumps(payload, indent=2) + "\n",
            encoding="utf-8",
        )
        logger.info("Saved %d credentials to %s", len(entries), self._path)

    # ── CRUD ─────────────────────────────────────────────────────

    def add_credential(self, credential: Credential) -> None:
        """Add a credential.  Duplicates are allowed."""
        self._credentials.append(credential)

    def get_credential(
        self,
        hostname: str,
        username: Optional[str] = None,
    ) -> Optional[Credential]:
        """Look up a credential by *hostname* and optional *username*.

        Returns *None* when no match is found.
        """
        for cred in self._credentials:
            if cred.hostname == hostname:
                if username is None or cred.username == username:
                    return cred
        return None

    def update_credential(self, credential: Credential) -> None:
        """Update an existing credential matched by hostname + username.

        If no match is found the credential is appended instead.
        """
        for i, existing in enumerate(self._credentials):
            if (
                existing.hostname == credential.hostname
                and existing.username == credential.username
            ):
                self._credentials[i] = credential
                return
        self._credentials.append(credential)

    def delete_credential(
        self,
        hostname: str,
        username: Optional[str] = None,
    ) -> bool:
        """Delete the first credential matching *hostname* (and *username*).

        Returns *True* if a credential was removed.
        """
        for i, cred in enumerate(self._credentials):
            if cred.hostname == hostname:
                if username is None or cred.username == username:
                    del self._credentials[i]
                    return True
        return False

    def list_credentials(self) -> list[Credential]:
        """Return a copy of all stored credentials."""
        return list(self._credentials)

    def clear_all(self) -> None:
        """Remove every credential from the in-memory store."""
        self._credentials.clear()

    # ── Master password ──────────────────────────────────────────

    def set_master_password(self, password: str) -> None:
        """Set (or change) the optional master password.

        The password itself is not stored – only a SHA-256 hash is kept
        so that :meth:`verify_master_password` can validate it.
        """
        self._master_hash = hashlib.sha256(password.encode("utf-8")).hexdigest()
        logger.info("Master password set.")

    def verify_master_password(self, password: str) -> bool:
        """Return *True* if *password* matches the stored master hash.

        Always returns *True* when no master password has been set.
        """
        if not self._master_hash:
            return True
        return hashlib.sha256(password.encode("utf-8")).hexdigest() == self._master_hash

    # ── Import / export ──────────────────────────────────────────

    def export_credentials(self, filepath: str, password: str) -> None:
        """Export all credentials to an obfuscated JSON file.

        The *password* is used as the XOR key instead of the machine
        key, making the export portable across machines.

        Parameters
        ----------
        filepath:
            Destination file path.
        password:
            Password to obfuscate the export with.
        """
        key = hashlib.sha256(password.encode("utf-8")).digest()
        entries = []
        for cred in self._credentials:
            d = asdict(cred)
            d["password"] = base64.b64encode(
                _xor_bytes(cred.password.encode("utf-8"), key),
            ).decode("ascii") if cred.password else ""
            d["key_passphrase"] = base64.b64encode(
                _xor_bytes(cred.key_passphrase.encode("utf-8"), key),
            ).decode("ascii") if cred.key_passphrase else ""
            entries.append(d)

        Path(filepath).write_text(
            json.dumps({"credentials": entries}, indent=2) + "\n",
            encoding="utf-8",
        )
        logger.info("Exported %d credentials to %s", len(entries), filepath)

    def import_credentials(self, filepath: str, password: str) -> None:
        """Import credentials from a file created by :meth:`export_credentials`.

        Parameters
        ----------
        filepath:
            Source file path.
        password:
            Password that was used during export.
        """
        data = json.loads(Path(filepath).read_text(encoding="utf-8"))
        key = hashlib.sha256(password.encode("utf-8")).digest()
        entries = data.get("credentials", [])

        for entry in entries:
            pw_token = entry.get("password", "")
            kp_token = entry.get("key_passphrase", "")
            cred = Credential(
                hostname=entry.get("hostname", ""),
                port=entry.get("port", 22),
                username=entry.get("username", ""),
                password=_xor_bytes(
                    base64.b64decode(pw_token.encode("ascii")), key,
                ).decode("utf-8") if pw_token else "",
                key_passphrase=_xor_bytes(
                    base64.b64decode(kp_token.encode("ascii")), key,
                ).decode("utf-8") if kp_token else "",
                description=entry.get("description", ""),
            )
            self._credentials.append(cred)

        logger.info("Imported %d credentials from %s", len(entries), filepath)
