from .cli import parse_limit


def legacy_limit(raw: str | None) -> int:
    """The legacy adapter treats an empty value as an unlimited request."""
    return parse_limit(raw)
