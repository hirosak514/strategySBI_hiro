import streamlit as st
import yfinance as yf
from datetime import datetime
import pandas as pd
from PIL import Image
import google.generativeai as genai

# --- 1. アプリ設定 ---
st.set_page_config(page_title="1% Investor Dashboard", layout="centered")

# --- 2. 確定済みポジションデータ ---
POSITIONS = [
    {"ticker": "MU",   "name": "マイクロン",     "shares": 71,   "cost": 374.88, "currency": "USD"},
    {"ticker": "VRT",  "name": "バーティブ",     "shares": 70,   "cost": 264.44, "currency": "USD"},
    {"ticker": "NEE",  "name": "ネクステラ",     "shares": 105,  "cost": 93.75,  "currency": "USD"},
    {"ticker": "7013.T", "name": "IHI",        "shares": 1400, "cost": 3425.4, "currency": "JPY"},
]

# --- 3. 市場データ取得 (yfinance: ここはAPI制限なし) ---
@st.cache_data(ttl=3600)
def get_market_data():
    try:
        forex = yf.Ticker("JPY=X").history(period="1d")
        current_usdjpy = forex['Close'].iloc[-1]
        results = []
        for p in POSITIONS:
            ticker_obj = yf.Ticker(p["ticker"])
            current_price = ticker_obj.history(period="1d")['Close'].iloc[-1]
            diff = current_price - p["cost"]
            profit_jpy = (diff * p["shares"] * current_usdjpy) if p["currency"] == "USD" else (diff * p["shares"])
            results.append({"銘柄": p["name"], "数量": p["shares"], "取得単価": f"{p['cost']:,.2f}", "現在値": f"{current_price:,.2f}", "損益(円)": profit_jpy})
        return results, current_usdjpy
    except:
        # 万が一yfinanceが失敗した際のフォールバック
        return [], 159.20

data_list, rate_now = get_market_data()

# --- 4. メイン表示 (最初期のUIレイアウト) ---
st.title("🚀 1%の投資家：出口戦略ボード")
days_left = (datetime(2026, 5, 29) - datetime.now()).days
st.metric("5/29 出口ターゲットまで", f"あと {days_left} 日")

st.divider()

if data_list:
    total_profit = sum(item["損益(円)"] for item in data_list)
    st.header("💰 総合損益状況")
    c1, c2 = st.columns(2)
    c1.metric("総損益 (日本円計)", f"¥{total_profit:,.0f}", delta=f"{total_profit/10000:.1f}万円")
    c2.metric("現在のドル円", f"¥{rate_now:.2f}")
    st.divider()
    st.table(pd.DataFrame(data_list))
else:
    st.error("現在、株価データの取得に失敗しています。時間を置いてリロードしてください。")

# --- 5. AI診断セクション ---
st.header("📸 AIチャート・画像診断")
uploaded_file = st.file_uploader("診断したい画像をアップロード", type=["png", "jpg", "jpeg"])

if uploaded_file:
    img = Image.open(uploaded_file)
    st.image(img, caption="診断対象の画像", use_container_width=True)

if uploaded_file and st.button("AIコンシェルジュに診断を依頼する"):
    with st.spinner('最新のGeminiモデルで分析中...'):
        try:
            if "GEMINI_API_KEY" in st.secrets:
                genai.configure(api_key=st.secrets["GEMINI_API_KEY"])
            else:
                st.error("Secretsに APIキー が設定されていません。")
                st.stop()
            
            # Gemini 2.0 Flash を優先使用
            model = genai.GenerativeModel('gemini-2.0-flash')
            
            prompt = f"あなたは「1%の投資家」の専属コンシェルジュです。現在の損益{total_profit:,.0f}円、出口まで残り{days_left}日という状況を踏まえ、この画像を分析してください。"
            
            response = model.generate_content([prompt, img])
            st.info(response.text)
            
        except Exception as e:
            if "429" in str(e):
                st.warning("現在、AIの利用制限（429エラー）がかかっています。数分〜1時間ほど待ってから再度「診断を依頼する」ボタンを押してください。※上の損益表はそのまま利用可能です。")
            else:
                st.error(f"診断中にエラーが発生しました。時間を置いてお試しください。")
