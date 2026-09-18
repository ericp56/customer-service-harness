from datetime import datetime

from src.tools import TOOL_NAME, TOOLS, get_current_datetime_iso


def test_date_time_tool_is_strict_and_returns_utc_iso_timestamp() -> None:
    assert TOOL_NAME == "getCurrentDateTimeIso"
    assert TOOLS[0]["strict"] is True
    assert TOOLS[0]["parameters"]["additionalProperties"] is False
    assert datetime.fromisoformat(get_current_datetime_iso()).tzinfo is not None
