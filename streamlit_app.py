import streamlit as st
from google import genai  # 新しい推奨パッケージを使用
from datetime import datetime
import pandas as pd
from PIL import Image

# --- 1. アプリ設定 & API接続 ---
st.set_page_config(page_title="1% Investor Dashboard", layout="centered")

# SecretsからAPIキーを取得
if "GEMINI_API_KEY" in st.secrets:
    client = genai.Client(api_key=st.secrets["GEMINI_API_KEY"])
else:
    st.error("Secretsに 'GEMINI_API_KEY' が登録されていません。")
    st.stop()

# --- 2. 統合済みポジションデータ ---
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

# --- 4. メイン表示 (初期のシンプルUI) ---
st.title("🚀 1%の投資家：出口戦略ダッシュボード")

st.header("🗓 カウントダウン")
days_left = (datetime(2026, 5, 29) - datetime.now()).days
st.metric("5/29 出口ターゲットまで", f"あと {days_left} 日")

st.divider()

st.header("💰 総合損益状況")
st.metric("総損益 (円計)", f"¥{total_profit_jpy:,.0f}", delta=f"{total_profit_jpy/10000:.1f}万円")
st.write(f"（為替レート: ¥{USD_JPY_RATE}）")

st.header("📊 統合ポジション詳細")
df = pd.DataFrame(positions)
df['損益'] = (df['price'] - df['cost']) * df['shares']
st.table(df)

st.divider()

# --- 5. AI解析セクション ---
st.header("📸 AIコンシェルジュ解析")
uploaded_file = st.file_uploader("チャート画像をアップロード", type=["png", "jpg", "jpeg"])

if uploaded_file:
    img = Image.open(uploaded_file)
    st.image(img, caption="解析対象", use_container_width=True)

user_question = st.text_input("AIへの質問を入力してください")

if st.button("AIコンシェルジュに相談する"):
    try:
        prompt = f"""
        あなたは「1%の投資家」の専属コンシェルジュです。
        以下の状況を踏まえ、品格のある日本語でアドバイスしてください。
        - 総損益(円): {total_profit_jpy:,.0f}円
        - 出口(5/29)まで残り: {days_left}日
        - ユーザーの質問: {user_question if user_question else "現状を分析してください"}
        """
        
        # 新しいSDKでの生成方法
        if uploaded_file:
            response = client.models.generate_content(
                model='gemini-2.0-flash', # 最新の2.0-flashを使用
                contents=[prompt, img]
            )
        else:
            response = client.models.generate_content(
                model='gemini-2.0-flash',
                contents=prompt
            )
            
        st.info(response.text)
        
    except Exception as e:
        st.error("最新のAIモデルへの接続に失敗しました。")
        st.write(f"エラー詳細: {e}")
