"""Index documents in the background: read them all quickly first, embed them one after the other afterwards.

Indexing has two very different steps (see IndexingService). Reading a document (extract, chunk, store the fragments) takes a
fraction of a second; embedding its fragments takes seconds per fragment on a CPU. A queue that did both per document made a
folder of 100 files unusable for half an hour. Now:

* every document is *read* first (the queue always prefers that step), so within seconds the whole folder can be read in the
  reading pane and searched by words;
* the *embedding* then goes on in the background, one document at a time (parallel requests were measured to be no faster:
  the model uses all cores), and semantic search gains the fragments as they are done.

The queue lives in memory: documents that are still ``pending`` or ``parsed`` after a restart are simply queued again.
"""
from __future__ import annotations

import asyncio
import itertools
import time
from dataclasses import dataclass, field

from app.core.logging import get_logger
from app.db.session import SessionLocal
from app.models import Document

log = get_logger(__name__)

READ, EMBED = 0, 1  # priorities: reading before embedding


@dataclass
class QueueStatus:
    #: A batch is running: something is queued or being worked on.
    active: bool
    #: Documents queued since the batch started; how many are read, how many are completely indexed, how many failed.
    total: int
    parsed: int
    done: int
    failed: int
    #: "lezen" or "embedden" while a document is being worked on, and which one.
    phase: str | None
    current: str | None
    #: Seconds of embedding per document so far in this batch (None before the first one is done).
    seconds_per_document: float | None
    errors: list[dict] = field(default_factory=list)


class IndexQueue:
    def __init__(self) -> None:
        self._loop: asyncio.AbstractEventLoop | None = None
        self._queue: asyncio.PriorityQueue | None = None
        self._task: asyncio.Task | None = None
        self._queued: set[int] = set()
        self._sequence = itertools.count()
        self._reset_batch()

    def _reset_batch(self) -> None:
        self.total = 0
        self.parsed = 0
        self.done = 0
        self.failed = 0
        self.phase: str | None = None
        self.current: str | None = None
        self.errors: list[dict] = []
        self._embed_seconds = 0.0
        self._embedded = 0

    def _ensure_worker(self) -> None:
        loop = asyncio.get_running_loop()
        if self._loop is not loop:  # a new event loop (a restarted server, a test): start over on it
            if self._task is not None and not self._task.done():
                self._task.cancel()
            self._loop, self._queue, self._task = loop, asyncio.PriorityQueue(), None
            self._queued.clear()
            self._reset_batch()
        if self._task is None or self._task.done():
            self._task = loop.create_task(self._work())

    def _put(self, priority: int, document_id: int) -> None:
        assert self._queue is not None
        self._queue.put_nowait((priority, next(self._sequence), document_id))

    def enqueue(self, document_ids: list[int]) -> int:
        """Queue documents (each only once). Must be called from inside the event loop. Returns how many were added."""
        self._ensure_worker()
        if not self._queued and self.current is None:  # nothing running: this is a new batch
            self._reset_batch()
        added = 0
        for document_id in document_ids:
            if document_id not in self._queued:
                self._queued.add(document_id)
                self._put(READ, document_id)
                self.total += 1
                added += 1
        return added

    async def _work(self) -> None:
        assert self._queue is not None
        while True:
            priority, _, document_id = await self._queue.get()
            started = time.monotonic()
            finished = False
            try:
                finished = await (self._read(document_id) if priority == READ else self._embed(document_id, started))
            except Exception:  # noqa: BLE001 - one document must never stop the queue
                log.exception("Indexing document %s failed", document_id)
                self.failed += 1
                finished = True
            finally:
                self.phase = self.current = None
                if finished:
                    self._queued.discard(document_id)

    def _fail(self, doc: Document) -> None:
        self.failed += 1
        self.errors.append({"document_id": doc.id, "filename": doc.filename, "error": doc.error_message})

    async def _read(self, document_id: int) -> bool:
        """Step 1. Returns True when the document needs nothing more (finished, or failed)."""
        from app.services.documents.indexer import IndexingService

        db = SessionLocal()
        try:
            doc = db.get(Document, document_id)
            if doc is None:
                self.done += 1
                return True
            self.phase, self.current = "lezen", doc.filename
            if doc.indexing_status != "parsed":  # an already parsed document only has to be embedded
                doc = await IndexingService().parse_document(db, document_id)
            if doc.indexing_status == "failed":
                self._fail(doc)
                return True
            self.parsed += 1
            if doc.indexing_status == "indexed":  # every fragment already had its vector
                self.done += 1
                return True
            self._put(EMBED, document_id)
            return False
        finally:
            db.close()

    async def _embed(self, document_id: int, started: float) -> bool:
        """Step 2. Returns True when the document is finished or failed."""
        from app.services.documents.indexer import IndexingService

        db = SessionLocal()
        try:
            doc = db.get(Document, document_id)
            if doc is None:
                self.done += 1
                return True
            self.phase, self.current = "embedden", doc.filename
            doc = await IndexingService().embed_document(db, document_id)
            self._embed_seconds += time.monotonic() - started
            if doc.indexing_status == "indexed":
                self.done += 1
                self._embedded += 1
            else:
                self._fail(doc)  # stays "parsed": readable and searchable by words, the reason is in error_message
            return True
        finally:
            db.close()

    def status(self) -> QueueStatus:
        return QueueStatus(
            active=bool(self._queued) or self.current is not None,
            total=self.total,
            parsed=self.parsed,
            done=self.done,
            failed=self.failed,
            phase=self.phase,
            current=self.current,
            seconds_per_document=round(self._embed_seconds / self._embedded, 2) if self._embedded else None,
            errors=self.errors[-20:],
        )


index_queue = IndexQueue()


def recover_interrupted_indexing() -> int:
    """A document left ``processing`` by a stopped app would refuse to be indexed again; make it ``pending`` again."""
    db = SessionLocal()
    try:
        count = db.query(Document).filter(Document.indexing_status == "processing").update({"indexing_status": "pending"})
        db.commit()
        return count
    finally:
        db.close()
