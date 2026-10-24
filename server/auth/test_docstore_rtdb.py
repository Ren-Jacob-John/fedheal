"""RTDBBackend against a strict in-memory fake of the firebase_admin Reference API.

The fake enforces what the real tree enforces (no null / [] / {} / arrays on write, key
character rules), so these tests fail if the encoding ever lets such a value through.
It does NOT prove behaviour against the real service or emulator.
"""
import copy
from datetime import datetime, timezone

import pytest

import models
from docstore import AlreadyExists, RTDBBackend
from repo import DuplicateError, Repo


def _check(v, path=""):
    if v is None or v == [] or v == {} or not isinstance(v, (str, int, float, bool, dict)):
        raise AssertionError(f"RTDB cannot store {v!r} at {path}")
    if isinstance(v, dict):
        for k, x in v.items():
            if any(c in k for c in ".$#[]") and "/" not in path + k[:0]:
                raise AssertionError(f"illegal key {k!r}")
            _check(x, f"{path}/{k}")


class FakeRef:
    def __init__(self, tree, path=""):
        self.tree, self.path = tree, path

    def _parts(self, p):
        return [x for x in p.strip("/").split("/") if x]

    def child(self, p):
        return FakeRef(self.tree, "/".join(self._parts(self.path + "/" + p)))

    def _walk(self, parts, create=False):
        node = self.tree
        for p in parts:
            if p not in node:
                if not create:
                    return None
                node[p] = {}
            node = node[p]
        return node

    def get(self, etag=False, shallow=False):
        node = self._walk(self._parts(self.path))
        node = copy.deepcopy(node)
        if shallow and isinstance(node, dict):
            node = {k: True for k in node}
        return (node, "etag") if etag else node

    def set(self, value):
        _check(value, self.path)
        parts = self._parts(self.path)
        parent = self._walk(parts[:-1], create=True)
        parent[parts[-1]] = copy.deepcopy(value)

    def delete(self):
        parts = self._parts(self.path)
        parent = self._walk(parts[:-1])
        if parent is not None:
            parent.pop(parts[-1], None)

    def update(self, writes):
        for p, v in writes.items():  # validate everything first: the real call is atomic
            if v is not None:
                _check(v, p)
        for p, v in writes.items():
            ref = self.child(p)
            ref.delete() if v is None else ref.set(v)

    def transaction(self, fn):
        new = fn(self.get())
        self.set(new)
        return new

    def order_by_child(self, field):
        outer = self

        class Q:
            def equal_to(self, v):
                class R:
                    def get(_s):
                        node = outer.get() or {}
                        hit = {k: d for k, d in node.items() if d.get(field) == v}
                        return hit or None
                return R()
        return Q()


@pytest.fixture
def backend():
    return RTDBBackend("http://x", root=FakeRef({}))


def test_roundtrip_types(backend):
    doc = {"id": "a", "none": None, "tags": [], "names": ["x", "y"], "when": datetime(2026, 1, 2, tzinfo=timezone.utc),
           "ok": True, "n": 3, "f": 1.5, "blob": '{"a":[[1]]}', "empty": ""}
    backend.set("c", "a.b@x/y", doc)  # id with every awkward character
    assert backend.get("c", "a.b@x/y") == doc


def test_create_conflict_leaves_nothing(backend):
    backend.create("idx", "e", {"user_id": "1"})
    with pytest.raises(AlreadyExists):
        backend.commit([("create", "users", "u2", {"id": "u2"}), ("create", "idx", "e", {"user_id": "2"})])
    assert backend.get("users", "u2") is None and backend.get("idx", "e") == {"user_id": "1"}


def test_failed_write_rolls_back_claims(backend):
    ops = [("create", "idx", "e", {"user_id": "1"}), ("set", "users", "u", {"id": "u", "bad": object()})]
    with pytest.raises(Exception):
        backend.commit(ops)
    assert backend.get("idx", "e") is None


def test_update_set_delete(backend):
    backend.set("c", "a", {"id": "a", "x": 1, "y": 2})
    backend.update("c", "a", {"y": None, "z": [1]})
    assert backend.get("c", "a") == {"id": "a", "x": 1, "y": None, "z": [1]}
    with pytest.raises(KeyError):
        backend.update("c", "missing", {"x": 1})
    backend.commit([("create", "c", "b", {"id": "b", "x": 1}), ("update", "c", "b", {"x": 9}), ("delete", "c", "a")])
    assert backend.get("c", "a") is None and backend.get("c", "b")["x"] == 9


def test_query_filters_order_limit_count(backend):
    for i, (h, n) in enumerate([("h1", 3), ("h1", 1), ("h2", 2), ("h1", None)]):
        backend.set("v", f"r{i}", {"id": f"r{i}", "hospital_id": h, "n": n, "when": datetime(2026, 1, i + 1, tzinfo=timezone.utc)})
    assert [r["id"] for r in backend.query("v", [("hospital_id", "==", "h1")], order_by="n")] == ["r3", "r1", "r0"]
    assert [r["id"] for r in backend.query("v", [("hospital_id", "==", "h1")], order_by="when", descending=True, limit=2)] == ["r3", "r1"]
    assert backend.count("v") == 4 and backend.count("v", [("hospital_id", "==", "h2")]) == 1
    assert backend.count("v", [("when", ">=", datetime(2026, 1, 3, tzinfo=timezone.utc))]) == 2
    assert backend.query("nothing") == [] and backend.count("nothing") == 0


def test_repo_enforces_uniqueness_and_roundtrips_models(backend):
    repo = Repo(backend)
    h = repo.create_hospital(models.Hospital(name="City General"))
    with pytest.raises(DuplicateError):
        repo.create_hospital(models.Hospital(name="City General"))
    u = repo.create_user(models.User(email="a.b@example.com", hashed_password="x", role=models.Role.CLINICIAN, hospital_id=h.id))
    with pytest.raises(DuplicateError):
        repo.create_user(models.User(email="a.b@example.com", hashed_password="y"))
    assert repo.get_user_by_email("a.b@example.com") == u
    assert repo.list_doctors(h.id) == [u]
    assert repo.get_hospital_by_name("City General") == h
