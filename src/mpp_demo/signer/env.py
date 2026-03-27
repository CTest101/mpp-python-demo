"""Load a Signer from environment variables.

Supports:
  MPP_PRIVATE_KEY=0x...  → LocalSigner

Future:
  MPP_SIGNER_TYPE=kms + MPP_KMS_KEY_ID=...  → KmsSigner
  MPP_SIGNER_TYPE=mpc + MPP_MPC_CONFIG=...  → MpcSigner
"""

import os

from .base import Signer
from .local import LocalSigner


def signer_from_env(env_key: str = "MPP_PRIVATE_KEY") -> Signer:
    """Create a signer from environment variables.

    Currently only supports local private key.
    Extend this factory for KMS/MPC/Passkey backends.
    """
    private_key = os.environ.get(env_key)
    if not private_key:
        raise ValueError(
            f"Set {env_key} environment variable. "
            f"Example: export {env_key}=0xac0974bec39a17e36ba4a6b4d238ff944bacb478cbed5efcae784d7bf4f2ff80"
        )
    return LocalSigner(private_key)
