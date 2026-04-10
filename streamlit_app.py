import streamlit as st
import google.generativeai as genai
from datetime import datetime
import pandas as pd
from PIL import Image

# --- 1. アプリ設定 & API接続 ---
st.set_page_config(page_title="1% Investor Dashboard", layout="wide")

# SecretsからAPIキーを取得
if "GEMINI_API_KEY" in st.secrets:
    genai.configure(api_key=st.secrets["GEMINI_API_KEY"])
else:
    st.error("Secretsに 'GEMINI_API_KEY' が登録されていません。")
    st.stop()

# --- 2. 統合済みポジションデータ (画像より完全集計) ---
# 2026/04/10時点 レート: 158.45
USD_JPY_RATE = 158.45 

positions = [
    {"ticker": "MU", "shares": 100, "price": 421.51, "cost": 377.29, "currency": "USD"},
    {"ticker": "VRT", "shares": 70, "price": 287.64, "cost": 262.13, "currency": "USD"},
    {"ticker": "NEE", "shares": 100, "price": 94.48, "cost": 92.95, "currency": "USD"},
    {"ticker": "IHI", "shares": 600, "price": 3312.3, "cost": 3415.5, "currency": "JPY"},
]

# --- 3. 計算ロジック ---
total_profit_jpy = 0.0
for p in positions:
    diff = p["price"] - p["cost"]
    if p["currency"] == "USD":
        total_profit_jpy += (diff * p["shares"] * USD_JPY_RATE)
    else:
        total_profit_jpy += (diff * p["shares"])

# --- 4. メイン表示 (初期の使いやすいデザインを再現) ---
st.title("🚀 1%の投資家：出口戦略ダッシュボード")

st.subheader("🗓 重要イベント・カウントダウン")
col_ev1, col_ev2, col_ev3 = st.columns(3)
days_to_goal = (datetime(2026, 5, 29) - datetime.now()).days
col_ev1.metric("VRT 決算発表 (4/22)", f"あと 12 日")
col_ev2.metric("MSCI 採用 (5/12)", f"あと 32 日")
col_ev3.metric("出口戦略 (5/29)", f"あと {days_to_goal} 日")

st.divider()

st.subheader("💰 総合損益ステータス")
m1, m2, m3 = st.columns(3)
m1.metric("現在のドル円レート", f"¥{USD_JPY_RATE}")
m2.metric("総損益 (JPY)", f"¥{total_profit_jpy:,.0f}", delta=f"{total_profit_jpy/10000:.1f}万円")
m3.metric("目標進捗", "順調")

st.subheader("📊 ポジション詳細")
df = pd.DataFrame(positions)
df['損益'] = (df['price'] - df['cost']) * df['shares']
st.table(df)

st.divider()

# --- 5. 画像解析セクション ---
st.subheader("📸 AI解析コンシェルジュ")
uploaded_file = st.file_uploader("チャート画像などをアップロード", type=["png", "jpg", "jpeg"])

if uploaded_file:
    img = Image.open(uploaded_file)
    st.image(img, caption="解析対象", use_container_width=True)

user_question = st.text_input("AIへの質問を入力してください")

if st.button("AIコンシェルジュに相談する"):
    try:
        # 【重要】404エラー回避のため、最も確実に認識される旧モデル名を指定
        # Streamlit Cloudの環境が古くても動く名称です
        model = genai.GenerativeModel('gemini-pro-vision' if uploaded_file else 'gemini-pro')
        
        prompt = f"""
        あなたは「1%の投資家」の専属コンシェルジュです。
        以下の状況を踏まえ、品格のある日本語でアドバイスしてください。
        - 総損益(円): {total_profit_jpy:,.0f}円
        - 出口(5/29)まで残り: {days_left}日
        - ユーザーの質問: {user_question if user_question else "現状を分析してください"}
        """
        
        if uploaded_file:
            response = model.generate_content([prompt, img])
        else:
            response = model.generate_content(prompt)
            
        st.info(response.text)
        
    except Exception as e:
        # 万が一これでもダメな場合のみ、代替モデルを試行
        try:
            model = genai.GenerativeModel('gemini-1.5-flash-latest')
            response = model.generate_content([prompt, img] if uploaded_file else prompt)
            st.info(response.text)
        except:
            st.error("解析エラーが発生しました。時間を置いてお試しいただくか、アプリを再起動してください。")
