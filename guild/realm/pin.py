import hashlib
import ssl
from pathlib import Path


def fingerprint(der_bytes):
    digest = hashlib.sha256(der_bytes).hexdigest().upper()
    return ":".join(digest[index : index + 2] for index in range(0, len(digest), 2))


def cert_fingerprint(cert_path):
    pem_text = Path(cert_path).read_text(encoding="ascii")
    return fingerprint(ssl.PEM_cert_to_DER_cert(pem_text))
