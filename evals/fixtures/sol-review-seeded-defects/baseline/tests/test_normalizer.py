from src.normalizer import first_normalized


def test_first_normalized_item() -> None:
    assert first_normalized(["  Alpha  ", "Beta"]) == "alpha"
