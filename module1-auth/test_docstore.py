"""
Document-store contract tests.

* LocalBackend (memory and JSON-file): the full contract the repositories rely on.
* FirestoreBackend: translation to the real google-cloud-firestore objects, checked
  offline (queries/batches are built by the real library; only the network call is
  stubbed). Skipped if the library isn't installed.
* If FIRESTORE_EMULATOR_HOST is set, the same contract suite also runs against the
  Firestore emulator:  firebase emulators:start --only firestore  (see README).
"""
import os
import threading
from datetime import datetime, timedelta, timezone

import pytest

import models
from docstore import AlreadyExists, FirestoreBackend, LocalBackend, from_doc, make_backend, to_doc
from repo import DuplicateError, Repo


def _backends(tmp_path):
    yield "memory", LocalBackend(None)
    yield "file", LocalBackend(str(tmp_path / "s.json"))
    if os.environ.get("FIRESTORE_EMULATOR_HOST"):
        yield "emulator", FirestoreBackend.from_env()


@pytest.fixture(params=["memory", "file", "emulator"])
def backend(request, tmp_path):
    for name, b in _backends(tmp_path):
        if name == request.param:
            return b
    pytest.skip(f"{request.param} backend not available")


@pytest.fixture
def coll():
    return f"t_{os.urandom(4).hex()}"  # isolates runs when pointed at a shared emulator


class TestContract:
    def test_create_get_update_delete(self, backend, coll):
        backend.create(coll, "a", {"x": 1})
        assert backend.get(coll, "a") == {"x": 1}
        backend.update(coll, "a", {"y": 2})
        assert backend.get(coll, "a") == {"x": 1, "y": 2}
        backend.delete(coll, "a")
        assert backend.get(coll, "a") is None

    def test_create_refuses_an_existing_document(self, backend, coll):
        backend.create(coll, "a", {"x": 1})
        with pytest.raises(AlreadyExists):
            backend.create(coll, "a", {"x": 2})
        assert backend.get(coll, "a") == {"x": 1}

    def test_commit_is_all_or_nothing(self, backend, coll):
        backend.create(coll, "taken", {"x": 1})
        with pytest.raises(AlreadyExists):
            backend.commit([("create", coll, "new", {"x": 9}), ("create", coll, "taken", {"x": 9})])
        assert backend.get(coll, "new") is None

    def test_filters_order_limit_count(self, backend, coll):
        now = datetime(2026, 1, 1, tzinfo=timezone.utc)
        for i in range(6):
            backend.create(coll, f"d{i}", {"id": f"d{i}", "h": "A" if i < 4 else "B", "n": i,
                                           "t": now + timedelta(days=i)})
        assert backend.count(coll, [("h", "==", "A")]) == 4
        assert backend.count(coll, [("t", ">=", now + timedelta(days=3))]) == 3
        rows = backend.query(coll, [("h", "==", "A")], order_by="t", descending=True, limit=2)
        assert [r["n"] for r in rows] == [3, 2]
        assert [r["n"] for r in backend.query(coll, [("h", "==", "B")], order_by="n")] == [4, 5]

    def test_bulk_set_chunks_beyond_one_batch(self, backend, coll):
        docs = [(f"d{i}", {"id": f"d{i}", "n": i}) for i in range(1000)]
        backend.bulk_set(coll, docs)
        assert backend.count(coll) == 1000


class TestLocalFileStore:
    def test_two_instances_share_one_file(self, tmp_path):
        p = str(tmp_path / "shared.json")
        a, b = LocalBackend(p), LocalBackend(p)
        a.create("c", "1", {"when": datetime(2026, 1, 2, tzinfo=timezone.utc)})
        got = b.get("c", "1")["when"]
        assert got == datetime(2026, 1, 2, tzinfo=timezone.utc) and got.tzinfo is not None

    def test_concurrent_creates_of_one_key_have_one_winner(self, tmp_path):
        b = LocalBackend(str(tmp_path / "race.json"))
        wins, losses = [], []

        def go(i):
            try:
                b.create("c", "same", {"i": i})
                wins.append(i)
            except AlreadyExists:
                losses.append(i)

        threads = [threading.Thread(target=go, args=(i,)) for i in range(8)]
        [t.start() for t in threads]
        [t.join() for t in threads]
        assert len(wins) == 1 and len(losses) == 7


class TestEntityMapping:
    def test_enum_blob_and_nested_arrays_round_trip(self):
        import importlib
        import sys
        sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "module7-admin"))
        # module7's models module has the blob fields; load it under another name to avoid the clash
        spec = importlib.util.spec_from_file_location("m7_models", os.path.join(
            os.path.dirname(__file__), "..", "module7-admin", "models.py"))
        m7 = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(m7)
        mv = m7.ModelVersion(model_name="n", version="v1", condition="c", training_round=1, artifact_hash="h",
                             parameters={"coef": [[0.1, 0.2]], "intercept": [0.0]})
        doc = to_doc(mv)
        assert isinstance(doc["parameters"], str)            # nested arrays never reach Firestore
        assert from_doc(m7.ModelVersion, doc).parameters == {"coef": [[0.1, 0.2]], "intercept": [0.0]}

    def test_role_enum_is_stored_as_its_value(self):
        u = models.User(email="e", hashed_password="h", role=models.Role.HOSPITAL_ADMIN)
        assert to_doc(u)["role"] == "hospital_admin"
        assert from_doc(models.User, to_doc(u)).role is models.Role.HOSPITAL_ADMIN

    def test_documents_written_before_a_field_existed_still_load(self):
        doc = to_doc(models.User(email="e", hashed_password="h"))
        doc.pop("full_name")
        assert from_doc(models.User, doc).full_name is None


class TestRepoUniqueness:
    def test_duplicate_email_and_hospital_name_are_refused(self):
        r = Repo(LocalBackend(None))
        r.create_user(models.User(email="a@x", hashed_password="h"))
        with pytest.raises(DuplicateError):
            r.create_user(models.User(email="a@x", hashed_password="h"))
        r.create_hospital(models.Hospital(name="H"))
        with pytest.raises(DuplicateError):
            r.create_hospital(models.Hospital(name="H"))
        assert len(r.list_hospitals()) == 1

    def test_email_lookup_is_exact_not_fuzzy(self):
        r = Repo(LocalBackend(None))
        r.create_user(models.User(email="a@x", hashed_password="h"))
        assert r.get_user_by_email("A@x") is None

    def test_one_history_per_case_by_construction(self):
        r = Repo(LocalBackend(None))
        r.save_history(models.MedicalHistory(case_id="c1", hospital_id="h", created_by="u", notes="one"))
        r.save_history(models.MedicalHistory(case_id="c1", hospital_id="h", created_by="u", notes="two"))
        assert r.b.count("medical_histories") == 1 and r.get_history("c1").notes == "two"

    def test_review_and_case_status_move_together(self):
        r = Repo(LocalBackend(None))
        c = r.add_case(models.Case(hospital_id="h", patient_ref="P", admission_reason="x", created_by="u"))
        r.add_review(models.ClinicianReview(case_id=c.id, hospital_id="h", doctor_id="u", decision="ACCEPTED"),
                     c, "REVIEWED")
        assert r.get_case(c.id).status == "REVIEWED" and len(r.list_reviews(c.id, "h")) == 1


class TestBackendSelection:
    def test_local_default_in_development(self, monkeypatch, tmp_path):
        monkeypatch.delenv("FEDHEAL_DB_BACKEND", raising=False)
        b = make_backend(local_default_path=str(tmp_path / "x.json"), is_local=True, env="development")
        assert isinstance(b, LocalBackend)

    def test_hosted_tiers_default_to_firestore_and_need_a_project(self, monkeypatch):
        monkeypatch.delenv("FEDHEAL_DB_BACKEND", raising=False)
        monkeypatch.delenv("FEDHEAL_FIREBASE_PROJECT_ID", raising=False)
        monkeypatch.delenv("FIRESTORE_EMULATOR_HOST", raising=False)
        with pytest.raises(RuntimeError, match="FEDHEAL_FIREBASE_PROJECT_ID"):
            make_backend(local_default_path="x", is_local=False, env="production")
        monkeypatch.setenv("FEDHEAL_FIREBASE_PROJECT_ID", "p")
        assert isinstance(make_backend(local_default_path="x", is_local=False, env="staging"), FirestoreBackend)


# ---------------------------------------------------------------- FirestoreBackend translation
fs = pytest.importorskip("google.cloud.firestore")


@pytest.fixture
def fsb(monkeypatch):
    from google.auth.credentials import AnonymousCredentials

    client = fs.Client(project="p", credentials=AnonymousCredentials())
    return FirestoreBackend("p", client=client), client


class TestFirestoreTranslation:
    def test_query_builds_the_expected_structured_query(self, fsb, monkeypatch):
        b, client = fsb
        captured = {}

        class Doc:
            def __init__(self, d): self._d = d
            def to_dict(self): return self._d

        def fake_stream(self, *a, **k):
            captured["q"] = self._to_protobuf()
            return iter([Doc({"id": "1"})])

        monkeypatch.setattr("google.cloud.firestore_v1.query.Query.stream", fake_stream)
        rows = b.query("cases", [("hospital_id", "==", "H1")], order_by="created_at", descending=True, limit=5)
        assert rows == [{"id": "1"}]
        q = captured["q"]
        assert q.from_[0].collection_id == "cases" and getattr(q.limit, "value", q.limit) == 5
        f = q.where.field_filter
        assert f.field.field_path == "hospital_id" and f.value.string_value == "H1"
        assert q.order_by[0].field.field_path == "created_at"
        assert q.order_by[0].direction == fs.Query.DESCENDING or q.order_by[0].direction.name == "DESCENDING"

    def test_batch_translates_ops_and_maps_already_exists(self, fsb, monkeypatch):
        from google.api_core import exceptions as gexc

        b, client = fsb
        seen = []
        monkeypatch.setattr("google.cloud.firestore_v1.batch.WriteBatch.commit",
                            lambda self, *a, **k: seen.append(list(self._write_pbs)))
        b.commit([("create", "u", "1", {"a": 1}), ("set", "u", "2", {"a": 2}),
                  ("update", "u", "3", {"a": 3}), ("delete", "u", "4")])
        create, set_, update, delete = seen[0]
        # create: write that must NOT already exist; set: unconditional write; update: must exist + field mask
        assert create.update.name.endswith("/u/1") and create.current_document.exists is False
        assert set_.update.name.endswith("/u/2") and not set_._pb.HasField("current_document")
        assert update.update.name.endswith("/u/3") and update.current_document.exists is True
        assert list(update.update_mask.field_paths) == ["a"]
        assert delete.delete.endswith("/u/4")

        def boom(self, *a, **k):
            raise gexc.AlreadyExists("exists")

        monkeypatch.setattr("google.cloud.firestore_v1.batch.WriteBatch.commit", boom)
        with pytest.raises(AlreadyExists):
            b.create("u", "1", {"a": 1})

    def test_count_uses_the_aggregation_api(self, fsb, monkeypatch):
        b, client = fsb

        class R:
            value = 7

        monkeypatch.setattr("google.cloud.firestore_v1.aggregation.AggregationQuery.get",
                            lambda self, *a, **k: [[R()]])
        assert b.count("vitals_records", [("hospital_id", "==", "H")]) == 7

    def test_batches_over_500_writes_are_refused_not_split_silently(self, fsb):
        b, _ = fsb
        with pytest.raises(ValueError):
            b.commit([("set", "c", str(i), {}) for i in range(501)])
