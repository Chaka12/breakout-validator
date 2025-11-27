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

st.subheader("📋 Paste MT5 line (Ctrl-V)")
raw = st.text_area(
    "Format: SYMBOL SIDE BREAKOUT RETEST ENTRY STOP TARGET ATR ADX VOLUME",
    placeholder="GBPUSD BUY 1.28030 1.27780 1.28040 1.27990 1.28290 0.00034 28.4 4123"
)

if st.button("🔍 Validate Trade", type="primary") and raw:
    try:
        parts = raw.strip().split()
        symbol, side, breakout, retest, entry, stop, target, atr, adx, vol = parts
        instrument = symbol.replace("USD","/USD").replace("GBP","GBP/")   # quick map
        side = side.upper()
        breakout = float(breakout)
        retest   = float(retest)
        entry    = float(entry)
        stop     = float(stop)
        target   = float(target)
        atr_v    = float(atr)
        adx_v    = float(adx)
        vol_v    = int(vol)

        # ---- auto-calculate ----
        risk_pips = abs(entry - stop)
        reward_pips = abs(target - entry)
        rr = reward_pips / risk_pips if risk_pips else 0
        account = 10_000
        risk_usd = account * 0.01                       # 1 % hard rule
        pip_val  = {"Gold":1, "S&P":1, "XAUUSD":1}.get(symbol, 1)   # customise
        lots = risk_usd / (risk_pips * pip_val)

        # ---- build identical prompt you already use ----
        prompt = f"""
You are a strict trade validator for a breakout-retest strategy…
(keep your original STRATEGY_RULES block here)
Trade details:
- Instrument: {instrument}
- Side: {side}
- Current GMT time: {gmt_time}
- High-impact news soon?: {news_risk}
- Breakout level: {breakout}
- Retest price: {retest}
- Entry price: {entry}
- Stop loss: {stop}
- Take profit: {target}
- H1 ATR: {atr_v} {instruments[instrument]['pip_unit']}
- H1 ADX: {adx_v}
- Volume vs 20-bar avg: {vol_v} (you may ignore if not needed)

Respond ONLY in JSON:
{{
  "decision": "APPROVED" or "REJECTED",
  "reason": "specific rule violated or confirmed",
  "risk_usd": {risk_usd},
  "rr_ratio": {rr:.2f},
  "lots": {lots:.2f}
}}
"""
        # ---- call OpenRouter exactly as before ----
        with st.spinner("🧠 AI is validating…"):
            response = client.chat.completions.create(
                model="meta-llama/llama-3.1-8b-instruct:free",
                messages=[{"role":"user","content":prompt}],
                temperature=0, max_tokens=250
            )
            raw_resp = response.choices[0].message.content.strip()
            result = json.loads(raw_resp.removeprefix("```json").removesuffix("```"))

        # ---- display ----
        if result["decision"]=="APPROVED":
            st.success(f"✅ APPROVED – {result['reason']}")
            st.info(f"Suggested size: {result['lots']} lots  (${result['risk_usd']})")
        else:
            st.error(f"❌ REJECTED – {result['reason']}")

        # ---- journal snippet ----
        unit = instruments[instrument]["pip_unit"]
        journal = f"""
[{result['decision'][0]}] {instrument} {side}
Breakout {breakout} → Retest {retest} → Entry {entry}
SL {stop}  TP {target}  ({rr:.1f}:1)
ATR {atr_v} {unit}  ADX {adx_v:.1f}  Lots {lots:.2f}
Emotion: _____________  Lesson: _____________
"""
        st.text_area("📝 Copy for journal", journal.strip(), height=140)

    except Exception as e:
        st.error(f"Parse error – check MT5 line format.\n{e}")
