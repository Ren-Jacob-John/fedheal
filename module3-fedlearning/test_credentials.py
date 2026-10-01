"""
Module 3's credentials for talking to Module 1 are hospital-scoped tokens,
never the old shared static key.

Run:  pytest test_credentials.py -v
"""
import pytest

import config
import real_data
import service_auth

SIGNING_KEY = "Rt5Yq8LmZc2VbNw7XeJk4HdSa9PfGu3T"
HOSP_A = "hospital-a-id"


@pytest.fixture(autouse=True)
def clean_env(monkeypatch):
    for k in ("FEDHEAL_SVC_TOKEN_M3_M1", "FEDHEAL_SVC_SIGNING_KEY_M3_M1", "FEDHEAL_SVC_KEY_M3_M1"):
        monkeypatch.delenv(k, raising=False)
    monkeypatch.setenv("FEDHEAL_ENV", "production")


def claims_of(headers, key=SIGNING_KEY, audiences=(service_auth.AUD_VITALS_EXPORT, service_auth.AUD_HOSPITAL_DIRECTORY)):
    return service_auth.verify_service_token(headers["X-Service-Key"], signing_key=key,
                                             allowed_audiences=set(audiences), allowed_callers={"module3"})


def test_operator_mode_mints_a_token_scoped_to_the_requested_hospital(monkeypatch):
    monkeypatch.setenv("FEDHEAL_SVC_SIGNING_KEY_M3_M1", SIGNING_KEY)
    claims = claims_of(real_data._export_headers(HOSP_A))
    assert claims["hid"] == HOSP_A and claims["aud"] == service_auth.AUD_VITALS_EXPORT and claims["sub"] == "module3"


def test_each_hospital_gets_its_own_token(monkeypatch):
    monkeypatch.setenv("FEDHEAL_SVC_SIGNING_KEY_M3_M1", SIGNING_KEY)
    a = claims_of(real_data._export_headers("hospital-a"))
    b = claims_of(real_data._export_headers("hospital-b"))
    assert a["hid"] == "hospital-a" and b["hid"] == "hospital-b"


def test_directory_token_is_wildcard_but_audience_limited(monkeypatch):
    monkeypatch.setenv("FEDHEAL_SVC_SIGNING_KEY_M3_M1", SIGNING_KEY)
    claims = claims_of(real_data._directory_headers())
    assert claims["aud"] == service_auth.AUD_HOSPITAL_DIRECTORY and claims["hid"] == service_auth.ANY_HOSPITAL


def test_hospital_client_mode_presents_its_premade_token_verbatim(monkeypatch):
    pre = service_auth.mint_service_token(SIGNING_KEY, caller="module3", audience=service_auth.AUD_VITALS_EXPORT,
                                          hospital_id=HOSP_A, ttl_seconds=86400)
    monkeypatch.setenv("FEDHEAL_SVC_TOKEN_M3_M1", pre)
    assert real_data._export_headers(HOSP_A) == {"X-Service-Key": pre}
    assert real_data._directory_headers() == {"X-Service-Key": pre}  # a scoped token is all it has


def test_hospital_client_never_needs_the_signing_key(monkeypatch):
    pre = service_auth.mint_service_token(SIGNING_KEY, caller="module3", audience=service_auth.AUD_VITALS_EXPORT,
                                          hospital_id=HOSP_A)
    monkeypatch.setenv("FEDHEAL_SVC_TOKEN_M3_M1", pre)
    assert "FEDHEAL_SVC_SIGNING_KEY_M3_M1" not in __import__("os").environ
    real_data._export_headers(HOSP_A)  # no error


def test_production_without_any_credential_fails_clearly():
    with pytest.raises(RuntimeError, match="No Module 1 credential"):
        real_data._export_headers(HOSP_A)
    with pytest.raises(RuntimeError, match="No Module 1 credential"):
        real_data._directory_headers()


def test_production_rejects_weak_signing_key(monkeypatch):
    monkeypatch.setenv("FEDHEAL_SVC_SIGNING_KEY_M3_M1", "dev-only-signing-key-module3-to-module1")
    with pytest.raises(config.ConfigError):
        real_data._export_headers(HOSP_A)


def test_development_falls_back_to_dev_signing_key(monkeypatch):
    monkeypatch.setenv("FEDHEAL_ENV", "development")
    claims = claims_of(real_data._export_headers(HOSP_A), key=real_data._DEV_SIGNING_KEY)
    assert claims["hid"] == HOSP_A


def test_legacy_static_key_is_ignored(monkeypatch):
    monkeypatch.setenv("FEDHEAL_SVC_KEY_M3_M1", "iamgodofthunder")
    with pytest.raises(RuntimeError):
        real_data._export_headers(HOSP_A)


def test_no_wildcard_export_token_can_be_minted():
    with pytest.raises(ValueError):
        service_auth.mint_service_token(SIGNING_KEY, caller="module3", audience=service_auth.AUD_VITALS_EXPORT,
                                        hospital_id=service_auth.ANY_HOSPITAL)
