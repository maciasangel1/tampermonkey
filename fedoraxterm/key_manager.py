"""SSH key management for FedoraXTerm.

Provides :class:`KeyManager` for generating, inspecting, converting, and
managing SSH keys – mirroring the key-management features found in
SecureCRT.  Operations delegate to ``ssh-keygen`` and ``ssh-add`` via
subprocess so that key material is handled by OpenSSH itself.
"""

from __future__ import annotations

import logging
import os
import subprocess
from dataclasses import dataclass
from typing import Optional

logger = logging.getLogger(__name__)

# ── Supported key parameters ────────────────────────────────────────

_VALID_KEY_TYPES: dict[str, list[int]] = {
    "rsa": [2048, 4096],
    "ed25519": [256],
    "ecdsa": [256, 384, 521],
    "dsa": [1024],
}


# ── Dataclass ────────────────────────────────────────────────────────


@dataclass
class SSHKeyInfo:
    """Metadata describing a single SSH key pair.

    Attributes
    ----------
    path:
        Absolute path to the private key file.
    key_type:
        Algorithm identifier (``rsa``, ``ed25519``, ``ecdsa``, ``dsa``).
    bits:
        Key length in bits.
    fingerprint:
        Key fingerprint as reported by ``ssh-keygen -l``.
    comment:
        Embedded key comment.
    has_passphrase:
        Whether the private key is passphrase-protected.
    public_key_path:
        Path to the corresponding ``.pub`` file.
    """

    path: str
    key_type: str
    bits: int
    fingerprint: str
    comment: str
    has_passphrase: bool
    public_key_path: str


# ── Manager ──────────────────────────────────────────────────────────


class KeyManager:
    """Generate, inspect, and manage SSH keys.

    Parameters
    ----------
    default_key_dir:
        Directory that is scanned by default when listing keys.
        Falls back to ``~/.ssh/``.
    """

    def __init__(self, default_key_dir: Optional[str] = None) -> None:
        self.default_key_dir: str = default_key_dir or os.path.expanduser(
            "~/.ssh",
        )

    # ── Key generation ───────────────────────────────────────────

    def generate_key(
        self,
        key_type: str = "ed25519",
        bits: int = 0,
        comment: str = "",
        passphrase: str = "",
        filepath: Optional[str] = None,
    ) -> SSHKeyInfo:
        """Generate a new SSH key pair.

        Parameters
        ----------
        key_type:
            Algorithm – one of ``rsa``, ``ed25519``, ``ecdsa``, ``dsa``.
        bits:
            Key length.  Ignored for ``ed25519``; required for ``rsa``
            and ``ecdsa``.
        comment:
            Key comment embedded in the public key file.
        passphrase:
            Passphrase to protect the private key.  An empty string
            means *no passphrase*.
        filepath:
            Destination path for the private key.  When *None* a
            sensible default inside :attr:`default_key_dir` is chosen.

        Returns
        -------
        SSHKeyInfo
            Metadata for the newly-created key.

        Raises
        ------
        ValueError
            If *key_type* or *bits* is not supported.
        RuntimeError
            If ``ssh-keygen`` exits with a non-zero status.
        """
        key_type = key_type.lower()
        if key_type not in _VALID_KEY_TYPES:
            raise ValueError(
                f"Unsupported key type {key_type!r}. "
                f"Choose from {list(_VALID_KEY_TYPES)}."
            )

        if key_type != "ed25519" and bits and bits not in _VALID_KEY_TYPES[key_type]:
            raise ValueError(
                f"Invalid bit size {bits} for {key_type}. "
                f"Allowed: {_VALID_KEY_TYPES[key_type]}."
            )

        if filepath is None:
            os.makedirs(self.default_key_dir, mode=0o700, exist_ok=True)
            filepath = os.path.join(self.default_key_dir, f"id_{key_type}")

        cmd: list[str] = [
            "ssh-keygen",
            "-t", key_type,
            "-f", filepath,
            "-N", passphrase,
            "-q",
        ]
        if comment:
            cmd.extend(["-C", comment])
        if bits and key_type != "ed25519":
            cmd.extend(["-b", str(bits)])

        logger.info("Generating %s key at %s", key_type, filepath)
        result = subprocess.run(cmd, capture_output=True, text=True, check=False)
        if result.returncode != 0:
            raise RuntimeError(
                f"ssh-keygen failed (rc={result.returncode}): {result.stderr.strip()}"
            )

        return self.get_key_info(filepath)

    # ── Key inspection ───────────────────────────────────────────

    def get_key_info(self, filepath: str) -> SSHKeyInfo:
        """Return metadata for an existing key file.

        Parameters
        ----------
        filepath:
            Path to the private key.

        Raises
        ------
        FileNotFoundError
            If *filepath* does not exist.
        RuntimeError
            If ``ssh-keygen -l`` fails.
        """
        if not os.path.isfile(filepath):
            raise FileNotFoundError(f"Key file not found: {filepath}")

        pub_path = filepath + ".pub"

        # Fingerprint / bits / type via ssh-keygen -l
        result = subprocess.run(
            ["ssh-keygen", "-l", "-f", filepath],
            capture_output=True,
            text=True,
            check=False,
        )
        if result.returncode != 0:
            raise RuntimeError(
                f"ssh-keygen -l failed: {result.stderr.strip()}"
            )

        parts = result.stdout.strip().split()
        bits = int(parts[0]) if parts else 0
        fingerprint = parts[1] if len(parts) > 1 else ""
        comment = parts[2] if len(parts) > 2 else ""
        raw_type = parts[-1].strip("()") if parts else ""
        key_type = raw_type.lower()

        # Detect passphrase by attempting a no-op with empty passphrase.
        has_passphrase = self._check_has_passphrase(filepath)

        return SSHKeyInfo(
            path=os.path.abspath(filepath),
            key_type=key_type,
            bits=bits,
            fingerprint=fingerprint,
            comment=comment,
            has_passphrase=has_passphrase,
            public_key_path=os.path.abspath(pub_path) if os.path.isfile(pub_path) else "",
        )

    def _check_has_passphrase(self, filepath: str) -> bool:
        """Return *True* if the private key is passphrase-protected."""
        result = subprocess.run(
            ["ssh-keygen", "-y", "-f", filepath, "-P", ""],
            capture_output=True,
            text=True,
            check=False,
        )
        return result.returncode != 0

    def list_keys(self, directory: Optional[str] = None) -> list[SSHKeyInfo]:
        """Scan *directory* for SSH key files and return their metadata.

        Parameters
        ----------
        directory:
            Directory to scan.  Defaults to :attr:`default_key_dir`.
        """
        target = directory or self.default_key_dir
        if not os.path.isdir(target):
            logger.warning("Key directory does not exist: %s", target)
            return []

        keys: list[SSHKeyInfo] = []
        for name in sorted(os.listdir(target)):
            path = os.path.join(target, name)
            if not os.path.isfile(path):
                continue
            # Skip .pub files and known non-key files.
            if name.endswith(".pub") or name in {"authorized_keys", "known_hosts", "config"}:
                continue
            try:
                keys.append(self.get_key_info(path))
            except (RuntimeError, FileNotFoundError):
                logger.debug("Skipping non-key file: %s", path)
        return keys

    # ── Key conversion ───────────────────────────────────────────

    def convert_key(
        self,
        filepath: str,
        output_format: str,
        output_path: Optional[str] = None,
    ) -> str:
        """Convert a key between formats.

        Parameters
        ----------
        filepath:
            Path to the source key.
        output_format:
            Target format – ``openssh``, ``pem``, or ``pkcs8``.
        output_path:
            Destination file.  When *None* the conversion is written
            back to *filepath* (in-place).

        Returns
        -------
        str
            The path to the converted key file.

        Raises
        ------
        ValueError
            If *output_format* is unrecognised.
        RuntimeError
            If ``ssh-keygen`` exits with a non-zero status.
        """
        fmt_map = {
            "openssh": "RFC4716",
            "pem": "PEM",
            "pkcs8": "PKCS8",
        }
        fmt_flag = fmt_map.get(output_format.lower())
        if fmt_flag is None:
            raise ValueError(
                f"Unsupported format {output_format!r}. "
                f"Choose from {list(fmt_map)}."
            )

        dest = output_path or filepath
        cmd = ["ssh-keygen", "-p", "-m", fmt_flag, "-f", filepath, "-N", "", "-P", ""]
        if output_path:
            # Copy first so we don't mutate the original.
            import shutil
            shutil.copy2(filepath, dest)
            cmd = ["ssh-keygen", "-p", "-m", fmt_flag, "-f", dest, "-N", "", "-P", ""]

        result = subprocess.run(cmd, capture_output=True, text=True, check=False)
        if result.returncode != 0:
            raise RuntimeError(
                f"Key conversion failed: {result.stderr.strip()}"
            )
        logger.info("Converted %s → %s (%s)", filepath, dest, output_format)
        return dest

    # ── Remote operations ────────────────────────────────────────

    def copy_public_key(
        self,
        key_path: str,
        remote_host: str,
        username: str,
        port: int = 22,
    ) -> bool:
        """Copy the public key to a remote host via ``ssh-copy-id``.

        Returns *True* on success.
        """
        pub_path = key_path + ".pub" if not key_path.endswith(".pub") else key_path
        cmd = [
            "ssh-copy-id",
            "-i", pub_path,
            "-p", str(port),
            f"{username}@{remote_host}",
        ]
        logger.info("Copying public key to %s@%s:%d", username, remote_host, port)
        result = subprocess.run(cmd, capture_output=True, text=True, check=False)
        if result.returncode != 0:
            logger.error("ssh-copy-id failed: %s", result.stderr.strip())
            return False
        return True

    def get_public_key_text(self, key_path: str) -> str:
        """Return the textual content of the public key file.

        Raises
        ------
        FileNotFoundError
            If the ``.pub`` file does not exist.
        """
        pub_path = key_path + ".pub" if not key_path.endswith(".pub") else key_path
        if not os.path.isfile(pub_path):
            raise FileNotFoundError(f"Public key not found: {pub_path}")
        with open(pub_path, encoding="utf-8") as fh:
            return fh.read().strip()

    # ── Key lifecycle ────────────────────────────────────────────

    def delete_key(self, filepath: str) -> None:
        """Delete a key pair (private key and its ``.pub`` counterpart).

        Raises
        ------
        FileNotFoundError
            If the private key file does not exist.
        """
        if not os.path.isfile(filepath):
            raise FileNotFoundError(f"Key file not found: {filepath}")

        os.remove(filepath)
        logger.info("Deleted private key: %s", filepath)

        pub_path = filepath + ".pub"
        if os.path.isfile(pub_path):
            os.remove(pub_path)
            logger.info("Deleted public key: %s", pub_path)

    def change_passphrase(
        self,
        filepath: str,
        old_passphrase: str,
        new_passphrase: str,
    ) -> None:
        """Change (or remove) the passphrase on a private key.

        Raises
        ------
        RuntimeError
            If ``ssh-keygen`` fails (e.g. wrong old passphrase).
        """
        cmd = [
            "ssh-keygen",
            "-p",
            "-f", filepath,
            "-P", old_passphrase,
            "-N", new_passphrase,
        ]
        result = subprocess.run(cmd, capture_output=True, text=True, check=False)
        if result.returncode != 0:
            raise RuntimeError(
                f"Passphrase change failed: {result.stderr.strip()}"
            )
        logger.info("Passphrase changed for %s", filepath)

    # ── SSH agent ────────────────────────────────────────────────

    def add_to_agent(self, filepath: str, passphrase: Optional[str] = None) -> bool:
        """Add a key to the running SSH agent.

        Parameters
        ----------
        filepath:
            Path to the private key.
        passphrase:
            Passphrase for the key (if required).

        Returns
        -------
        bool
            *True* when the key was added successfully.
        """
        env = os.environ.copy()
        if passphrase is not None:
            env["SSH_ASKPASS"] = "/bin/echo"
            env["SSH_ASKPASS_REQUIRE"] = "force"
            env["DISPLAY"] = env.get("DISPLAY", ":0")

        cmd = ["ssh-add", filepath]
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            check=False,
            env=env,
            input=passphrase if passphrase else None,
        )
        if result.returncode != 0:
            logger.error("ssh-add failed: %s", result.stderr.strip())
            return False
        logger.info("Added key to agent: %s", filepath)
        return True

    def remove_from_agent(self, filepath: str) -> bool:
        """Remove a key from the running SSH agent.

        Returns *True* on success.
        """
        result = subprocess.run(
            ["ssh-add", "-d", filepath],
            capture_output=True,
            text=True,
            check=False,
        )
        if result.returncode != 0:
            logger.error("ssh-add -d failed: %s", result.stderr.strip())
            return False
        logger.info("Removed key from agent: %s", filepath)
        return True

    def list_agent_keys(self) -> list[str]:
        """List fingerprints of keys currently loaded in the SSH agent.

        Returns an empty list when no agent is running or no keys are
        loaded.
        """
        result = subprocess.run(
            ["ssh-add", "-l"],
            capture_output=True,
            text=True,
            check=False,
        )
        if result.returncode != 0:
            return []
        return [line for line in result.stdout.strip().splitlines() if line]
