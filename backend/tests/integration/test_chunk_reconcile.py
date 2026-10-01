"""Re-indexing keeps unchanged chunks (id and embedding) and only embeds what is new."""
import asyncio

import pytest

from app.models import Document, DocumentChunk, Evidence
from app.services.chunking.chunker import Chunker
from app.services.documents import indexer as indexer_module
from app.services.documents.indexer import IndexingService
from app.services.extraction.base import ExtractionResult


class CountingEmbedder:
    """Deterministic fake: the vector encodes the text, so a reused vector is recognisable."""

    def __init__(self, model="m1", dim=4):
        self.model, self.dim, self.calls = model, dim, []

    async def embed_documents(self, texts):
        self.calls.append(list(texts))
        return [[float(len(t))] * self.dim for t in texts]


@pytest.fixture
def doc(db):
    d = Document(
        filename="a.md", stored_filename="a", file_type="md", file_size=1, content_hash="h", source_type="upload",
    )
    db.add(d)
    db.commit()
    return d


@pytest.fixture
def text(monkeypatch):
    """Control what 'extraction' returns; each section is one chunk."""
    current = {"sections": []}
    monkeypatch.setattr(
        indexer_module.document_service,
        "extract",
        lambda _doc: ExtractionResult(full_text="\n\n".join(f"# {h}\n{b}" for h, b in current["sections"])),
    )
    return current


def _index(db, doc, embedder):
    service = IndexingService(embedding_service=embedder, chunker=Chunker(chunk_size=500, overlap=0))
    result = asyncio.run(service.index_document(db, doc.id))
    assert result.indexing_status == "indexed", result.error_message
    db.expire_all()
    return service.last_stats


def _chunks(db, doc):
    return db.query(DocumentChunk).filter_by(document_id=doc.id).order_by(DocumentChunk.chunk_index).all()


def test_first_index_embeds_everything(db, doc, text):
    text["sections"] = [("One", "alpha"), ("Two", "beta")]
    emb = CountingEmbedder()
    stats = _index(db, doc, emb)
    assert (stats.added, stats.reused, stats.removed) == (2, 0, 0)
    assert len(emb.calls[0]) == 2


def test_unchanged_document_embeds_nothing_and_keeps_ids(db, doc, text):
    text["sections"] = [("One", "alpha"), ("Two", "beta")]
    _index(db, doc, CountingEmbedder())
    ids = [c.id for c in _chunks(db, doc)]

    emb = CountingEmbedder()
    stats = _index(db, doc, emb)
    assert (stats.added, stats.reused, stats.reembedded, stats.removed) == (0, 2, 0, 0)
    assert emb.calls == [], "no embedding call when nothing changed"
    assert [c.id for c in _chunks(db, doc)] == ids


def test_edit_embeds_only_the_changed_chunk(db, doc, text):
    text["sections"] = [("One", "alpha"), ("Two", "beta"), ("Three", "gamma")]
    _index(db, doc, CountingEmbedder())
    before = {c.section: c.id for c in _chunks(db, doc)}

    text["sections"] = [("One", "alpha"), ("Two", "beta changed a lot"), ("Three", "gamma")]
    emb = CountingEmbedder()
    stats = _index(db, doc, emb)
    assert (stats.added, stats.reused, stats.removed) == (1, 2, 1)
    assert emb.calls == [["# Two\nbeta changed a lot"]]
    after = {c.section: c.id for c in _chunks(db, doc)}
    assert after["One"] == before["One"] and after["Three"] == before["Three"]
    assert after["Two"] != before["Two"]


def test_inserting_a_section_shifts_positions_but_keeps_vectors(db, doc, text):
    text["sections"] = [("One", "alpha"), ("Two", "beta")]
    _index(db, doc, CountingEmbedder())
    two_id = next(c.id for c in _chunks(db, doc) if c.section == "Two")

    text["sections"] = [("Zero", "new"), ("One", "alpha"), ("Two", "beta")]
    emb = CountingEmbedder()
    stats = _index(db, doc, emb)
    assert (stats.added, stats.reused, stats.removed) == (1, 2, 0)
    chunks = _chunks(db, doc)
    assert [c.section for c in chunks] == ["Zero", "One", "Two"]
    assert [c.chunk_index for c in chunks] == [0, 1, 2]
    assert next(c.id for c in chunks if c.section == "Two") == two_id


def test_other_embedding_model_reembeds_in_place(db, doc, text):
    text["sections"] = [("One", "alpha")]
    _index(db, doc, CountingEmbedder("m1", 4))
    chunk_id = _chunks(db, doc)[0].id

    emb = CountingEmbedder("m2", 8)
    stats = _index(db, doc, emb)
    assert (stats.reused, stats.reembedded, stats.added, stats.removed) == (0, 1, 0, 0)
    chunk = _chunks(db, doc)[0]
    assert (chunk.id, chunk.embedding_model, chunk.embedding_dim, len(chunk.embedding)) == (chunk_id, "m2", 8, 8)


def test_duplicate_texts_are_matched_one_to_one(db, doc, text):
    text["sections"] = [("Same", "x"), ("Same", "x")]
    _index(db, doc, CountingEmbedder())
    text["sections"] = [("Same", "x"), ("Same", "x"), ("Same", "x")]
    emb = CountingEmbedder()
    stats = _index(db, doc, emb)
    assert (stats.added, stats.reused, stats.removed) == (1, 2, 0)
    assert len(_chunks(db, doc)) == 3


def test_evidence_keeps_pointing_at_unchanged_chunks(db, doc, text):
    text["sections"] = [("One", "alpha"), ("Two", "beta")]
    _index(db, doc, CountingEmbedder())
    chunks = {c.section: c for c in _chunks(db, doc)}
    kept = Evidence(document_id=doc.id, chunk_id=chunks["One"].id, original_text="alpha")
    db.add(kept)
    db.commit()

    text["sections"] = [("One", "alpha"), ("Two", "something else")]
    _index(db, doc, CountingEmbedder())
    assert db.get(Evidence, kept.id).chunk_id == chunks["One"].id


class Broken(CountingEmbedder):
    async def embed_documents(self, texts):
        raise RuntimeError("provider down")


def test_a_failing_embedding_keeps_the_document_readable_and_what_was_done(db, doc, text):
    text["sections"] = [("One", "alpha")]
    _index(db, doc, CountingEmbedder())
    first = _chunks(db, doc)[0]
    kept_id, kept_vector = first.id, list(first.embedding)

    text["sections"] = [("One", "alpha"), ("Two", "beta")]
    service = IndexingService(embedding_service=Broken(), chunker=Chunker(chunk_size=500, overlap=0))
    result = asyncio.run(service.index_document(db, doc.id))
    assert result.indexing_status == "parsed", "the fragments are stored and the document stays usable"
    assert "Embedden mislukt" in result.error_message and "provider down" in result.error_message
    db.expire_all()
    one, two = _chunks(db, doc)
    assert (one.id, list(one.embedding)) == (kept_id, kept_vector), "what already had its vector keeps it"
    assert two.content.endswith("beta") and two.embedding is None, "the new fragment is stored, without a vector yet"

    # asking again continues with what is missing
    emb = CountingEmbedder()
    done = asyncio.run(IndexingService(embedding_service=emb, chunker=Chunker(chunk_size=500, overlap=0)).embed_document(db, doc.id))
    assert done.indexing_status == "indexed" and done.error_message is None
    assert emb.calls == [["# Two\nbeta"]], "only the missing fragment is embedded"


def _service(embedder):
    return IndexingService(embedding_service=embedder, chunker=Chunker(chunk_size=500, overlap=0))


def test_parsing_stores_the_fragments_without_embedding_anything(db, doc, text):
    text["sections"] = [("One", "alpha"), ("Two", "beta")]
    emb = CountingEmbedder()
    parsed = asyncio.run(_service(emb).parse_document(db, doc.id))
    assert parsed.indexing_status == "parsed" and emb.calls == []
    db.expire_all()
    chunks = _chunks(db, doc)
    assert [c.section for c in chunks] == ["One", "Two"] and all(c.embedding is None for c in chunks)
    assert [(c.line_start, c.line_end) for c in chunks] == [(1, 2), (4, 5)], "readable and locatable at once"


def test_embedding_fills_in_the_vectors_a_batch_at_a_time(db, doc, text, monkeypatch):
    from app.core.config import get_settings

    monkeypatch.setattr(get_settings(), "embedding_batch_size", 2)
    text["sections"] = [(f"S{i}", f"body {i}") for i in range(5)]
    emb = CountingEmbedder()
    service = _service(emb)
    asyncio.run(service.parse_document(db, doc.id))
    done = asyncio.run(service.embed_document(db, doc.id))
    assert done.indexing_status == "indexed"
    assert [len(call) for call in emb.calls] == [2, 2, 1], "each batch is stored as it comes"
    db.expire_all()
    assert all(c.embedding is not None and c.embedding_model == "m1" for c in _chunks(db, doc))


def test_parsing_a_document_that_is_fully_embedded_leaves_it_indexed(db, doc, text):
    text["sections"] = [("One", "alpha")]
    _index(db, doc, CountingEmbedder())
    emb = CountingEmbedder()
    again = asyncio.run(_service(emb).parse_document(db, doc.id))
    assert again.indexing_status == "indexed" and emb.calls == []


def test_a_parsed_document_is_found_by_its_words_before_it_is_embedded(db, doc, text):
    from app.services.search.service import SearchService

    text["sections"] = [("Harbour", "The harbour budget is 250000 EUR."), ("Other", "Nothing about it.")]
    asyncio.run(_service(CountingEmbedder()).parse_document(db, doc.id))
    db.expire_all()
    assert db.get(Document, doc.id).indexing_status == "parsed"
    hits = asyncio.run(SearchService().search(db, "harbour budget", top_k=3, mode="keyword"))
    assert hits and hits[0].section == "Harbour" and hits[0].match == "keyword"
