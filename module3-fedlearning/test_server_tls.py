import pytest

from server import load_tls_certificates


def test_tls_is_disabled_when_no_certificates_are_configured():
    assert load_tls_certificates(None, None, None) is None


def test_tls_requires_all_certificate_files(tmp_path):
    with pytest.raises(ValueError, match="provided together"):
        load_tls_certificates("ca.pem", None, "server.key")

    ca = tmp_path / "ca.pem"
    cert = tmp_path / "server.pem"
    key = tmp_path / "server.key"
    ca.write_bytes(b"CA")
    cert.write_bytes(b"CERT")
    key.write_bytes(b"KEY")
    assert load_tls_certificates(str(ca), str(cert), str(key)) == (b"CA", b"CERT", b"KEY")
