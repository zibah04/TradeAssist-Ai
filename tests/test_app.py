"""Framework interaction check using fictional prices and mocked news only."""
from pathlib import Path

import pandas as pd
from streamlit.testing.v1 import AppTest


def test_beginner_dashboard_and_news(monkeypatch, tmp_path):
    from ngxintel import ledger, news

    connect = ledger.connection
    monkeypatch.setattr(ledger, "connection", lambda: connect(tmp_path / "ideas.sqlite"))
    monkeypatch.setattr(news, "fetch_headlines", lambda symbol: pd.DataFrame([{
        "title": "FAKE profit warning and debt loss", "publisher": "Fictional publisher",
        "published": "2026-01-06", "url": "https://example.com/fictional-news",
    }]))
    app = AppTest.from_file(str(Path(__file__).resolve().parents[1] / "app.py"), default_timeout=30).run()
    assert not app.exception
    assert [tab.label for tab in app.tabs] == ["💡 Stock updates", "🧪 Try it on past prices",
                                              "📒 Saved ideas", "🗞️ News explained", "📁 How it works"]
    assert any("What should I know?" in h.value for h in app.subheader)
    assert any("Fictional demo" in c.value for c in app.caption)
    assert any(e.label == "Optional settings" and not e.proto.expanded for e in app.expander)
    next(b for b in app.button if b.label == "Find recent news").click().run()
    assert not app.exception
    assert any("does not establish that this stock will fall" in m.value for m in app.markdown)
    assert any("Fictional publisher" in c.value and "2026-01-06" in c.value for c in app.caption)
    assert app.get("link_button")[0].proto.url == "https://example.com/fictional-news"
    app.radio[0].set_value("DAY").run()
    assert not app.exception
    assert any("needs several prices" in e.value for e in app.error)
