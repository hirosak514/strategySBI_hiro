import streamlit as st
import google.generativeai as genai
from datetime import datetime
import pandas as pd
from PIL import Image

# --- 1. アプリ設定 & API接続 ---
st.set_page_config(page_title="1% Investor Dashboard", layout="centered")

# Secretsから安全に取得
if "GEMINI_API_KEY" in st.secrets:
    genai.configure(api_key=st.secrets["GEMINI_API_KEY"])
else:
    st.error("Secretsに 'GEMINI_API_KEY' が登録されていません。")
    st.stop()

# --- 2. 統合済みポジションデータ (image_d516e6.jpgより完全手動集計) ---
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

# --- 4. メイン表示 (初期の使いやすいUIを再現) ---
st.title("🚀 1%の投資家：出口戦略ダッシュボード")

# カウントダウンセクション
st.header("🗓 カウントダウン")
days_left = (datetime(2026, 5, 29) - datetime.now()).days
st.metric("5/29 出口ターゲットまで", f"あと {days_left} 日")

st.divider()

# 総合損益ステータス
st.header("💰 総合損益状況")
m1, m2 = st.columns(2)
m1.metric("総損益 (円計)", f"¥{total_profit_jpy:,.0f}", delta=f"{total_profit_jpy/10000:.1f}万円")
m2.metric("現在のドル円", f"¥{USD_JPY_RATE}")

# ポジション詳細
st.header("📊 統合ポジション詳細")
df = pd.DataFrame(positions)
df['損益'] = (df['price'] - df['cost']) * df['shares']
st.table(df)

st.divider()

# 画像解析 & AI解析
st.header("📸 AIコンシェルジュ解析")
uploaded_file = st.file_uploader("チャート画像をアップロードして相談", type=["png", "jpg", "jpeg"])

if uploaded_file:
    img = Image.open(uploaded_file)
    st.image(img, caption="解析対象の画像", use_container_width=True)

user_question = st.text_input("AIへの質問を入力してください")

if st.button("AIコンシェルジュに相談する"):
    try:
        # モデル名は最も安定している 'gemini-1.5-flash' を使用
        model = genai.GenerativeModel('gemini-1.5-flash')
        
        prompt = f"""
        あなたは「1%の投資家」の専属コンシェルジュです。
        以下の状況を踏まえ、品格のある日本語でアドバイスしてください。
        - 総損益(円): {total_profit_jpy:,.0f}円
        - 出口(5/29)まで残り: {days_left}日
        - ユーザーの質問: {user_question if user_question else "現在の相場環境を分析してください"}
        """
        
        # 画像がある場合はマルチモーダル、ない場合はテキストのみで送信
        if uploaded_file:
            response = model.generate_content([prompt, img])
        else:
            response = model.generate_content(prompt)
            
        st.info(response.text)
        
    except Exception as e:
        st.error("解析エラーが発生しました。モデルの更新を待つか、APIキーの設定を確認してください。")
        st.write(f"詳細: {e}")
