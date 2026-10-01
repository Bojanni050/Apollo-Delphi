from app.services.search.service import bm25_rank, query_terms, rrf_fuse


def test_query_terms_keep_numbers_and_identifiers_and_drop_common_words():
    assert query_terms("What is the total approved budget of 250,000 EUR?") == ["total", "approved", "budget", "250,000", "eur"]
    assert query_terms("Where is ADR-0042 and Maria Chen?") == ["adr-0042", "maria", "chen"]
    assert query_terms("de het een en van") == [], "only common words: nothing worth searching"
    assert query_terms("budget Budget BUDGET") == ["budget"], "case-insensitive and de-duplicated"


def test_query_terms_are_capped():
    assert len(query_terms(" ".join(f"term{i}" for i in range(100)))) == 32


def test_rrf_a_chunk_found_by_both_legs_beats_one_found_by_a_single_leg():
    fused = rrf_fuse(semantic=[1, 2, 3], keyword=[3, 9, 1])
    order = [f.chunk_id for f in fused]
    assert order[:2] == [1, 3], "both legs found 1 and 3"
    by_id = {f.chunk_id: f for f in fused}
    assert by_id[1].sources == ["semantic", "keyword"] and by_id[2].sources == ["semantic"] and by_id[9].sources == ["keyword"]
    assert abs(by_id[1].score - (1 / 61 + 1 / 63)) < 1e-12


def test_rrf_each_leg_alone_still_returns_its_results_in_order():
    assert [f.chunk_id for f in rrf_fuse([5, 4, 3], [])] == [5, 4, 3]
    assert [f.chunk_id for f in rrf_fuse([], [7, 8])] == [7, 8]
    assert rrf_fuse([], []) == []


def test_rrf_is_deterministic_on_ties():
    # 1 is top of one leg, 2 is top of the other: equal scores, equal sources -> lower id first
    assert [f.chunk_id for f in rrf_fuse([2], [1])] == [1, 2]
    assert [f.chunk_id for f in rrf_fuse([1], [2])] == [1, 2], "the order does not depend on which leg found which"


def test_bm25_prefers_rare_terms_and_ignores_non_matching_chunks():
    docs = {
        1: "the budget is discussed in the meeting",
        2: "the budget for the quay wall is 250000 EUR",
        3: "nothing relevant here at all",
        4: "the budget budget budget again the budget",
    }
    ranked = bm25_rank(docs, ["budget", "250000"])
    assert ranked[0] == 2, "the rare number outweighs a repeated common word"
    assert 3 not in ranked and set(ranked) == {1, 2, 4}


def test_bm25_empty_inputs():
    assert bm25_rank({}, ["x"]) == [] and bm25_rank({1: "x"}, []) == []


from app.models import Document, DocumentChunk
from app.services.search.service import evidence_lines


def _chunk(content, start=10, end=14):
    return DocumentChunk(content=content, line_start=start, line_end=end)


def test_evidence_lines_narrow_to_the_quote():
    chunk = _chunk("Intro line\nThe budget is 250000 EUR.\nMore text\nand more\nlast")
    doc = Document(file_type="txt", source_type="upload")
    assert evidence_lines(doc, chunk, "The budget is 250000 EUR.") == (11, 11)
    assert evidence_lines(doc, chunk, "More text\nand more") == (12, 13)


def test_evidence_lines_fall_back_to_the_whole_chunk():
    doc = Document(file_type="md", source_type="upload")
    chunk = _chunk("alpha\nbeta")
    assert evidence_lines(doc, chunk, "something the model paraphrased") == (10, 14)
    assert evidence_lines(doc, chunk) == (10, 14)


def test_evidence_lines_start_at_the_first_line_with_text():
    chunk = _chunk("\n\nfirst\nsecond", start=3, end=4)  # line_start already skips the leading blank lines
    assert evidence_lines(Document(file_type="txt", source_type="upload"), chunk, "second") == (4, 4)


def test_evidence_lines_are_absent_when_not_citable_or_not_recorded():
    assert evidence_lines(Document(file_type="pdf", source_type="upload"), _chunk("x"), "x") == (None, None)
    assert evidence_lines(Document(file_type="md", source_type="github"), _chunk("x"), "x") == (None, None)
    assert evidence_lines(Document(file_type="txt", source_type="upload"), _chunk("x", None, None), "x") == (None, None)
