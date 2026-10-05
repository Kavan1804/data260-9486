"""Counts SQL statements executed inside a `with count_queries()` block.

Used by the N+1 endpoints to report statements per request in the
X-SQL-Count response header. Session validation happens before the block,
so only the list query work is counted.
"""

from contextlib import contextmanager
from contextvars import ContextVar

from sqlalchemy import event

from .database import engine

_counter: ContextVar[list[int] | None] = ContextVar("sql_counter", default=None)


@event.listens_for(engine, "before_cursor_execute")
def _count(conn, cursor, statement, parameters, context, executemany):
    box = _counter.get()
    if box is not None:
        box[0] += 1


@contextmanager
def count_queries():
    box = [0]
    token = _counter.set(box)
    try:
        yield box
    finally:
        _counter.reset(token)
