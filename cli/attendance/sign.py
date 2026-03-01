import base64
import time

from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import padding, rsa


class SignatureError(Exception):
    pass


_PRIVATE_KEY_PEM = """-----BEGIN PRIVATE KEY-----
MIIBVAIBADANBgkqhkiG9w0BAQEFAASCAT4wggE6AgEAAkEAw1OBuvkAyMU70/cn
0WKNk6xgB2leC+jd1i3fAt+lmxMFMjHuv4On/0ZoEILzidwlSkkA3lfjVT135ADE
i2WThwIDAQABAkEAqptW9hQmXjcAUd1QdzAozzLB0ddz4N0uXrREVUM5aB+HPUsw
+H/1i9oTm2bYznzdWfa8Rz/c/zOaJDhRnrF3CQIhAOL6EJxOl57Ny2O3C1Cwp1ki
iQ4juRzi+/aaNs0KGE1jAiEA3E1hRK+k9/Q1iRFVczIx3nJ6r8tQbR+e/VVaFT2N
fI0CIHLuTrTnMu0tpbyDNk6QdNy0mRO40QYohY80PWWLpAyjAiB1fa9KeoJ42v1S
RLRV44dFI7ja2IvkJuEcKtEIUvOKYQIgElLvoKegVbSfhFhhezxoJ2MLZ03ybWTH
LF5qmtC+MjI=
-----END PRIVATE KEY-----"""

_PRIVATE_KEY = serialization.load_pem_private_key(
    _PRIVATE_KEY_PEM.encode("ascii"),
    password=None,
)


def generate_signature(md5str: str, user_code: str) -> dict:
    if not md5str:
        raise SignatureError("md5str is required")
    if not user_code:
        raise SignatureError("user_code is required")

    timestamp = int(time.time())
    payload = f"{md5str}&{user_code}&{timestamp}"

    try:
        if not isinstance(_PRIVATE_KEY, rsa.RSAPrivateKey):
            raise SignatureError("invalid RSA private key")
        raw_signature = _PRIVATE_KEY.sign(
            payload.encode("utf-8"),
            padding.PKCS1v15(),
            hashes.SHA256(),
        )
    except Exception as exc:
        raise SignatureError(f"failed to sign payload: {exc}") from exc

    signature = base64.b64encode(raw_signature).decode("ascii")
    return {
        "sign": signature,
        "timestamp": timestamp,
    }
