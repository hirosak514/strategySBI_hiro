import streamlit as st
import google.generativeai as genai
from datetime import datetime
import pandas as pd
from PIL import Image

# --- 1. アプリの設定 & セキュリティ ---
st.set_page_config(page_title="1% Investor Dashboard", layout="wide")

if "GEMINI_API_KEY" in st.secrets:
    API_KEY = st.secrets["GEMINI_API_KEY"]
    genai.configure(api_key=API_KEY)
else:
    st.error("Secretsに 'GEMINI_API_KEY' が登録されていません。")
    st.stop()

# --- 2. 最新レート & ポジションデータ (画像から合算) ---
USD_JPY_RATE = 158.45 

positions = [
    {"ticker": "MU", "shares": 100, "price": 421.51, "cost": 377.29, "currency": "USD"},
    {"ticker": "VRT", "shares": 70, "price": 287.64, "cost": 262.13, "currency": "USD"},
    {"ticker": "NEE", "shares": 100, "price": 94.48, "cost": 92.95, "currency": "USD"},
    {"ticker": "IHI", "shares": 600, "price": 3312.3, "cost": 3415.5, "currency": "JPY"},
]

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

# --- 4. UI表示 ---
st.title("🚀 1%の投資家：出口戦略ダッシュボード")

# カウントダウン
st.subheader("🗓 重要イベント・カウントダウン")
event_cols = st.columns(len(events))
for i, event in enumerate(events):
    days_left = (event["date"] - datetime.now()).days
    with event_cols[i]:
        st.metric(label=event["name"], value=f"{days_left}日", delta=f"{event['date'].strftime('%m/%d')}")

st.divider()

# 総合損益
st.subheader("💰 総合損益ステータス")
m1, m2, m3 = st.columns(3)
m1.metric("現在のドル円レート", f"¥{USD_JPY_RATE}")
m2.metric("総損益 (USD)", f"${total_profit_usd:,.2f}")
m3.metric("総損益 (JPY)", f"¥{total_profit_jpy:,.0f}", delta=f"{total_profit_jpy/10000:.1f}万円")

# ポジション詳細
with st.expander("📊 ポジション詳細を表示"):
    df = pd.DataFrame(positions)
    df['損益'] = (df['price'] - df['cost']) * df['shares']
    st.table(df)

# AI解析セクション
st.divider()
st.subheader("📸 チャート解析 & AIコンシェルジュ")
col_a, col_b = st.columns([1, 1])

with col_a:
    uploaded_file = st.file_uploader("画像をアップロード", type=["png", "jpg", "jpeg"])
    if uploaded_file is not None:
        image = Image.open(uploaded_file)
        st.image(image, caption='分析対象', use_container_width=True)

with col_b:
    user_question = st.text_input("質問を入力")
    if st.button("AIコンシェルジュに相談"):
        try:
            # モデル名を 'gemini-1.5-flash' に固定（これが最も安定します）
            model = genai.GenerativeModel('gemini-1.5-flash')
            
            prompt = f"""
            あなたは「1%の投資家」の専属コンシェルジュです。
            以下のデータを踏まえ、5/29の出口戦略に向けた助言を品格のある日本語で行ってください。
            - 総損益(円): {total_profit_jpy:,.0f}円
            - ターゲット(5/29)まで残り: {(events[2]['date'] - datetime.now()).days}日
            """
            
            content = [prompt, image] if uploaded_file else prompt
            response = model.generate_content(content)
            st.info(response.text)
        except Exception as e:
            st.error(f"解析エラーが発生しました。SettingsのSecretsを確認してください。")
            st.write(f"詳細: {e}")
