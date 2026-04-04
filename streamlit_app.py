import streamlit as st
import yfinance as yf
import pandas as pd
from datetime import datetime

# --- 設定: あなたの保有データ ---
PORTFOLIO = {
    "MU": {"shares": 27, "cost": 364.78, "currency": "USD"},
    "VRT": {"shares": 32, "cost": 257.77, "currency": "USD"},
    "7013.T": {"shares": 300, "cost": 3492.0, "currency": "JPY"} # IHI (東証)
}

# --- 重要日程 ---
DATE_ANNOUNCEMENT = datetime(2026, 5, 12)
DATE_EXIT = datetime(2026, 5, 29)

def get_stock_data(tickers):
    data = {}
    for ticker in tickers:
        stock = yf.Ticker(ticker)
        # プレマーケットや時間外も含めた直近価格を取得
        hist = stock.history(period="1d")
        if not hist.empty:
            data[ticker] = hist['Close'].iloc[-1]
        else:
            data[ticker] = None
    return data

# --- Streamlit UI ---
st.set_page_config(page_title="MSCI Exit Strategy Dashboard", layout="wide")

st.title("🚀 Strategist Dashboard: 5/29 Exit Path")
st.write(f"現在時刻: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")

# --- カウントダウンセクション ---
col1, col2 = st.columns(2)
days_to_ann = (DATE_ANNOUNCEMENT - datetime.now()).days
days_to_exit = (DATE_EXIT - datetime.now()).days

with col1:
    st.metric("MSCI発表 (5/12) まで", f"{days_to_ann} 日")
    st.info("💡 発表直後のボラティリティに備えよ。指値の再調整。")

with col2:
    st.metric("出口戦略 (5/29) まで", f"{days_to_exit} 日", delta_color="inverse")
    st.warning("🎯 [EXIT TARGET] 市場が閉まる直前の需要を刈り取る。")

st.divider()

# --- ポートフォリオ監視 ---
st.header("📉 Real-time Portfolio Monitor")

current_prices = get_stock_data(list(PORTFOLIO.keys()))

rows = []
for ticker, info in PORTFOLIO.items():
    cur_price = current_prices.get(ticker)
    if cur_price:
        profit_loss = (cur_price - info['cost']) / info['cost'] * 100
        display_name = "IHI" if ticker == "7013.T" else ticker
        
        rows.append({
            "銘柄": display_name,
            "取得単価": f"{info['cost']:.2f} {info['currency']}",
            "現在値": f"{cur_price:.2f} {info['currency']}",
            "損益率 (%)": f"{profit_loss:.2f}%",
            "保有数": info['shares']
        })

df = pd.DataFrame(rows)
st.table(df)

# --- 戦略メモ ---
st.divider()
st.subheader("📋 Intelligence Reminder")
st.markdown(f"""
- **MU (マイクロン):** 5月リバランスの主役。今夜の買い増し候補。余力 $10,000 のうち $6,000 の投入を検討。
- **VRT (バーティブ):** S&P 500採用済み。AIインフラの鉄板。含み益を伸ばすフェーズ。
- **IHI (7013.T):** 5月「昇格」期待銘柄。日本株の切り札。
- **リスク管理:** トランプ発言によるノイズに惑わされず、5/29の需給イベントに集中すること。
""")

if st.button('データを更新'):
    st.rerun()
