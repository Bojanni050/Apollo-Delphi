from app.services.ask.service import (
    Source,
    best_sentence,
    build_prompt,
    extractive_answer,
    numbers_in,
    parse_citations,
    unsupported_numbers,
)


def _src(n, text, filename="doc.txt", page=None):
    return Source(n=n, chunk_id=100 + n, document_id=n, document_filename=filename, page_number=page, section=None, excerpt=text)


def test_parse_citations_keeps_valid_markers_in_first_use_order():
    text, cited, invalid = parse_citations("A is true [2]. B too [1][2]. C [3].", 3)
    assert text == "A is true [2]. B too [1][2]. C [3]."
    assert cited == [2, 1, 3] and invalid == []


def test_parse_citations_removes_markers_that_point_at_nothing():
    text, cited, invalid = parse_citations("Budget is 5 [1]. Also this [7]. And that [0].", 2)
    assert cited == [1] and invalid == [7, 0]
    assert "[7]" not in text and "[0]" not in text and "[1]" in text
    assert text == "Budget is 5 [1]. Also this. And that."


def test_parse_citations_handles_comma_lists_and_partially_invalid_lists():
    text, cited, invalid = parse_citations("Both agree [1, 2]. One is bogus [2, 9].", 2)
    assert cited == [1, 2] and invalid == [9]
    assert text == "Both agree [1][2]. One is bogus [2]."


def test_parse_citations_text_without_markers():
    assert parse_citations("No sources here.", 3) == ("No sources here.", [], [])


def test_numbers_ignore_separators_and_citation_markers():
    assert numbers_in("Budget 250,000 EUR [1], also 250.000 and 7 people [2].") == {"250000", "7"}


def test_unsupported_numbers_only_flags_numbers_missing_from_the_sources():
    sources = ["The budget is 250000 EUR for 6 people.", "Delivery on 15 March 2025."]
    assert unsupported_numbers("It costs 250,000 EUR [1] and ships 15 March 2025 [2].", sources) == []
    assert unsupported_numbers("It costs 999,999 EUR [1].", sources) == ["999999"]
    assert unsupported_numbers("There are 7 of them.", sources) == [], "single digits are too noisy to flag"


def test_best_sentence_picks_the_overlapping_sentence_and_reports_no_overlap():
    text = "The weather is nice. The total approved budget is 25000 EUR. Lunch is at noon."
    assert best_sentence("What is the total approved budget?", text) == ("The total approved budget is 25000 EUR.", 3)
    assert best_sentence("completely unrelated giraffes", text)[1] == 0


def test_extractive_answer_cites_and_orders_by_overlap_and_returns_none_without_match():
    sources = [_src(1, "Lunch is at noon."), _src(2, "The total approved budget is 25000 EUR."), _src(3, "Budget talks are on Friday.")]
    answer = extractive_answer("total approved budget", sources)
    assert answer.startswith("The total approved budget is 25000 EUR. [2]")
    assert "[1]" not in answer
    assert extractive_answer("giraffes", sources) is None


def test_build_prompt_numbers_sources_and_names_their_files():
    prompt = build_prompt("What?", [_src(1, "Alpha.", "a.txt", page=3), _src(2, "Beta.", "b.txt")])
    assert "[1] (file: a.txt, page 3)\nAlpha." in prompt and "[2] (file: b.txt)\nBeta." in prompt
    assert prompt.rstrip().endswith("Question: What?")


from app.services.ask.service import Turn, build_prompt, build_rewrite_prompt, fallback_standalone, strip_citations


def test_strip_citations_removes_markers_and_the_gap_they_leave():
    assert strip_citations("The budget is 250000 EUR [1][2]. Repairs are included [2].") == "The budget is 250000 EUR. Repairs are included."


def test_fallback_standalone_puts_the_previous_topic_in_front():
    assert fallback_standalone([], "Who is the sponsor?") == "Who is the sponsor?"
    turns = [Turn("What is the harbour budget?", "250000 EUR [1]")]
    assert fallback_standalone(turns, "And when is it due?") == "What is the harbour budget? And when is it due?"


def test_fallback_standalone_builds_on_an_earlier_rewrite():
    turns = [Turn("And when is it due?", "In May.", standalone="What is the harbour budget? And when is it due?")]
    assert fallback_standalone(turns, "Who approved it?").startswith("What is the harbour budget? And when is it due?")


def test_prompt_marks_the_conversation_as_context_and_drops_old_citation_numbers():
    turns = [Turn("What is the budget?", "It is 250000 EUR [1].")]
    prompt = build_prompt("And when?", [], turns, standalone="When is the budget due?")
    assert "NOT a source" in prompt and "A: It is 250000 EUR." in prompt and "[1]" not in prompt
    assert "Question: And when?" in prompt and "When is the budget due?" in prompt
    assert "Conversation" not in build_prompt("Q?", [])


def test_rewrite_prompt_contains_the_turns_and_the_last_question():
    prompt = build_rewrite_prompt([Turn("What is the budget?", "250000 EUR [1]")], "And when?")
    assert "Q: What is the budget?" in prompt and "A: 250000 EUR" in prompt and prompt.endswith("Last question: And when?")
