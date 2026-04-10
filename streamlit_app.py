import streamlit as st
import google.generativeai as genai
from datetime import datetime
import pandas as pd
from PIL import Image

# --- 1. アプリの設定 ---
st.set_page_config(page_title="1% Investor Dashboard", layout="wide")

# APIキーの設定
# StreamlitのSecretsを使う場合は st.secrets["GEMINI_API_KEY"] に書き換えてください
API_KEY = "YOUR_API_KEY_HERE" 
genai.configure(api_key=API_KEY)

# --- 2. データ定義 & レート設定 ---
# 最新のドル円レート（手動更新用）
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
with st.expander("📊 ポジション詳細を表示"):
    df = pd.DataFrame(positions)
    df['損益(ベース通貨)'] = (df['price'] - df['cost']) * df['shares']
    st.table(df)

# --- 7. UI: 画像アップロード & AI解析 ---
st.divider()
st.subheader("📸 チャート解析 & AIコンシェルジュ")

col_a, col_b = st.columns([1, 1])

with col_a:
    uploaded_file = st.file_uploader("チャートやエラー画面をアップロード", type=["png", "jpg", "jpeg"])
    if uploaded_file is not None:
        image = Image.open(uploaded_file)
        st.image(image, caption='アップロードされた画像', use_container_width=True)

with col_b:
    user_question = st.text_input("AIへの質問（例：このチャートの展望は？、エラーの直し方は？）")
    analyze_button = st.button("AIコンシェルジュに相談する")

if analyze_button:
    try:
        # 最新のGemini 3.1 Flashを使用
        model = genai.GenerativeModel('gemini-3.1-flash-preview')
        
        # 解析用のプロンプト作成
        prompt = f"""
        あなたは「1%の投資家」を支える専門コンシェルジュです。
        品格のある言葉遣いで、以下のデータを踏まえたアドバイスを「普通の日本語」で提供してください。
        JSON形式やプログラムコードのみの回答は禁止です。
        
        【現在の状況】
        - ドル円: {USD_JPY_RATE}
        - 総損益(円): {total_profit_jpy:,.0f}円
        - 5/29まで残り: {(events[2]['date'] - datetime.now()).days}日
        - ユーザーの質問: {user_question if user_question else "現在の状況を分析してください"}
        """
        
        # 画像がある場合とない場合で処理を分岐
        if uploaded_file is not None:
            response = model.generate_content([prompt, image])
        else:
            response = model.generate_content(prompt)
            
        st.info(response.text)
        
    except Exception as e:
        st.error(f"解析中にエラーが発生しました。モデル名やAPIキーを確認してください: {e}")
