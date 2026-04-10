import streamlit as st
import google.generativeai as genai
from datetime import datetime
import pandas as pd
from PIL import Image

# --- 1. アプリ設定 & API接続 ---
st.set_page_config(page_title="1% Investor Dashboard", layout="centered")

if "GEMINI_API_KEY" in st.secrets:
    genai.configure(api_key=st.secrets["GEMINI_API_KEY"])
else:
    st.error("Secretsに 'GEMINI_API_KEY' が登録されていません。")
    st.stop()

# --- 2. 最新レート & 統合済みポジションデータ ---
# 2026/04/10 時点
USD_JPY_RATE = 158.45 

# 画像(image_d516e6.jpg)の全入力を銘柄ごとに合算・平均化した数値
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

# --- 4. メイン画面表示 ---
st.title("🚀 1%の投資家ダッシュボード")

# カウントダウン（5/29 出口戦略）
days_to_goal = (datetime(2026, 5, 29) - datetime.now()).days
st.metric("5/29 出口戦略まで", f"あと {days_to_goal} 日")

st.divider()

# 損益サマリー
st.header("💰 総合損益")
st.metric("総損益 (円)", f"¥{total_profit_jpy:,.0f}", delta=f"{total_profit_jpy/10000:.1f}万円")
st.write(f"（ベース為替レート: 1ドル = ¥{USD_JPY_RATE}）")

# ポジション詳細
st.header("📊 保有銘柄詳細")
df = pd.DataFrame(positions)
df['個別損益'] = (df['price'] - df['cost']) * df['shares']
st.table(df)

st.divider()

# --- 5. シンプルな画像解析機能 ---
st.header("📸 AI解析コンシェルジュ")
uploaded_file = st.file_uploader("チャート画像をアップロード", type=["png", "jpg", "jpeg"])

if uploaded_file:
    img = Image.open(uploaded_file)
    st.image(img, caption="解析対象の画像", use_container_width=True)
    
    if st.button("AIに状況を相談する"):
        try:
            # 2026年時点で最も安定しているモデル名
            model = genai.GenerativeModel('gemini-1.5-flash')
            
            prompt = f"""
            あなたは「1%の投資家」の専属コンシェルジュです。
            現在の総損益 {total_profit_jpy:,.0f}円、出口まで残り {days_to_goal}日という状況を踏まえ、
            アップロードされた画像（チャートやデータ）を分析し、品格のある日本語でアドバイスしてください。
            """
            
            # 画像とテキストを同時に送信
            response = model.generate_content([prompt, img])
            st.info(response.text)
            
        except Exception as e:
            st.error("解析中にエラーが発生しました。")
            st.write(f"詳細: {e}")
