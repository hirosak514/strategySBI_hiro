import streamlit as st
import google.generativeai as genai
from datetime import datetime
import pandas as pd

# --- 1. アプリの設定 ---
st.set_page_config(page_title="1% Investor Dashboard", layout="wide")

# APIキーの設定（StreamlitのSecretsに設定することを推奨）
# genai.configure(api_key=st.secrets["GEMINI_API_KEY"])
genai.configure(api_key="YOUR_API_KEY_HERE") # テスト用。本来はSecretsを使用

# --- 2. データ定義 & レート設定 ---
# 最新のドル円レート（2026/04/10 時点。API連携がない場合はここを手動更新）
USD_JPY_RATE = 158.45 

# 保有ポジションデータ
positions = [
    {"ticker": "MU", "shares": 43, "price": 421.51, "cost": 368.19, "currency": "USD"},
    {"ticker": "VRT", "shares": 32, "price": 287.64, "cost": 257.77, "currency": "USD"},
    {"ticker": "IHI", "shares": 300, "price": 3391.0, "cost": 3503.7, "currency": "JPY"},
]

# 重要イベント
events = [
    {"name": "VRT 決算発表", "date": datetime(2026, 4, 22)},
    {"name": "MSCI 採用発表", "date": datetime(2026, 5, 12)},
    {"name": "出口戦略 ターゲット", "date": datetime(2026, 5, 29)},
]

# --- 3. 計算ロジック ---
total_profit_usd = 0.0
total_profit_jpy = 0.0

for p in positions:
    diff = p["price"] - p["cost"]
    profit_base = diff * p["shares"]
    
    if p["currency"] == "USD":
        total_profit_usd += profit_base
        total_profit_jpy += profit_base * USD_JPY_RATE
    else:
        total_profit_jpy += profit_base
        total_profit_usd += profit_base / USD_JPY_RATE

# --- 4. UI: ヘッダー & カウントダウン ---
st.title("🚀 1%の投資家：出口戦略ダッシュボード")

st.subheader("🗓 重要イベント・カウントダウン")
event_cols = st.columns(len(events))
for i, event in enumerate(events):
    days_left = (event["date"] - datetime.now()).days
    with event_cols[i]:
        st.metric(label=event["name"], value=f"{days_left}日", delta=f"{event['date'].strftime('%m/%d')}")

st.divider()

# --- 5. UI: 損益サマリー ---
st.subheader("💰 総合損益ステータス")
m1, m2, m3 = st.columns(3)
m1.metric("現在のドル円レート", f"¥{USD_JPY_RATE}")
m2.metric("総損益 (USD)", f"${total_profit_usd:,.2f}")
m3.metric("総損益 (JPY)", f"¥{total_profit_jpy:,.0f}", delta=f"{total_profit_jpy/10000:.1f}万円")

# --- 6. UI: 個別銘柄詳細テーブル ---
st.subheader("📊 ポジション詳細")
df = pd.DataFrame(positions)
df['損益'] = (df['price'] - df['cost']) * df['shares']
st.table(df)

# --- 7. AIコンシェルジュ解析 ---
st.divider()
st.subheader("🤖 AIコンシェルジュの分析")

if st.button("現在の状況をAIで解析する"):
    try:
        # 最新のGemini 3.1 Flashを使用
        model = genai.GenerativeModel('gemini-3.1-flash-preview')
        
        prompt = f"""
        あなたは「1%の投資家」を支える専門コンシェルジュです。
        以下のデータを分析し、5/29の出口戦略に向けた、品格のあるアドバイスを「普通の日本語の文章」で提供してください。
        JSONやプログラム形式は禁止です。
        
        データ：
        - 現在のドル円: {USD_JPY_RATE}
        - 総損益(円): {total_profit_jpy:,.0f}円
        - MU株価: $421.51 (取得: $368.19)
        - VRT株価: $287.64 (取得: $257.77)
        - IHI株価: ¥3391 (取得: ¥3503.7)
        - 5/29まであと {(events[2]['date'] - datetime.now()).days} 日
        """
        
        response = model.generate_content(prompt)
        st.write(response.text)
    except Exception as e:
        st.error(f"AI解析中にエラーが発生しました: {e}")
