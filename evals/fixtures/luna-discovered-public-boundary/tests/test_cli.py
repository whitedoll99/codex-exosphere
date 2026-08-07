from src.cli import DEFAULT_LIMIT, parse_limit


def test_empty_limit_uses_default_for_the_new_cli() -> None:
    assert parse_limit("") == DEFAULT_LIMIT
