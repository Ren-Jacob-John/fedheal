"""
Secret / environment handling: production and staging fail fast when a
required secret is missing, weak or a placeholder; development falls back
with a warning that never contains the value.

Each case runs in a FRESH interpreter (the secrets are read at import time,
which is exactly the startup behaviour being verified).

Run:  pytest test_config.py -v
"""
import os
import pathlib
import subprocess
import sys

import pytest

HERE = pathlib.Path(__file__).resolve().parent
ROOT = HERE.parent
GOOD = {
    "FEDMED_JWT_SECRET": "k9V2mQxT7rLw4ZbN8cFhY1sPdAe6UgJo",
    "FEDHEAL_SVC_SIGNING_KEY_M3_M1": "Rt5Yq8LmZc2VbNw7XeJk4HdSa9PfGu3T",
    "FEDHEAL_SVC_SIGNING_KEY_M1_M2": "Bn6Wz1QxCv8LkMj3RtYh5GfDs2AoPe9U",
    "FEDHEAL_DASHBOARD_ORIGIN": "https://dashboard.example-hospital.org",
    "FEDHEAL_DATABASE_URL": "sqlite:///./_test_config_unused.db",
}


def run(module_dir: str, code: str, env: dict, *, unset=()):
    full = {k: v for k, v in os.environ.items() if not k.startswith(("FEDHEAL_", "FEDMED_"))}
    full.update(env)
    for k in unset:
        full.pop(k, None)
    return subprocess.run([sys.executable, "-c", code], cwd=ROOT / module_dir, env=full,
                          capture_output=True, text=True, timeout=120)


def prod(**over):
    e = {**GOOD, "FEDHEAL_ENV": "production"}
    e.update(over)
    return e


IMPORT_M1 = "import main"


@pytest.mark.parametrize("tier", ["production", "staging"])
class TestHostedTiers:
    def test_valid_config_starts(self, tier):
        r = run("module1-auth", IMPORT_M1, prod(FEDHEAL_ENV=tier))
        assert r.returncode == 0, r.stderr[-800:]

    @pytest.mark.parametrize("missing", ["FEDMED_JWT_SECRET", "FEDHEAL_SVC_SIGNING_KEY_M3_M1",
                                         "FEDHEAL_SVC_SIGNING_KEY_M1_M2", "FEDHEAL_DASHBOARD_ORIGIN"])
    def test_missing_secret_or_origin_refuses_to_start(self, tier, missing):
        env = prod(FEDHEAL_ENV=tier)
        env.pop(missing)
        r = run("module1-auth", IMPORT_M1, env)
        assert r.returncode != 0 and "ConfigError" in r.stderr and missing in r.stderr

    @pytest.mark.parametrize("weak", ["dev-only-change-me", "Zq7xk", "change-me-please-change-me-please-1234",
                                      "iamgodofthunder", "your-secret-here-your-secret-here-12"])
    def test_weak_or_placeholder_jwt_secret_refused_without_echoing_it(self, tier, weak):
        r = run("module1-auth", IMPORT_M1, prod(FEDHEAL_ENV=tier, FEDMED_JWT_SECRET=weak))
        assert r.returncode != 0 and "ConfigError" in r.stderr
        # the exception message (last line) names the variable, never the value
        assert weak not in r.stderr.strip().splitlines()[-1]

    def test_insecure_cookie_flag_refused(self, tier):
        r = run("module1-auth", IMPORT_M1, prod(FEDHEAL_ENV=tier, FEDHEAL_COOKIE_SECURE="false"))
        assert r.returncode != 0 and "FEDHEAL_COOKIE_SECURE" in r.stderr

    @pytest.mark.parametrize("origin", ["http://dashboard.example.org", "*", "https://*.example.org"])
    def test_non_https_or_wildcard_origin_refused(self, tier, origin):
        r = run("module1-auth", IMPORT_M1, prod(FEDHEAL_ENV=tier, FEDHEAL_DASHBOARD_ORIGIN=origin))
        assert r.returncode != 0 and "FEDHEAL_DASHBOARD_ORIGIN" in r.stderr

    def test_session_cookie_is_secure(self, tier):
        r = run("module1-auth", "import main; print(main.COOKIE_SECURE)", prod(FEDHEAL_ENV=tier))
        assert r.stdout.strip() == "True"


def test_unset_environment_is_treated_as_production():
    env = {k: v for k, v in GOOD.items() if k != "FEDMED_JWT_SECRET"}
    r = run("module1-auth", IMPORT_M1, env)  # FEDHEAL_ENV not set at all
    assert r.returncode != 0 and "FEDMED_JWT_SECRET" in r.stderr


def test_unknown_environment_name_refused():
    r = run("module1-auth", IMPORT_M1, {**GOOD, "FEDHEAL_ENV": "prod-ish"})
    assert r.returncode != 0 and "FEDHEAL_ENV" in r.stderr


class TestDevelopment:
    def test_starts_with_fallbacks_and_warns_by_name_only(self):
        r = run("module1-auth", "import main", {"FEDHEAL_ENV": "development",
                                                "FEDHEAL_DATABASE_URL": GOOD["FEDHEAL_DATABASE_URL"]})
        assert r.returncode == 0, r.stderr[-800:]
        assert "FEDMED_JWT_SECRET" in r.stderr and "DEVELOPMENT-ONLY" in r.stderr
        assert "dev-only-change-me" not in r.stderr.split("DEVELOPMENT-ONLY")[0].splitlines()[-1]  # warning names the variable, not the value

    def test_dev_cookie_not_secure_by_default(self):
        r = run("module1-auth", "import main; print(main.COOKIE_SECURE)",
                {"FEDHEAL_ENV": "development", "FEDHEAL_DATABASE_URL": GOOD["FEDHEAL_DATABASE_URL"]})
        assert r.stdout.strip() == "False"


@pytest.mark.parametrize("module,code,keys", [
    ("module2-validation", "import main", ["FEDHEAL_SVC_SIGNING_KEY_M1_M2", "FEDHEAL_SVC_KEY_M2_M7"]),
    ("module7-admin", "import main", ["FEDMED_JWT_SECRET", "FEDHEAL_SVC_KEY_M2_M7", "FEDHEAL_SVC_KEY_M3_M7",
                                      "FEDHEAL_DASHBOARD_ORIGIN"]),
    ("module8-synthesis", "import main", ["FEDMED_JWT_SECRET", "FEDHEAL_DASHBOARD_ORIGIN"]),
])
def test_other_services_fail_fast_in_production(module, code, keys):
    base = {**GOOD, "FEDHEAL_ENV": "production",
            "FEDHEAL_SVC_KEY_M2_M7": "Zx3Cv7BnMq1WeRt5YuIo9PaSd2FgHj4K",
            "FEDHEAL_SVC_KEY_M3_M7": "Lk8Jh2GfDs6AqWe1RtYu4IoPz9XcVb3N",
            "FEDHEAL_ADMIN_DATABASE_URL": "sqlite:////tmp/fedheal_cfg_test_admin.db"}
    assert run(module, code, base).returncode == 0
    for key in keys:
        env = dict(base)
        env.pop(key, None)
        r = run(module, code, env)
        assert r.returncode != 0 and key in r.stderr, (module, key, r.stderr[-300:])


def test_no_hardcoded_fallback_secrets_remain_in_source():
    """Guards against the old literals returning."""
    banned = ["iamgodofthunder", "iammightythor", "iamgodofdeath"]
    hits = []
    for path in ROOT.rglob("*"):
        if path.suffix in (".py", ".sh", ".md", ".example", ".js", ".jsx", ".yml", ".yaml", ".env") and \
                "node_modules" not in path.parts and not path.name.startswith("test_"):
            text = path.read_text(errors="ignore")
            hits += [f"{path.relative_to(ROOT)}: {b}" for b in banned if b in text]
    assert not hits, hits
