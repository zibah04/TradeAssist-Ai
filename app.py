"""TradeAssist AI — practical research / prediction-tracking MVP."""
import os
import pandas as pd
import plotly.graph_objects as go
import streamlit as st
from dotenv import load_dotenv
from ngxintel.data import DataError, csv_to_bars, fetch_investo
from ngxintel.demo import generate_demo
from ngxintel.signals import calculate_signal, MIN_BARS
from ngxintel.backtest import run_backtest, metrics
from ngxintel.ledger import connection, record, evaluate, load, summary
from ngxintel.news import fetch_headlines, ai_news_brief, fetch_filings
from ngxintel.messages import ACTION_LABELS, stock_message, headline_message

load_dotenv()
st.set_page_config(page_title="TradeAssist AI", page_icon="📈", layout="wide", initial_sidebar_state="expanded")
st.markdown("""<style>
  .block-container {max-width: 1450px; padding-top: 2rem}
  h1,h2,h3 {letter-spacing: -.035em}
  [data-testid="stMetric"] {border:1px solid #334155; border-radius:12px; padding:14px}
  div[data-testid="stAlert"] {border-radius: 10px}
  .tag {display:inline-block; border:1px solid #365f7d; background: #0c2436;
       color:#b6e0ff; font-weight:600; padding:4px 12px; border-radius: 30px}
</style>""", unsafe_allow_html=True)

st.title("📈 TradeAssist AI")
st.caption("Understand share prices, explore ideas, and keep track of what happens next.")
st.info("Start with the practice demo or load your own prices. These are research ideas; profits are not guaranteed and the app never places trades.")

with st.sidebar:
    st.header("Get started")
    source_kind = st.selectbox("Where should prices come from?", ["Synthetic demo", "CSV upload", "Investo NGX API"],
                              format_func=lambda value: {"Synthetic demo": "Practice with fictional prices", "CSV upload": "Upload a price file (CSV)", "Investo NGX API": "Connect Investo daily prices"}[value])
    mode = st.radio("How long are you looking ahead?", ["SWING", "DAY"], horizontal=True,
                    format_func=lambda value: {"SWING": "Several days", "DAY": "Within one day"}[value],
                    help="Within one day needs several recorded prices during each day, not just a daily closing price.")
    st.caption("You can leave the settings below at their starting values.")
    with st.expander("Optional settings"):
        horizon = st.slider("How many future price records to check?", min_value=2, max_value=30,
                            value=5 if mode == "SWING" else 8,
                            help="A record is one row in your price file. Daily files have one record per trading day.")
        min_volume = st.number_input("Minimum average shares traded per record", min_value=0, max_value=50_000_000,
                                     value=20_000 if mode == "SWING" else 1000, step=1000)
        stop_pct = st.slider("Price drop to test before stopping (%)", 1.0, 12.0, 3.0, step=0.5) / 100
        reward_multiple = st.slider("Desired gain compared with the allowed drop", 1.0, 4.0, 2.0, step=0.25,
                                    help="For a possible buy, 2 means testing a 6% gain against a 3% drop.")
        roundtrip_bps = round(st.slider("Estimated buying and selling costs (%)", 0.0, 4.0, 1.0, step=0.1) * 100)
        st.caption("Costs are an example. Replace them with your own fees. These settings affect research calculations, not real orders.")

bars = None
source_id = {"Synthetic demo":"DEMO_SYNTHETIC", "CSV upload":"CSV_USER", "Investo NGX API":"INVESTO"}[source_kind]
if source_kind == "Synthetic demo":
    bars = generate_demo()
    st.warning("Practice mode: all companies and prices below are fictional. These messages are examples, not real buying or selling opportunities.")
elif source_kind == "CSV upload":
    upload = st.file_uploader("Upload CSV with date/timestamp, close, optional symbol/open/high/low/volume", type="csv")
    st.caption("Example: date,symbol,open,high,low,close,volume. Include real timestamps for DAY mode. Price data should be properly licensed.")
    if upload is not None:
        try:
            bars = csv_to_bars(upload)
        except Exception as exc:
            st.error(f"Could not read CSV: {exc}")
else:
    st.info("Connect daily prices from Investo. These are end-of-day records, not live prices. You need an Investo access key.")
    key = st.text_input("Investo API key", type="password", value=os.getenv("INVESTO_API_KEY", ""))
    syms = st.text_input("NGX tickers (comma-separated)", "GTCO, UBA, ZENITHBANK")
    days = st.select_slider("History lookback (calendar days)", options=[90, 180, 365, 730], value=365)
    if st.button("Fetch NGX historical prices", type="primary"):
        try:
            with st.spinner("Fetching market data…"):
                st.session_state["investo_bars"] = fetch_investo(
                    [s.strip() for s in syms.split(",") if s.strip()], key, days)
            st.success("NGX data loaded into this app session.")
        except Exception as exc:
            st.error(str(exc))
    bars = st.session_state.get("investo_bars")

if bars is None:
    st.info("Choose a data source above to begin. **Synthetic demo** works without any account or API key.")
    st.stop()

bars = bars.sort_values(["symbol", "timestamp"])
if bars.empty:
    st.stop()

# A day strategy must not quietly use end-of-day prices as if they were intraday.
def is_intraday(data):
    return bool(data.groupby([data.symbol, data.timestamp.dt.date]).size().max() >= 2)

if mode == "DAY" and not is_intraday(bars):
    st.error("Within one day needs several prices recorded during each trading day. This file has daily prices only. Choose Several days, or upload prices with times throughout the day.")
    st.stop()

symbols = sorted(bars.symbol.unique())
selected = st.selectbox("Which stock would you like to explore?", symbols)
frame = bars[bars.symbol == selected].copy().sort_values("timestamp").reset_index(drop=True)
source_info = f"Source: {source_kind} · Latest observation: {frame.timestamp.max()} · Price records: {len(frame)}"
st.caption(source_info)
if source_kind == "Investo NGX API":
    st.caption("Data: Investo — investo.ng · The latest observation is NOT a live tradeable quote.")

conn = connection()
tabs = st.tabs(["💡 Stock updates", "🧪 Try it on past prices", "📒 Saved ideas", "🗞️ News explained", "📁 How it works"])

with tabs[0]:
    st.subheader("What should I know?")
    st.caption("Updates appear here when you load prices or change settings. They are not background, phone, or email notifications.")
    signals = [calculate_signal(bars[bars.symbol == sym], mode, source_id, min_volume, stop_pct, reward_multiple)
               for sym in symbols]
    messages = {signal.symbol: stock_message(bars, signal) for signal in signals}
    selected_signal = next(signal for signal in signals if signal.symbol == selected)
    message = messages[selected]
    with st.container(border=True):
        st.subheader(f"{selected} · {message.title}")
        st.write(message.observation)
        st.write(message.suggestion)
        st.caption(message.context)
    st.subheader("Other stocks at a glance")
    for sym in symbols:
        if sym != selected:
            other = messages[sym]
            with st.container(border=True):
                st.write(f"**{sym} · {other.title}**")
                st.write(other.observation)
                st.write(other.suggestion)
                st.caption(other.context)
    if len(frame) >= 2:
        fig = go.Figure()
        fig.add_trace(go.Scatter(x=frame.timestamp, y=frame.close, name="Recorded price", mode="lines"))
        fig.update_layout(height=320, margin=dict(l=10, r=10, t=20, b=20),
                          yaxis_title="Price (₦)", xaxis_title="Date / time recorded")
        st.plotly_chart(fig, use_container_width=True)
    if st.button("Save current buy / sell research ideas", type="primary"):
        count = sum(record(conn, signal, horizon) for signal in signals)
        st.success(f"Saved {count} new idea(s). Wait-and-watch messages and duplicates are not saved. No shares were bought or sold.")
    st.caption("Saving an idea lets you check it later with newer prices in Saved ideas.")
    with st.expander("Show the numbers behind these messages"):
        tabrows = [{"Stock": signal.symbol, "Research suggestion": ACTION_LABELS[signal.action],
                    "Recorded price (₦)": round(signal.reference_price, 4),
                    "Checks aligned (not a probability)": f"{signal.strength}/{signal.strength_max}",
                    "Price goal (₦)": signal.target, "Price limit (₦)": signal.stop,
                    "Recorded at": signal.signal_time} for signal in signals]
        st.dataframe(pd.DataFrame(tabrows), hide_index=True, use_container_width=True)
        st.write(selected_signal.reason)
        st.caption("Four price checks must agree before a buy or sell idea appears. A sell idea means reviewing shares you already own, not borrowing shares to sell.")

with tabs[1]:
    st.subheader(f"What would have happened with past prices? · {selected}")
    st.caption("This test uses older prices to try the research rules. It assumes buying at the next recorded opening price and subtracts your estimated fees. Past results do not tell us what will happen next.")
    if len(frame) < MIN_BARS + horizon + 1:
        st.warning(f"This test needs at least {MIN_BARS + horizon + 1} price records. Please load more history.")
    else:
        trades, skipped = run_backtest(frame, mode, horizon, min_volume, stop_pct, reward_multiple,
                                       roundtrip_bps, source_id)
        stats = metrics(trades)
        c1, c2, c3, c4 = st.columns(4)
        c1.metric("Ideas checked", stats["evaluated"])
        c2.metric("Reached the price goal", f"{stats['hit_rate']:.1f}%" if stats["hit_rate"] is not None else "N/A")
        c3.metric("Simulated buys that made money", f"{stats['buy_win_rate']:.1f}%" if stats["buy_win_rate"] is not None else "N/A")
        c4.metric("Average simulated gain / loss after fees", f"{stats['mean_net_return']:+.2f}%" if stats["mean_net_return"] is not None else "N/A")
        if skipped:
            st.warning(f"Skipped {skipped} idea(s) because the next opening price was missing. We cannot test a purchase without that price.")
        if stats["evaluated"]:
            with st.expander("Detailed test results"):
                if stats["buys"]:
                    st.caption(f"Combining the simulated buys: {stats['total_compounded']:+.2f}%. Largest fall from a previous high in this simulation: {stats['max_drawdown']:.2f}%. This assumes reinvesting everything after each buy and excludes some real-world costs.")
                else:
                    st.caption("There were no simulated buys with a result. Sell ideas alone cannot show a buying profit.")
                st.dataframe(trades, hide_index=True, use_container_width=True)
            st.download_button("⬇️ Export backtest results CSV", trades.to_csv(index=False).encode(),
                               file_name=f"backtest_{selected.lower()}.csv", mime="text/csv")
        else:
            st.info("There are no completed ideas to show for these prices and settings. Try loading more price history.")
        st.caption("Gains and losses are calculated only for simulated buys. A sell idea means reviewing shares already owned. Actual fees, available buyers and sellers, and execution prices may change real results.")

with tabs[2]:
    st.subheader("Keep track of your research ideas")
    st.write("Save ideas in **Stock updates**. Later, load newer prices and press the button below to see what happened. Saved ideas keep their original details.")
    if st.button("Check saved ideas with newer prices"):
        n = evaluate(conn, bars, source_id)
        st.success(f"Checked {n} completed idea(s). Others still need newer prices.")
    historical = load(conn, source_id)
    report = summary(historical)
    cols = st.columns(4)
    cols[0].metric("Saved", report["total"])
    cols[1].metric("Checked", report["resolved"])
    cols[2].metric("Reached the price goal", f"{report['accuracy']:.1f}%" if report["accuracy"] is not None else "N/A")
    cols[3].metric("Waiting for results", report["pending"])
    if historical.empty:
        st.info("No ideas saved for this source yet. Save one in Stock updates to begin.")
    else:
        breakdown = []
        for strategy_name in ("SWING", "DAY"):
            for direction_name in ("BUY", "SELL"):
                segment = historical[(historical["mode"] == strategy_name) &
                                     (historical["action"] == direction_name)]
                s = summary(segment)
                if s["total"]:
                    breakdown.append({"Timeframe": {"SWING": "Several days", "DAY": "Within one day"}[strategy_name], "Idea": ACTION_LABELS[direction_name],
                        "Checked":s["resolved"], "Reached the goal":s["wins"],
                        "Reached the price goal (%)":round(s["accuracy"],1) if s["accuracy"] is not None else None,
                        "Waiting for results": s["pending"]})
        if breakdown:
            st.dataframe(pd.DataFrame(breakdown), hide_index=True, use_container_width=True)
        with st.expander("Show original saved records"):
            st.dataframe(historical, hide_index=True, use_container_width=True)
        st.download_button("⬇️ Export journal", historical.to_csv(index=False).encode(),
                           file_name="prediction_ledger.csv", mime="text/csv")
        st.caption("An idea succeeds in this check when its price goal is reached before its price limit. Running out of time counts as a missed goal; unfinished ideas are excluded. If both prices are touched in one record, we count the limit first. These are price checks, not proof of a profitable trade.")
        for k in ("SWING", "DAY"):
            m = summary(historical[historical["mode"] == k])
            if m["resolved"]:
                st.write(f"**{dict(SWING='Several days', DAY='Within one day')[k]}:** {m['wins']} of {m['resolved']} checked ideas reached their goal ({m['accuracy']:.1f}%).")

with tabs[3]:
    st.subheader(f"What is in the news? · {selected}")
    st.caption("These are article headlines, not verified facts or predictions. Some may refer to another company. News does not change the app’s price-based suggestions.")
    if st.button("Find recent news"):
        try:
            st.session_state["headlines"] = fetch_headlines(selected)
            st.session_state["headline_symbol"] = selected
            st.session_state.pop("ai_brief", None)
        except Exception as exc:
            st.error(str(exc))
    news = st.session_state.get("headlines")
    if news is not None and st.session_state.get("headline_symbol") == selected:
        if news.empty:
            st.info("No matching RSS headlines were returned.")
        else:
            for _, article in news.iterrows():
                with st.container(border=True):
                    st.write(headline_message(str(article["title"])))
                    st.text(str(article["title"]))
                    st.caption(f"Publisher: {article['publisher']} · Published: {article['published'] or 'Time not supplied'}")
                    url = str(article["url"])
                    if url.startswith("https://"):
                        st.link_button("Read the source", url)
            st.caption("Messages describe words in headlines only. They cannot establish that a stock will experience a serious drop or rise.")
            ai_key = st.text_input("Optional OpenAI API key for cautious headline brief",
                                  type="password", value=os.getenv("OPENAI_API_KEY", ""))
            if st.button("Explain these headlines in simple words"):
                if not ai_key.strip():
                    st.warning("Enter an OpenAI API key first for the optional explanation. Stock updates and news headlines do not need an AI key.")
                else:
                    try:
                        with st.spinner("Summarising unverified headlines…"):
                            st.session_state["ai_brief"] = ai_news_brief(
                                news, selected, ai_key, os.getenv("OPENAI_MODEL", "gpt-4.1-mini"))
                    except Exception as exc:
                        st.error(f"AI request failed: {exc}")
            if st.session_state.get("ai_brief"):
                st.markdown(st.session_state["ai_brief"])
                st.caption("Based on headlines only. This explanation has not checked the full articles and is not a buying or selling suggestion.")
    else:
        st.info("Press 'Find recent news' to begin. Internet access is needed.")

    st.divider()
    st.subheader("Company announcements")
    st.caption("Find links to company announcements through Investo. Open and read the documents yourself; this app has not checked their contents.")
    filing_key = st.text_input("Investo key for NGX disclosure lookup", type="password",
                               value=os.getenv("INVESTO_API_KEY", ""), key="filing_key")
    if st.button("Fetch official filing links"):
        try:
            st.session_state["filings"] = fetch_filings(selected, filing_key)
            st.session_state["filing_symbol"] = selected
        except Exception as exc:
            st.error(str(exc))
    filings = st.session_state.get("filings")
    if filings is not None and st.session_state.get("filing_symbol") == selected:
        if filings.empty:
            st.info("No filings were returned for this ticker.")
        else:
            st.dataframe(filings, hide_index=True, use_container_width=True,
                column_config={"url":st.column_config.LinkColumn("Official PDF")})
            st.caption("Disclosures via Investo — investo.ng. Original documents are hosted by their publishers, often the NGX document library.")

with tabs[4]:
    st.subheader("Your price data and how to read the app")
    st.markdown("""
    - **Worth a closer look:** the price checks agree on a possible buying idea. Research it first.
    - **Review shares you own:** the checks suggest weakness. Selling for a profit depends on your purchase price and fees.
    - **Wait and watch:** there is no clear idea, or there is not enough information.
    - **Price goal:** the price we test for a possible gain. **Price limit:** the price where the idea is considered unsuccessful.
    - **Reached the price goal:** how often completed ideas reached their goal before their limit. This is not the chance that the next idea will succeed.
    - **Practice prices:** fictional examples. Uploaded and connected prices may be old; always check the observation date.
    """)
    st.dataframe(frame.tail(40), use_container_width=True, hide_index=True)
    st.download_button("⬇️ Download selected observations", frame.to_csv(index=False).encode(),
                       file_name=f"bars_{selected.lower()}.csv", mime="text/csv")
    with st.expander("Detailed calculation rules and limitations"):
        st.markdown("""
        **How this build should be used**

        - **Synthetic demo**: fictional data for testing the UI and algorithms; do not trade from it.
        - **CSV**: import legally obtained daily OHLCV data, or genuine timestamped intraday data for DAY mode.
        - **Investo API**: documented `/api/v1/prices/{symbol}` and `/api/v1/filings/{symbol}` endpoints; key and internet required, EOD only, raw responses remain in session memory.
        - **Signal accuracy**: ratio of target-hit alerts to all resolved alerts; not a predictor's confidence, a trading win rate, or a promise of profitability.
        - **Costs**: hypothetical percentage charged per round trip. Supply your actual broker rates. No spread, slippage, dividends or splits adjustment is performed.
        - **No look-ahead**: historical indicators are calculated only on previous/current bars; backtest enters on the next bar open. RSS is not backfilled as a historical feature.
        - **Bar ambiguity**: when target and stop appear in one bar, stop takes precedence. Missing high/low triggers conservative close-only level checks for that bar.
        - **Not production-ready**: no authenticated brokerage execution, automated scheduling, market-hours validation, live data, compliance checks or monitored risk controls.

        **Provider terms:** Investo — https://investo.ng/api-terms · NGX — https://ngxgroup.com/exchange/data/
        """)

conn.close()
