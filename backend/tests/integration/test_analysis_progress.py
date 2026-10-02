"""What an analysis is doing while it runs: started in the background, followed through its progress."""
import io
import threading
import time

from app.services.analysis import service as analysis_service_module
from app.services.analysis.claim_extraction import HeuristicClaimExtractor
from app.services.analysis.progress import analysis_progress
from app.services.analysis.service import recover_interrupted_analyses

BUDGET_250 = "The harbour renovation budget is 250000 EUR. The quay repairs are included."
BUDGET_300 = "The harbour renovation budget is 300000 EUR. The quay repairs are included."


def _setup(client):
    ws = client.post("/api/workspaces", json={"name": "Voortgang"}).json()["id"]
    for name, text in [("plan.md", BUDGET_250), ("besluit.md", BUDGET_300)]:
        doc = client.post(
            "/api/documents", params={"workspace_id": ws}, files={"file": (name, io.BytesIO(text.encode()), "text/plain")}
        ).json()
        client.post(f"/api/documents/{doc['id']}/index")
    return ws


def _wait_finished(client, run_id, timeout=20):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        snap = client.get(f"/api/analysis/{run_id}/progress").json()
        if snap["finished"]:
            return snap
        time.sleep(0.05)
    raise AssertionError("the analysis did not finish")


class _GatedExtractor(HeuristicClaimExtractor):
    """Holds the analysis at its first fragment until the test lets go, so that a run can be looked at while it is running."""

    def __init__(self, gate, entered):
        self.gate, self.entered = gate, entered

    def extract(self, text):
        self.entered.set()
        assert self.gate.wait(10), "the test never let the analysis go"
        return super().extract(text)


def test_a_background_run_returns_at_once_and_its_progress_tells_what_it_found(client):
    ws = _setup(client)
    run = client.post("/api/analysis", params={"workspace_id": ws, "background": True}).json()
    assert run["status"] in ("running", "completed")
    snap = _wait_finished(client, run["id"])
    assert snap["stage"] == "klaar" and snap["error"] is None
    assert (snap["documents_total"], snap["documents_done"]) == (2, 2) and snap["chunks_total"] == snap["chunks_done"] >= 2
    assert snap["claims"] >= 2 and snap["contradictions"] >= 1
    kinds = {e["kind"] for e in snap["feed"]}
    assert {"stage", "document", "claim", "contradiction"} <= kinds
    assert any(e["text"].startswith("Lezen: plan.md (1 van 2)") for e in snap["feed"])
    # the run itself agrees with what the progress said
    done = client.get(f"/api/analysis/{run['id']}").json()
    assert done["status"] == "completed" and done["stats"]["claims"] == snap["claims"]


def test_the_feed_can_be_followed_from_where_you_stopped(client):
    ws = _setup(client)
    run = client.post("/api/analysis", params={"workspace_id": ws, "background": True}).json()
    snap = _wait_finished(client, run["id"])
    assert snap["feed"] and snap["last"] == snap["feed"][-1]["n"]
    later = client.get(f"/api/analysis/{run['id']}/progress", params={"since": snap["last"]}).json()
    assert later["feed"] == [], "nothing new after the last line"
    middle = client.get(f"/api/analysis/{run['id']}/progress", params={"since": snap["feed"][1]["n"]}).json()
    assert [e["n"] for e in middle["feed"]] == [e["n"] for e in snap["feed"][2:]]


def test_while_it_runs_the_progress_says_where_it_is_and_a_second_run_is_refused(client, monkeypatch):
    ws = _setup(client)
    gate, entered = threading.Event(), threading.Event()
    monkeypatch.setattr(analysis_service_module, "get_claim_extractor", lambda: _GatedExtractor(gate, entered))
    try:
        run = client.post("/api/analysis", params={"workspace_id": ws, "background": True}).json()
        assert run["status"] == "running"
        assert entered.wait(10)
        snap = client.get(f"/api/analysis/{run['id']}/progress").json()
        assert (snap["stage"], snap["finished"], snap["current_document"]) == ("lezen", False, "plan.md")
        assert snap["documents_total"] == 2 and snap["documents_done"] == 0
        running = client.get("/api/analysis/running", params={"workspace_id": ws}).json()
        assert running["run_id"] == run["id"], "the page can pick the running analysis up again"
        assert client.post("/api/analysis", params={"workspace_id": ws, "background": True}).status_code == 409
    finally:
        gate.set()
    assert _wait_finished(client, run["id"])["stage"] == "klaar"
    assert client.get("/api/analysis/running", params={"workspace_id": ws}).json() is None


def test_a_failing_analysis_says_so_in_the_progress_and_on_the_run(client, monkeypatch):
    ws = _setup(client)

    class Broken(HeuristicClaimExtractor):
        def extract(self, text):
            raise RuntimeError("the model is not reachable")

    monkeypatch.setattr(analysis_service_module, "get_claim_extractor", lambda: Broken())
    run = client.post("/api/analysis", params={"workspace_id": ws, "background": True}).json()
    snap = _wait_finished(client, run["id"])
    assert snap["stage"] == "mislukt" and "not reachable" in snap["error"]
    assert client.get(f"/api/analysis/{run['id']}").json()["status"] == "failed"
    assert any(e["text"].startswith("Mislukt") for e in snap["feed"])


def test_a_run_from_before_a_restart_is_described_by_its_row(client):
    ws = _setup(client)
    run = client.post("/api/analysis", params={"workspace_id": ws, "background": True}).json()
    _wait_finished(client, run["id"])
    analysis_progress._runs.clear()  # what a restart does to the memory
    snap = client.get(f"/api/analysis/{run['id']}/progress").json()
    assert snap["stage"] == "klaar" and snap["finished"] and snap["claims"] >= 2
    assert client.get("/api/analysis/99999/progress").status_code == 404


def test_the_progress_of_a_run_limited_to_groups_only_counts_those_documents(client):
    ws = _setup(client)
    run = client.post("/api/analysis", params=[("workspace_id", ws), ("groups", "bestaat-niet"), ("background", "true")]).json()
    snap = _wait_finished(client, run["id"])
    assert snap["documents_total"] == 0 and snap["stage"] == "klaar"


def test_an_analysis_that_was_running_when_the_app_stopped_is_marked_failed(client):
    ws = _setup(client)
    gate, entered = threading.Event(), threading.Event()
    original = analysis_service_module.get_claim_extractor
    analysis_service_module.get_claim_extractor = lambda: _GatedExtractor(gate, entered)
    try:
        run = client.post("/api/analysis", params={"workspace_id": ws, "background": True}).json()
        assert entered.wait(10)
        # "the app stops": the row is still running, but nothing will ever finish it
        gate.set()
        _wait_finished(client, run["id"])
    finally:
        analysis_service_module.get_claim_extractor = original
        gate.set()
    from app.db.session import SessionLocal
    from app.models import AnalysisRun

    db = SessionLocal()
    try:
        row = db.get(AnalysisRun, run["id"])
        row.status = "running"
        db.commit()
    finally:
        db.close()
    assert recover_interrupted_analyses() >= 1
    assert client.get(f"/api/analysis/{run['id']}").json()["status"] == "failed"
