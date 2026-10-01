"""Index documents in the background, one after the other.

Indexing is the slow part of adding documents: every fragment is embedded, and a real model on a CPU takes seconds per
fragment (about 1.7 s for Jina code 1.5B on a Ryzen 7 5800X), while storing the file takes a quarter of a second. Doing
both per file made a folder of 100 files take half an hour in which the page could not be left. Now the files are stored
at once and put in this queue; a single worker indexes them in the background, so the page is free and the progress can
be looked at from anywhere.

One worker, one document at a time: the embedding model uses all the cores anyway (parallel requests were measured to
be no faster), and one at a time keeps the order and the memory predictable. The queue lives in memory: documents that
are still ``pending`` after a restart are simply queued again.
"""
from __future__ import annotations

import asyncio
import time
from dataclasses import dataclass, field

from app.core.logging import get_logger
from app.db.session import SessionLocal
from app.models import Document

log = get_logger(__name__)


@dataclass
class QueueStatus:
    #: A batch is running: something is queued or being indexed.
    active: bool
    #: Documents queued since the batch started, how many are done, how many failed, and which one is being indexed.
    total: int
    done: int
    failed: int
    current: str | None
    #: Seconds per document so far in this batch (None before the first one finishes).
    seconds_per_document: float | None
    errors: list[dict] = field(default_factory=list)


class IndexQueue:
    def __init__(self) -> None:
        self._loop: asyncio.AbstractEventLoop | None = None
        self._queue: asyncio.Queue[int] | None = None
        self._task: asyncio.Task | None = None
        self._queued: set[int] = set()
        self._reset_batch()

    def _reset_batch(self) -> None:
        self.total = 0
        self.done = 0
        self.failed = 0
        self.current: str | None = None
        self.errors: list[dict] = []
        self._started: float | None = None
        self._busy_seconds = 0.0

    def _ensure_worker(self) -> None:
        loop = asyncio.get_running_loop()
        if self._loop is not loop:  # a new event loop (a restarted server, a test): start over on it
            if self._task is not None and not self._task.done():
                self._task.cancel()
            self._loop, self._queue, self._task = loop, asyncio.Queue(), None
            self._queued.clear()
            self._reset_batch()
        if self._task is None or self._task.done():
            self._task = loop.create_task(self._work())

    def enqueue(self, document_ids: list[int]) -> int:
        """Queue documents (each only once). Must be called from inside the event loop. Returns how many were added."""
        self._ensure_worker()
        assert self._queue is not None
        if not self._queued and self.current is None:  # nothing running: this is a new batch
            self._reset_batch()
        added = 0
        for document_id in document_ids:
            if document_id not in self._queued:
                self._queued.add(document_id)
                self._queue.put_nowait(document_id)
                self.total += 1
                added += 1
        return added

    async def _work(self) -> None:
        assert self._queue is not None
        while True:
            document_id = await self._queue.get()
            started = time.monotonic()
            self._started = self._started or started
            self.current = None
            try:
                await self._index(document_id)
            except Exception:  # noqa: BLE001 - one document must never stop the queue
                log.exception("Indexing document %s failed", document_id)
                self.failed += 1
            finally:
                self._queued.discard(document_id)
                self._busy_seconds += time.monotonic() - started
                self.current = None

    async def _index(self, document_id: int) -> None:
        from app.services.documents.indexer import IndexingService

        db = SessionLocal()
        try:
            doc = db.get(Document, document_id)
            if doc is None:
                self.done += 1
                return
            self.current = doc.filename
            result = await IndexingService().index_document(db, document_id)
            if result.indexing_status == "indexed":
                self.done += 1
            else:
                self.failed += 1
                self.errors.append({"document_id": document_id, "filename": doc.filename, "error": result.error_message})
        finally:
            db.close()

    def status(self) -> QueueStatus:
        finished = self.done + self.failed
        return QueueStatus(
            active=bool(self._queued) or self.current is not None,
            total=self.total,
            done=self.done,
            failed=self.failed,
            current=self.current,
            seconds_per_document=round(self._busy_seconds / finished, 2) if finished else None,
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
