"""Wat een codecheck doet terwijl hij draait, voor de pagina om mee te kijken.

Een codecheck kan met een echt model even duren (per bewering een oordeel). Zolang hij loopt meldt hij hier de fase, het
document waar hij is, de tellers per oordeel en de beweringen die al getoetst zijn (met hun bewijs), zodat de pagina ze
meteen kan tonen en openen. Het volledige resultaat wordt hier ook bewaard zodra de run klaar is: een codecheck heeft
geen rij in de database, dus zonder de pagina die meekeek zou er na een herstart niets meer van over zijn. Het leeft in
het geheugen (KEEP_RUNS runs) en de pagina vraagt het op.
"""
from __future__ import annotations

import datetime as dt
import threading
from collections import OrderedDict, deque
from dataclasses import dataclass, field

#: Zoveel afgeronde runs blijven beschikbaar (resultaat + verloop).
KEEP_RUNS = 20

#: Zoveel regels van het verloop (fasen/documenten) worden bewaard.
FEED_SIZE = 40

#: De fasen in de volgorde waarin ze komen.
STAGES = ("start", "lezen", "toetsen", "klaar", "mislukt")


@dataclass
class CodecheckProgress:
    run_id: int
    workspace_id: int | None
    stage: str = "start"
    documents_total: int = 0
    documents_done: int = 0
    current_document: str | None = None
    checked: int = 0
    bevestigd: int = 0
    tegengesproken: int = 0
    niet_gevonden: int = 0
    error: str | None = None
    #: De al getoetste beweringen (CheckedClaim-objecten), in volgorde; de pagina toont ze live en klikbaar.
    results: list = field(default_factory=list)
    #: Het volledige CodecheckResult zodra de run klaar is (None zolang hij loopt).
    result: object | None = None
    started_at: str = field(default_factory=lambda: dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"))
    feed: deque = field(default_factory=lambda: deque(maxlen=FEED_SIZE))
    _next: int = 0

    @property
    def finished(self) -> bool:
        return self.stage in ("klaar", "mislukt")


class CodecheckProgressRegistry:
    def __init__(self) -> None:
        self._runs: "OrderedDict[int, CodecheckProgress]" = OrderedDict()
        self._lock = threading.Lock()
        self._next_id = 0

    def start(self, workspace_id: int | None) -> CodecheckProgress:
        with self._lock:
            self._next_id += 1
            progress = CodecheckProgress(run_id=self._next_id, workspace_id=workspace_id)
            self._runs[progress.run_id] = progress
            while len(self._runs) > KEEP_RUNS:
                self._runs.popitem(last=False)
            return progress

    def update(self, run_id: int | None, **fields) -> None:
        if run_id is None:
            return
        with self._lock:
            progress = self._runs.get(run_id)
            if progress is not None:
                for key, value in fields.items():
                    setattr(progress, key, value)

    def event(self, run_id: int | None, kind: str, text: str) -> None:
        """Een regel in het verloop: ``kind`` is document, claim of stage."""
        if run_id is None:
            return
        with self._lock:
            progress = self._runs.get(run_id)
            if progress is not None:
                progress._next += 1
                progress.feed.append(
                    {
                        "n": progress._next,
                        "at": dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"),
                        "kind": kind,
                        "text": text[:240],
                    }
                )

    def add_result(self, run_id: int | None, claim) -> None:
        """Een getoetste bewering: meetellen en bewaren zodat de pagina hem meteen toont."""
        if run_id is None:
            return
        with self._lock:
            progress = self._runs.get(run_id)
            if progress is None:
                return
            progress.results.append(claim)
            progress.checked += 1
            verdict = getattr(claim, "verdict", None)
            if verdict in ("bevestigd", "tegengesproken", "niet_gevonden"):
                setattr(progress, verdict, getattr(progress, verdict) + 1)
            progress._next += 1
            progress.feed.append(
                {
                    "n": progress._next,
                    "at": dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"),
                    "kind": "claim",
                    "text": f"{getattr(claim, 'filename', '')}: {getattr(claim, 'statement', '')[:160]}",
                }
            )

    def finish(self, run_id: int | None, result) -> None:
        with self._lock:
            progress = self._runs.get(run_id) if run_id is not None else None
            if progress is not None:
                progress.result = result
                progress.stage = "klaar"
                progress.current_document = None

    def fail(self, run_id: int | None, error: str) -> None:
        with self._lock:
            progress = self._runs.get(run_id) if run_id is not None else None
            if progress is not None:
                progress.error = error
                progress.stage = "mislukt"
                progress.current_document = None

    def get(self, run_id: int) -> CodecheckProgress | None:
        with self._lock:
            return self._runs.get(run_id)

    def running_for(self, workspace_id: int | None) -> CodecheckProgress | None:
        with self._lock:
            for progress in reversed(self._runs.values()):
                if progress.workspace_id == workspace_id and not progress.finished:
                    return progress
        return None

    def snapshot(self, progress: CodecheckProgress, since: int = 0) -> dict:
        """De stand en (het nieuwe deel van) het verloop; het resultaat zodra de run klaar is."""
        with self._lock:
            return {
                "run_id": progress.run_id,
                "stage": progress.stage,
                "finished": progress.finished,
                "documents_total": progress.documents_total,
                "documents_done": progress.documents_done,
                "current_document": progress.current_document,
                "checked": progress.checked,
                "bevestigd": progress.bevestigd,
                "tegengesproken": progress.tegengesproken,
                "niet_gevonden": progress.niet_gevonden,
                "error": progress.error,
                "started_at": progress.started_at,
                "results": [c.model_dump() if hasattr(c, "model_dump") else c for c in progress.results],
                "result": progress.result.model_dump() if hasattr(progress.result, "model_dump") else progress.result,
                "feed": [e for e in progress.feed if e["n"] > since],
                "last": progress._next,
            }


codecheck_progress = CodecheckProgressRegistry()
