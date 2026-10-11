"""
Document store used by Module 1 and Module 7 — Firestore in staging/production,
a local JSON-file (or pure in-memory) store for development and tests.

CANONICAL COPY: this file is duplicated verbatim into module1-auth and
module7-admin (each deploys on its own). tests/test_shared_files_in_sync.py
fails if the copies drift apart — edit one, then copy it to the other.

Why this exists
---------------
The services used to talk to Postgres through SQLAlchemy. Firestore has no
SQL, joins, foreign keys or unique constraints, so the data layer is now a
deliberately small interface (`Backend`) with two implementations:

  FirestoreBackend  google-cloud-firestore. Credentials come from the standard
                    Google mechanisms (GOOGLE_APPLICATION_CREDENTIALS, or the
                    attached service account on Cloud Run/GCE). Setting
                    FIRESTORE_EMULATOR_HOST points it at the local emulator.
  LocalBackend      Plain Python dicts, optionally persisted to one JSON file
                    (safe across threads and across processes on one machine).
                    Replaces the old "SQLite fallback for quick local dev".
                    Refused in staging/production.

Everything above this layer (repo.py) only uses the methods below, so it runs
unchanged against either backend. Only equality / simple range filters, one
ordering and a limit are used — nothing that needs more than a composite index
declared in firestore.indexes.json.

Firestore facts the callers rely on (and the LocalBackend mimics):
  * no unique constraints -> uniqueness is enforced with an "index document"
    whose id is derived from the unique value, created atomically with the
    real document (`commit` with two `create` ops; both or neither);
  * a batch holds at most 500 writes -> bulk inserts go through `bulk_set`,
    which chunks (and is therefore NOT atomic across chunks);
  * nested arrays (a list directly inside a list) are rejected by Firestore ->
    fields that hold arbitrary JSON are stored as JSON text (`blob` fields).
"""
from __future__ import annotations

import copy
import dataclasses
import json
import logging
import os
import tempfile
import threading
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Optional, Sequence

try:  # POSIX only; on Windows the local file store is single-process
    import fcntl
except ImportError:  # pragma: no cover
    fcntl = None

logger = logging.getLogger("fedheal.docstore")

Filter = tuple  # (field, op, value); op in ==, >=, >, <=, <
MAX_BATCH = 450  # Firestore's hard limit is 500 writes per batch


class AlreadyExists(Exception):
    """A `create` hit an existing document (the document-store form of a unique-constraint violation)."""


# ----------------------------------------------------------------------------
# Entity <-> document mapping
# ----------------------------------------------------------------------------

def enum_field(enum_cls, **kw):
    return dataclasses.field(metadata={"enum": enum_cls}, **kw)


def blob_field(**kw):
    """Arbitrary JSON (dicts/lists, possibly nested lists). Stored as JSON text."""
    return dataclasses.field(metadata={"blob": True}, **kw)


def to_doc(obj) -> dict:
    out: dict[str, Any] = {}
    for f in dataclasses.fields(obj):
        v = getattr(obj, f.name)
        if f.metadata.get("blob"):
            v = None if v is None else json.dumps(v, separators=(",", ":"), sort_keys=True)
        elif isinstance(v, Enum):
            v = v.value
        elif isinstance(v, list):
            v = list(v)
        out[f.name] = v
    return out


def from_doc(cls, data: Optional[dict]):
    if data is None:
        return None
    kwargs = {}
    for f in dataclasses.fields(cls):
        if f.name not in data:
            continue  # field added after this document was written -> dataclass default
        v = data[f.name]
        enum_cls = f.metadata.get("enum")
        if f.metadata.get("blob"):
            v = None if v is None else json.loads(v)
        elif enum_cls is not None and v is not None:
            v = enum_cls(v)
        elif isinstance(v, datetime) and v.tzinfo is None:
            v = v.replace(tzinfo=timezone.utc)
        kwargs[f.name] = v
    return cls(**kwargs)


# ----------------------------------------------------------------------------
# Backend interface
# ----------------------------------------------------------------------------

class Backend:
    def get(self, coll: str, doc_id: str) -> Optional[dict]: raise NotImplementedError
    def set(self, coll: str, doc_id: str, data: dict) -> None: raise NotImplementedError
    def delete(self, coll: str, doc_id: str) -> None: raise NotImplementedError
    def query(self, coll: str, filters: Sequence[Filter] = (), order_by: Optional[str] = None,
              descending: bool = False, limit: Optional[int] = None) -> list[dict]: raise NotImplementedError
    def count(self, coll: str, filters: Sequence[Filter] = ()) -> int: raise NotImplementedError
    def commit(self, ops: Sequence[tuple]) -> None:
        """Atomically apply ops: ("create"|"set"|"update"|"delete", coll, doc_id[, data]).
        `create` raises AlreadyExists (and nothing is written) if the document exists."""
        raise NotImplementedError

    # convenience built on commit
    def create(self, coll: str, doc_id: str, data: dict) -> None:
        self.commit([("create", coll, doc_id, data)])

    def update(self, coll: str, doc_id: str, fields: dict) -> None:
        self.commit([("update", coll, doc_id, fields)])

    def bulk_set(self, coll: str, docs: Sequence[tuple[str, dict]]) -> None:
        """Insert many documents. Chunked, so NOT atomic across chunks."""
        for i in range(0, len(docs), MAX_BATCH):
            self.commit([("set", coll, d_id, data) for d_id, data in docs[i:i + MAX_BATCH]])


def _matches(doc: dict, filters: Sequence[Filter]) -> bool:
    for field, op, value in filters:
        have = doc.get(field)
        if op == "==":
            if have != value:
                return False
            continue
        if have is None:
            return False
        if op == ">=" and not have >= value: return False
        if op == ">" and not have > value: return False
        if op == "<=" and not have <= value: return False
        if op == "<" and not have < value: return False
        if op not in ("==", ">=", ">", "<=", "<"):
            raise ValueError(f"unsupported filter operator {op!r}")
    return True


# ----------------------------------------------------------------------------
# LocalBackend
# ----------------------------------------------------------------------------

def _encode(o):
    if isinstance(o, datetime):
        return {"__dt__": o.isoformat()}
    raise TypeError(f"cannot store {type(o).__name__}")


def _decode(o):
    if "__dt__" in o and len(o) == 1:
        return datetime.fromisoformat(o["__dt__"])
    return o


class LocalBackend(Backend):
    """In-memory when `path` is None; otherwise persisted to one JSON file that
    is re-read on every operation (so several local processes can share it)."""

    def __init__(self, path: Optional[str] = None):
        self._path = os.path.abspath(path) if path else None
        self._mem: dict[str, dict[str, dict]] = {}
        self._lock = threading.RLock()

    # -- persistence ---------------------------------------------------------
    def _load(self) -> dict:
        if self._path is None:
            return self._mem
        try:
            with open(self._path, "r", encoding="utf-8") as fh:
                return json.load(fh, object_hook=_decode)
        except FileNotFoundError:
            return {}

    def _save(self, data: dict) -> None:
        if self._path is None:
            return
        directory = os.path.dirname(self._path) or "."
        os.makedirs(directory, exist_ok=True)
        fd, tmp = tempfile.mkstemp(dir=directory, prefix=".store-", suffix=".tmp")
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as fh:
                json.dump(data, fh, default=_encode)
            os.replace(tmp, self._path)
        except BaseException:
            try:
                os.remove(tmp)
            except OSError:
                pass
            raise

    class _Txn:
        def __init__(self, outer: "LocalBackend", write: bool):
            self.o, self.write, self.lock_fh = outer, write, None

        def __enter__(self):
            self.o._lock.acquire()
            try:
                if self.o._path is not None and fcntl is not None:
                    os.makedirs(os.path.dirname(self.o._path) or ".", exist_ok=True)
                    self.lock_fh = open(self.o._path + ".lock", "a+")
                    fcntl.flock(self.lock_fh, fcntl.LOCK_EX if self.write else fcntl.LOCK_SH)
                self.data = self.o._load()
            except BaseException:
                if self.lock_fh is not None:
                    self.lock_fh.close()
                self.o._lock.release()
                raise
            return self.data

        def __exit__(self, exc_type, exc, tb):
            try:
                if exc_type is None and self.write:
                    self.o._save(self.data)
            finally:
                if self.lock_fh is not None:
                    fcntl.flock(self.lock_fh, fcntl.LOCK_UN)
                    self.lock_fh.close()
                self.o._lock.release()
            return False

    # -- Backend -------------------------------------------------------------
    def get(self, coll, doc_id):
        with self._Txn(self, write=False) as data:
            doc = data.get(coll, {}).get(doc_id)
            return copy.deepcopy(doc) if doc is not None else None

    def set(self, coll, doc_id, doc):
        self.commit([("set", coll, doc_id, doc)])

    def delete(self, coll, doc_id):
        self.commit([("delete", coll, doc_id)])

    def commit(self, ops):
        with self._Txn(self, write=True) as data:
            # validate first so a failing op leaves nothing half-applied
            pending: dict[tuple[str, str], bool] = {}
            for op in ops:
                kind, coll, doc_id = op[0], op[1], op[2]
                exists = pending.get((coll, doc_id), doc_id in data.get(coll, {}))
                if kind == "create":
                    if exists:
                        raise AlreadyExists(f"{coll}/{doc_id}")
                    pending[(coll, doc_id)] = True
                elif kind == "update":
                    if not exists:
                        raise KeyError(f"{coll}/{doc_id} does not exist")
                elif kind == "set":
                    pending[(coll, doc_id)] = True
                elif kind == "delete":
                    pending[(coll, doc_id)] = False
                else:
                    raise ValueError(f"unknown op {kind!r}")
            for op in ops:
                kind, coll, doc_id = op[0], op[1], op[2]
                table = data.setdefault(coll, {})
                if kind in ("create", "set"):
                    table[doc_id] = copy.deepcopy(op[3])
                elif kind == "update":
                    table[doc_id].update(copy.deepcopy(op[3]))
                else:
                    table.pop(doc_id, None)

    def query(self, coll, filters=(), order_by=None, descending=False, limit=None):
        with self._Txn(self, write=False) as data:
            rows = [d for d in data.get(coll, {}).values() if _matches(d, filters)]
            if order_by:
                rows = [r for r in rows if order_by in r]  # Firestore drops docs missing the ordered field
                rows.sort(key=lambda r: (r[order_by] is not None, r[order_by]), reverse=descending)
            if limit is not None:
                rows = rows[:limit]
            return copy.deepcopy(rows)

    def count(self, coll, filters=()):
        with self._Txn(self, write=False) as data:
            return sum(1 for d in data.get(coll, {}).values() if _matches(d, filters))


# ----------------------------------------------------------------------------
# FirestoreBackend
# ----------------------------------------------------------------------------

class FirestoreBackend(Backend):
    """The client (and the google libraries) are created on first use, so importing a
    service never needs credentials; the configuration itself is validated up front
    in from_env()."""

    def __init__(self, project: str, database: str = "(default)", client=None):
        self._project, self._database, self._client = project, database, client
        self._init_lock = threading.Lock()

    @classmethod
    def from_env(cls) -> "FirestoreBackend":
        project = os.environ.get("FEDHEAL_FIREBASE_PROJECT_ID", "").strip() or None
        if project is None and not os.environ.get("FIRESTORE_EMULATOR_HOST"):
            # Without an explicit project the client would silently guess from ambient credentials.
            raise RuntimeError("FEDHEAL_FIREBASE_PROJECT_ID must be set to use Firestore "
                               "(or set FIRESTORE_EMULATOR_HOST to use the local emulator)")
        database = os.environ.get("FEDHEAL_FIRESTORE_DATABASE", "").strip() or "(default)"
        return cls(project or "demo-fedheal", database)

    @property
    def _c(self):
        if self._client is None:
            with self._init_lock:
                if self._client is None:
                    from google.cloud import firestore
                    self._client = firestore.Client(project=self._project, database=self._database)
        return self._client

    @staticmethod
    def _already_exists():
        from google.api_core import exceptions as gexc
        return gexc.AlreadyExists

    @staticmethod
    def _not_found():
        from google.api_core import exceptions as gexc
        return gexc.NotFound

    def _ref(self, coll, doc_id):
        return self._c.collection(coll).document(doc_id)

    def get(self, coll, doc_id):
        snap = self._ref(coll, doc_id).get()
        return snap.to_dict() if snap.exists else None

    def set(self, coll, doc_id, data):
        self._ref(coll, doc_id).set(data)

    def delete(self, coll, doc_id):
        self._ref(coll, doc_id).delete()

    def commit(self, ops):
        if len(ops) > 500:
            raise ValueError("a Firestore batch holds at most 500 writes; use bulk_set for large inserts")
        batch = self._c.batch()
        for op in ops:
            kind, coll, doc_id = op[0], op[1], op[2]
            ref = self._ref(coll, doc_id)
            if kind == "create": batch.create(ref, op[3])
            elif kind == "set": batch.set(ref, op[3])
            elif kind == "update": batch.update(ref, op[3])
            elif kind == "delete": batch.delete(ref)
            else: raise ValueError(f"unknown op {kind!r}")
        try:
            batch.commit()
        except self._already_exists() as exc:
            raise AlreadyExists(str(exc)) from exc
        except self._not_found() as exc:   # `update` of a missing document: same error as LocalBackend
            raise KeyError(str(exc)) from exc

    def _query(self, coll, filters, order_by=None, descending=False, limit=None):
        from google.cloud import firestore
        from google.cloud.firestore_v1.base_query import FieldFilter

        q = self._c.collection(coll)
        for field, op, value in filters:
            q = q.where(filter=FieldFilter(field, op, value))
        if order_by:
            q = q.order_by(order_by, direction=(firestore.Query.DESCENDING if descending
                                                else firestore.Query.ASCENDING))
        if limit is not None:
            q = q.limit(limit)
        return q

    def query(self, coll, filters=(), order_by=None, descending=False, limit=None):
        return [d.to_dict() for d in self._query(coll, filters, order_by, descending, limit).stream()]

    def count(self, coll, filters=()):
        result = self._query(coll, filters).count().get()
        return int(result[0][0].value)


# ----------------------------------------------------------------------------
# Selection
# ----------------------------------------------------------------------------

def make_backend(*, local_default_path: str, is_local: bool, env: str) -> Backend:
    """
    FEDHEAL_DB_BACKEND = firestore | local | memory
      default: `local` (JSON file at FEDHEAL_LOCAL_STORE_PATH, else local_default_path) in development/test,
               `firestore` everywhere else.
    The local/memory stores have no access control and no durability guarantees, so they are
    refused outside development/test; and the Firestore emulator is refused in production.
    """
    choice = os.environ.get("FEDHEAL_DB_BACKEND", "").strip().lower() or ("local" if is_local else "firestore")
    if choice in ("local", "memory"):
        if not is_local:
            raise RuntimeError(f"FEDHEAL_DB_BACKEND={choice} is only allowed when FEDHEAL_ENV is development/test "
                               f"(got {env}); use FEDHEAL_DB_BACKEND=firestore")
        if choice == "memory":
            return LocalBackend(None)
        return LocalBackend(os.environ.get("FEDHEAL_LOCAL_STORE_PATH", "").strip() or local_default_path)
    if choice != "firestore":
        raise RuntimeError("FEDHEAL_DB_BACKEND must be one of: firestore, local, memory")
    if env == "production" and os.environ.get("FIRESTORE_EMULATOR_HOST"):
        raise RuntimeError("FIRESTORE_EMULATOR_HOST is set while FEDHEAL_ENV=production; refusing to use the emulator")
    if os.environ.get("FIRESTORE_EMULATOR_HOST"):
        logger.warning("Using the Firestore EMULATOR at %s (no persistence, no access control).",
                       os.environ["FIRESTORE_EMULATOR_HOST"])
    return FirestoreBackend.from_env()
