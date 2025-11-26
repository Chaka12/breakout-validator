import streamlit as st
import os
import json
from openai import OpenAI

# --- CONFIG ---
st.set_page_config(page_title="Breakout Validator", page_icon="🔍", layout="centered")

# OpenRouter setup (use st.secrets in production)
API_KEY = st.secrets.get("OPENROUTER_API_KEY") or os.getenv("OPENROUTER_API_KEY")
if not API_KEY:
    st.error("⚠️ Set OPENROUTER_API_KEY in secrets or environment")
    st.stop()

client = OpenAI(
    base_url="https://openrouter.ai/api/v1",
    api_key=API_KEY,
)

STRATEGY_RULES = """
You are a strict trade validator for a breakout-retest strategy. The trader uses MetaTrader 5 (demo, $10,000).

APPROVE only if ALL these are true:
1. Current time is between 8 AM and 4 PM GMT (London/US session).
2. No high-impact news within 30 minutes.
3. Price has broken and retested a clear H1 swing point.
4. M5 candle closed confirming direction.
5. H1 ATR meets minimum: Gold > $0.3, S&P500 > 3 pts, AUD/USD & GBP/USD > 20 pips, GBP/JPY > 30 pips.
6. H1 ADX > 20.
7. Risk = $100 (1% of $10k), with ≥1:2 R:R.

If any condition fails, REJECT with specific reason.
"""

# --- UI ---
st.title("📱 Breakout Validator")
st.caption("Validate your H1/M5 breakout-retest setup before trading")

# Instrument-specific defaults
instruments = {
    "Gold": {"atr_min": 0.3, "pip_unit": "$", "stop_pips": 0.5, "target_pips": 3.0},
    "S&P 500": {"atr_min": 3, "pip_unit": "pts", "stop_pips": 1, "target_pips": 10},
    "AUD/USD": {"atr_min": 20, "pip_unit": "pips", "stop_pips": 10, "target_pips": 30},
    "GBP/USD": {"atr_min": 20, "pip_unit": "pips", "stop_pips": 10, "target_pips": 30},
    "GBP/JPY": {"atr_min": 30, "pip_unit": "pips", "stop_pips": 15, "target_pips": 40},
}

col1, col2 = st.columns(2)
with col1:
    instrument = st.selectbox("Instrument", list(instruments.keys()))
with col2:
    gmt_time = st.time_input("Current GMT Time", value=None)

news_risk = st.checkbox("⚠️ High-impact news in next 30 min?", value=False)

st.subheader("Price Levels")
col1, col2, col3 = st.columns(3)
with col1:
    breakout = st.number_input("Breakout Level", format="%.5f")
with col2:
    retest = st.number_input("Retest Price", format="%.5f")
with col3:
    entry = st.number_input("Entry Price", format="%.5f")

st.subheader("Confirmation")
col1, col2 = st.columns(2)
with col1:
    atr = st.number_input(f"H1 ATR ({instruments[instrument]['pip_unit']})", value=0.0, format="%.2f")
with col2:
    adx = st.number_input("H1 ADX", value=0.0, format="%.1f")

stop = st.number_input("Stop Loss", format="%.5f")
target = st.number_input("Take Profit", format="%.5f")

# --- VALIDATION ---
if st.button("🔍 Validate Trade", type="primary"):
    if not gmt_time:
        st.error("Enter GMT time")
    else:
        # Calculate R:R
        risk = abs(entry - stop)
        reward = abs(target - entry)
        rr = reward / risk if risk > 0 else 0

        trade_data = {
            "instrument": instrument,
            "gmt_time": f"{gmt_time.hour:02d}:{gmt_time.minute:02d}",
            "news_risk": news_risk,
            "breakout_level": breakout,
            "retest_price": retest,
            "entry": entry,
            "stop": stop,
            "target": target,
            "atr": atr,
            "adx": adx,
            "rr_ratio": round(rr, 2)
        }

        # Build prompt
        prompt = f"""
{STRATEGY_RULES}

Trade details:
- Instrument: {instrument}
- Current GMT time: {trade_data['gmt_time']}
- High-impact news soon?: {news_risk}
- Breakout level: {breakout}
- Retest price: {retest}
- Entry price: {entry}
- Stop loss: {stop}
- Take profit: {target}
- H1 ATR: {atr} {instruments[instrument]['pip_unit']}
- H1 ADX: {adx}

Respond ONLY in JSON format:
{{
  "decision": "APPROVED" or "REJECTED",
  "reason": "specific rule violated or confirmed",
  "risk_usd": 100.0,
  "rr_ratio": {rr}
}}
"""

        with st.spinner("🧠 AI is validating..."):
            try:
                response = client.chat.completions.create(
                    model="meta-llama/llama-3.1-8b-instruct:free",
                    messages=[{"role": "user", "content": prompt}],
                    temperature=0.0,
                    max_tokens=250
                )
                raw = response.choices[0].message.content.strip()
                if raw.startswith("```json"):
                    raw = raw[7:-3]
                result = json.loads(raw)

                # Display result
                if result["decision"] == "APPROVED":
                    st.success(f"✅ **APPROVED**\n\n{result['reason']}")
                else:
                    st.error(f"❌ **REJECTED**\n\n{result['reason']}")

                # Journal snippet
                unit = instruments[instrument]["pip_unit"]
                session = "London" if 8 <= gmt_time.hour < 12 else "US" if 13 <= gmt_time.hour <= 16 else "Invalid"
                journal = f"""
[{ '✅' if result['decision'] == 'APPROVED' else '❌' }] {instrument}:
- Breakout: {breakout} → Retest: {retest} → Entry: {entry}
- SL: {stop}, TP: {target} ({result['rr_ratio']}:1)
- ATR: {atr} {unit}, ADX: {adx}, Session: {session}
- Emotion: [______________] → Lesson: [______________]
"""
                st.text_area("📝 Copy for your journal", journal.strip(), height=150)

            except Exception as e:
                st.error(f"AI Error: {str(e)}")