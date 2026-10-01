"""create_super_admin.py: the only way to make the first super_admin."""
import os
import subprocess
import sys

import secsupport as sx  # must be first: throwaway DB before `database` loads
import models  # noqa: E402
from secsupport import client, main  # noqa: E402


def run(email, password):
    env = {**os.environ, "FEDHEAL_BOOTSTRAP_ADMIN_PASSWORD": password}
    return subprocess.run([sys.executable, "create_super_admin.py", "--email", email],
                          capture_output=True, text=True, env=env, timeout=60)


def test_creates_a_super_admin_who_can_create_hospitals():
    email = f"{sx.uid('boot')}@test.fedheal.local"
    r = run(email, "a-long-enough-password")
    assert r.returncode == 0, r.stderr
    assert "a-long-enough-password" not in r.stdout + r.stderr
    tok = client.post("/token", data={"username": email, "password": "a-long-enough-password"}).json()["access_token"]
    client.cookies.clear()
    resp = client.post("/hospitals", json={"name": sx.uid("Boot")}, headers=sx.bearer(tok))
    assert resp.status_code == 200


def test_short_password_and_duplicates_refused():
    email = f"{sx.uid('dup')}@test.fedheal.local"
    assert run(email, "short").returncode == 2
    assert run(email, "a-long-enough-password").returncode == 0
    assert run(email, "a-long-enough-password").returncode == 1
