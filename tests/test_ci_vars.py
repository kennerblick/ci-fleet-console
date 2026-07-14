from app.ci_vars import parse_required_vars


def test_block_with_hints_and_defaults():
    content = """default:
  image: x
# CI-VARS:
#   SERVER_HOST = $CI_PROJECT_NAME
#   HOSTPORT = 22
#   ANSIBLE_USER          SSH-Benutzer
# CI-VARS-END
include: []
"""
    result = parse_required_vars(content)
    assert [v["name"] for v in result] == ["SERVER_HOST", "HOSTPORT", "ANSIBLE_USER"]
    assert result[0]["default"] == "$CI_PROJECT_NAME"
    assert result[1]["default"] == "22"
    assert result[2]["default"] is None
    assert result[2]["hint"] == "SSH-Benutzer"


def test_single_line_form():
    result = parse_required_vars("# CI-VARS: A B=x C")
    assert [(v["name"], v["default"]) for v in result] == [
        ("A", None), ("B", "x"), ("C", None)]


def test_block_ends_at_non_comment_and_dedupes():
    content = "# CI-VARS:\n#  A\nstages: [x]\n#  B\n# CI-VARS: A"
    result = parse_required_vars(content)
    assert [v["name"] for v in result] == ["A"]


def test_no_declaration():
    assert parse_required_vars("stages: [a]\njob:\n  script: [x]") == []
