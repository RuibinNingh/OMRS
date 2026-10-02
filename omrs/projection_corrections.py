"""SQL 修正索引；集合接口仅为投影/历史调用方兼容，不缓存全部修正。"""
from collections.abc import Mapping, Set
from contextlib import contextmanager
import json

from .ledger import connect


class _SQLView:
    def __init__(self, vault, db=None):
        self.vault, self.db = vault, db

    @contextmanager
    def connection(self):
        if self.db is not None:
            yield self.db
        else:
            with connect(self.vault) as db:
                yield db


class CorrectionSet(_SQLView, Set):
    def __init__(self, vault, kind, db=None):
        super().__init__(vault, db)
        self.kind = kind

    def __contains__(self, key):
        if not key:
            return False
        with self.connection() as db:
            if self.kind == "session":
                return db.execute("SELECT 1 FROM projection_session_corrections WHERE session_id=? AND retracted=1", (key,)).fetchone() is not None
            return db.execute("SELECT 1 FROM projection_review_corrections WHERE review_key=? AND status=?", (key, self.kind)).fetchone() is not None

    def __iter__(self):
        with self.connection() as db:
            if self.kind == "session":
                rows = db.execute("SELECT session_id FROM projection_session_corrections WHERE retracted=1")
            else:
                rows = db.execute("SELECT review_key FROM projection_review_corrections WHERE status=?", (self.kind,))
            for row in rows:
                yield row[0]

    def __len__(self):
        with self.connection() as db:
            if self.kind == "session":
                return db.execute("SELECT COUNT(*) FROM projection_session_corrections WHERE retracted=1").fetchone()[0]
            return db.execute("SELECT COUNT(*) FROM projection_review_corrections WHERE status=?", (self.kind,)).fetchone()[0]


class ReplacementMap(_SQLView, Mapping):
    def __getitem__(self, key):
        with self.connection() as db:
            row = db.execute("SELECT replacement_json FROM projection_review_corrections WHERE review_key=? AND replacement_json IS NOT NULL", (key,)).fetchone()
            if row is None:
                raise KeyError(key)
            return json.loads(row[0])

    def __iter__(self):
        with self.connection() as db:
            for row in db.execute("SELECT review_key FROM projection_review_corrections WHERE replacement_json IS NOT NULL"):
                yield row[0]

    def __len__(self):
        with self.connection() as db:
            return db.execute("SELECT COUNT(*) FROM projection_review_corrections WHERE replacement_json IS NOT NULL").fetchone()[0]

    def effective(self, key, review):
        with self.connection() as db:
            row = db.execute("SELECT status,replacement_json FROM projection_review_corrections WHERE review_key=?", (key,)).fetchone()
        if row is None:
            return review
        if row["status"] == "retracted":
            return None
        return {**review, **json.loads(row["replacement_json"])} if row["replacement_json"] is not None else review


def install(vault, state, db=None):
    state["retracted_sessions"] = CorrectionSet(vault, "session", db)
    state["retracted_reviews"] = CorrectionSet(vault, "retracted", db)
    state["restored_reviews"] = CorrectionSet(vault, "restored", db)
    state["review_replacements"] = ReplacementMap(vault, db)


def bind(state, db=None):
    for key in ("retracted_sessions", "retracted_reviews", "restored_reviews", "review_replacements"):
        if isinstance(state.get(key), _SQLView):
            state[key].db = db
