from app.services.config_service import get_config_service
from app.services.grader_service import GRADING_GRAMMAR, GraderService


def test_grading_grammar_is_canonical_json_only():
    expected = 'root ::= "{" "\\"relevance\\"" ":" value "}"\nvalue ::= "\\"yes\\"" | "\\"no\\""'
    assert GRADING_GRAMMAR == expected


def test_parse_grading_response_accepts_canonical_yes():
    service = GraderService(config=get_config_service())
    result = service._parse_grading_response("doc-1", '{"relevance":"yes"}', threshold=0.15)

    assert result.relevant is True
    assert result.score == 1.0


def test_parse_grading_response_accepts_canonical_no():
    service = GraderService(config=get_config_service())
    result = service._parse_grading_response("doc-2", '{"relevance":"no"}', threshold=0.15)

    assert result.relevant is False
    assert result.score == 0.0
