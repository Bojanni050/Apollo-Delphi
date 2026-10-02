"""What an analysis is doing right now, for the page to show while it runs.

The analysis can take minutes with a real model (one call per fragment). The service reports here what it is busy with: the
stage, the document and fragment it is on, how many claims, open questions and contradictions it has found so far, and a short
feed of the latest findings. The page polls it. It lives in memory: it is only interesting while a run is going, and a finished
run is fully described by its row in the database.
"""
from __future__ import annotations

import datetime as dt
import threading
from collections import OrderedDict, deque
from dataclasses import dataclass, field

KEEP_RUNS = 20
FEED_SIZE = 60

#: The stages in the order they come.
STAGES = ("start", "lezen", "opslaan", "vergelijken", "klaar", "mislukt")


@dataclass
class AnalysisProgress:
    run_id: int
    workspace_id: int | None
    stage: str = "start"
    documents_total: int = 0
    documents_done: int = 0
    chunks_total: int = 0
    chunks_done: int = 0
    current_document: str | None = None
    claims: int = 0
    open_questions: int = 0
    contradictions: int = 0
    error: str | None = None
    started_at: str = field(default_factory=lambda: dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"))
    feed: deque = field(default_factory=lambda: deque(maxlen=FEED_SIZE))
    _next: int = 0

    @property
    def finished(self) -> bool:
        return self.stage in ("klaar", "mislukt")


class ProgressRegistry:
    def __init__(self) -> None:
        self._runs: "OrderedDict[int, AnalysisProgress]" = OrderedDict()
        self._lock = threading.Lock()

    def start(self, run_id: int, workspace_id: int | None) -> AnalysisProgress:
        with self._lock:
            progress = AnalysisProgress(run_id=run_id, workspace_id=workspace_id)
            self._runs[run_id] = progress
            while len(self._runs) > KEEP_RUNS:
                self._runs.popitem(last=False)
            return progress

    def update(self, run_id: int, **fields) -> None:
        with self._lock:
            progress = self._runs.get(run_id)
            if progress is not None:
                for key, value in fields.items():
                    setattr(progress, key, value)

    def add(self, run_id: int, **counters: int) -> None:
        """Count up: ``add(7, claims=1)``."""
        with self._lock:
            progress = self._runs.get(run_id)
            if progress is not None:
                for key, delta in counters.items():
                    setattr(progress, key, getattr(progress, key) + delta)

    def event(self, run_id: int, kind: str, text: str) -> None:
        """A line in the feed: ``kind`` is document, claim, question, contradiction or stage."""
        with self._lock:
            progress = self._runs.get(run_id)
            if progress is not None:
                progress._next += 1
                progress.feed.append(
                    {"n": progress._next, "at": dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"), "kind": kind, "text": text[:240]}
                )

    def get(self, run_id: int) -> AnalysisProgress | None:
        with self._lock:
            return self._runs.get(run_id)

    def running_for(self, workspace_id: int | None) -> AnalysisProgress | None:
        with self._lock:
            for progress in reversed(self._runs.values()):
                if progress.workspace_id == workspace_id and not progress.finished:
                    return progress
        return None

    def snapshot(self, progress: AnalysisProgress, since: int = 0) -> dict:
        """The numbers and the feed lines after ``since`` (the page asks for what it has not seen yet)."""
        with self._lock:
            return {
                "run_id": progress.run_id,
                "stage": progress.stage,
                "finished": progress.finished,
                "documents_total": progress.documents_total,
                "documents_done": progress.documents_done,
                "chunks_total": progress.chunks_total,
                "chunks_done": progress.chunks_done,
                "current_document": progress.current_document,
                "claims": progress.claims,
                "open_questions": progress.open_questions,
                "contradictions": progress.contradictions,
                "error": progress.error,
                "started_at": progress.started_at,
                "feed": [e for e in progress.feed if e["n"] > since],
                "last": progress._next,
            }


analysis_progress = ProgressRegistry()
