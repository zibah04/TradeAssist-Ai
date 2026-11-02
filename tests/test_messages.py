from dataclasses import replace

import pandas as pd
import pytest

from ngxintel.messages import headline_message, stock_message
from ngxintel.signals import Signal


def prices():
    return pd.DataFrame({"symbol": ["FAKE"] * 6,
                         "timestamp": pd.date_range("2026-01-01", periods=6),
                         "close": [100, 98, 96, 94, 92, 90]})


def signal(action="WAIT", source="CSV_USER"):
    return Signal("FAKE", "2026-01-06", "SWING", action, 90, None, None,
                  3, 4, "fixture", source)


def test_drop_does_not_turn_wait_into_buy():
    result = stock_message(prices(), signal())
    assert "fell 10.0%" in result.observation
    assert "2026-01-01" in result.observation and "2026-01-06" in result.observation
    assert result.title == "Wait and watch"
    assert "do not give a clear reason" in result.suggestion


def test_messages_do_not_use_future_or_another_stock():
    original = stock_message(prices(), signal())
    extra = pd.DataFrame({"symbol": ["FAKE", "OTHER"],
                          "timestamp": pd.to_datetime(["2026-01-07", "2026-01-06"]),
                          "close": [1000, 1]})
    assert stock_message(pd.concat([extra, prices()]), signal()) == original


@pytest.mark.parametrize("action,title", [("BUY", "Worth a closer look"),
                                         ("SELL", "Review shares you own")])
def test_suggestions_follow_existing_signal(action, title):
    result = stock_message(prices(), signal(action))
    assert result.title == title
    if action == "SELL":
        assert "If you own" in result.suggestion
        assert "what you paid" in result.suggestion


def test_rise_is_observed_not_a_peak_or_profit_claim():
    frame = prices()
    frame["close"] = [100, 102, 104, 106, 108, 110]
    result = stock_message(frame, signal())
    assert "rose 10.0%" in result.observation
    assert "does not mean the peak" in result.suggestion


def test_demo_and_observation_context_are_explicit():
    result = stock_message(prices(), signal(source="DEMO_SYNTHETIC"))
    assert "Fictional demo" in result.context
    assert "not a live quote" in result.context
    assert "2026-01-06" in result.context


@pytest.mark.parametrize("value", [float("nan"), float("inf"), 0, -1])
def test_unusable_prices_do_not_invent_change(value):
    frame = prices()
    frame["close"] = frame["close"].astype(float)
    frame.loc[0, "close"] = value
    result = stock_message(frame, signal())
    assert "not enough usable price history" in result.observation


def test_short_history_and_missing_volume_explain_wait():
    result = stock_message(prices().tail(1), replace(signal(), strength=0))
    assert "not enough usable price history" in result.observation
    assert "Wait for more information" in result.suggestion


def test_news_warning_is_not_a_price_prediction():
    assert "does not establish that this stock will fall" in headline_message("FAKE profit warning and debt loss")
    assert "does not establish that this stock will rise" in headline_message("FAKE profit growth dividend")
    assert "closer read" in headline_message("FAKE holds annual meeting")
