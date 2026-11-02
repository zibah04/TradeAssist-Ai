"""Plain-language explanations of observed prices and existing research signals."""
from dataclasses import dataclass
import math

import pandas as pd

from .signals import Signal
from .news import headline_tag


ACTION_LABELS = {
    "BUY": "Worth a closer look",
    "SELL": "Review shares you own",
    "WAIT": "Wait and watch",
}


@dataclass(frozen=True)
class StockMessage:
    title: str
    observation: str
    suggestion: str
    context: str


def stock_message(bars: pd.DataFrame, signal: Signal) -> StockMessage:
    """Explain only this symbol's observations available at the signal timestamp.

    A price fall alone never produces a buy suggestion. The existing signal
    engine remains the sole source of the research suggestion.
    """
    history = bars[(bars.symbol == signal.symbol) &
                   (bars.timestamp <= pd.Timestamp(signal.signal_time))]
    history = history.sort_values("timestamp").tail(6)
    observation = "There is not enough usable price history to describe a recent change."
    if len(history) >= 2:
        first, last = float(history.close.iloc[0]), float(history.close.iloc[-1])
        if math.isfinite(first) and math.isfinite(last) and first > 0 and last > 0:
            change = (last / first - 1) * 100
            start = pd.Timestamp(history.timestamp.iloc[0]).isoformat(sep=" ")
            end = pd.Timestamp(history.timestamp.iloc[-1]).isoformat(sep=" ")
            movement = (f"fell {abs(change):.1f}%" if change < 0 else
                        f"rose {change:.1f}%" if change > 0 else "was unchanged")
            observation = f"{signal.symbol}'s recorded price {movement} between {start} and {end}."
    if signal.action == "BUY":
        suggestion = ("The price checks suggest this may be worth researching as a possible buy. "
                      "Check the latest price and company news before deciding.")
    elif signal.action == "SELL":
        suggestion = ("The price checks suggest weakness. If you own these shares, consider reviewing "
                      "whether to keep or sell them. A profit depends on what you paid and your costs.")
    elif signal.strength == 0:
        suggestion = ("Wait for more information. There may be too little price history or too little "
                      "information about how many shares are being traded.")
    else:
        suggestion = ("The price checks do not give a clear reason to buy or sell. "
                      "A price drop alone does not mean a bargain, and a rise does not mean the peak.")
    demo = "Fictional demo — practice only. " if signal.source == "DEMO_SYNTHETIC" else ""
    context = (f"{demo}Source: {signal.source}. Latest observation: {signal.signal_time}. "
               "Based on loaded prices, not a live quote. Future prices can rise or fall.")
    return StockMessage(ACTION_LABELS[signal.action], observation, suggestion, context)


def headline_message(title: str) -> str:
    """Describe a headline's wording without turning it into a price forecast."""
    tag = headline_tag(title)
    if tag == "Negative terms":
        return ("This headline contains possible warning signs. Read the source and check which "
                "company it refers to. It does not establish that this stock will fall.")
    if tag == "Positive terms":
        return ("This headline may describe encouraging news. Read the source to check the details. "
                "It does not establish that this stock will rise.")
    return "This headline needs a closer read; its wording does not clearly point to good or bad news."
