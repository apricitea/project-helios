from unittest.mock import MagicMock, patch

from project_helios.alert.llm import FALLBACK_INSIGHT, generate_insight


def test_no_api_key_returns_fallback(monkeypatch):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    assert generate_insight({"churn": 0.1}) == FALLBACK_INSIGHT


def test_api_error_returns_fallback(monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-test")
    with patch("anthropic.Anthropic") as mock_anthropic:
        mock_anthropic.return_value.messages.create.side_effect = RuntimeError("boom")
        assert generate_insight({"churn": 0.1}) == FALLBACK_INSIGHT


def test_refusal_returns_fallback(monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-test")
    mock_response = MagicMock(stop_reason="refusal", content=[])
    with patch("anthropic.Anthropic") as mock_anthropic:
        mock_anthropic.return_value.messages.create.return_value = mock_response
        assert generate_insight({"churn": 0.1}) == FALLBACK_INSIGHT


def test_unparseable_json_returns_fallback(monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-test")
    text_block = MagicMock(type="text", text="not json")
    mock_response = MagicMock(stop_reason="end_turn", content=[text_block])
    with patch("anthropic.Anthropic") as mock_anthropic:
        mock_anthropic.return_value.messages.create.return_value = mock_response
        assert generate_insight({"churn": 0.1}) == FALLBACK_INSIGHT


def test_successful_response_parses_insight(monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-test")
    text_block = MagicMock(
        type="text",
        text='{"summary": "Churn ticked up.", "watch_items": ["Watch postpaid segment"]}',
    )
    mock_response = MagicMock(stop_reason="end_turn", content=[text_block])
    with patch("anthropic.Anthropic") as mock_anthropic:
        mock_anthropic.return_value.messages.create.return_value = mock_response
        result = generate_insight({"churn": 0.1})
    assert result["summary"] == "Churn ticked up."
    assert result["watch_items"] == ["Watch postpaid segment"]
