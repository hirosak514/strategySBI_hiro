import streamlit as st
import yfinance as yf
from datetime import datetime
import pandas as pd
from PIL import Image

# --- 1. アプリ設定 ---
st.set_page_config(page_title="1% Investor Dashboard", layout="centered")

# --- 2. 確定済みポジションデータ (2026/04/10 精査データ) ---
# あなたの最新の保有状況を完全に反映しています
POSITIONS = [
    {"ticker": "MU",   "name": "マイクロン",     "shares": 71,   "cost": 374.88, "currency": "USD"},
    {"ticker": "VRT",  "name": "バーティブ",     "shares": 70,   "cost": 264.44, "currency": "USD"},
    {"ticker": "NEE",  "name": "ネクステラ",     "shares": 105,  "cost": 93.75,  "currency": "USD"},
    {"ticker": "7013.T", "name": "IHI",        "shares": 1400, "cost": 3425.4, "currency": "JPY"},
]

# --- 3. 最新データの自動取得 (yfinance) ---
# API不要・無料・無制限
@st.cache_data(ttl=3600)  # 1時間ごとにデータをキャッシュ更新
def get_market_data():
    # ドル円レートの取得
    forex = yf.Ticker("JPY=X").history(period="1d")
    current_usdjpy = forex['Close'].iloc[-1]
    
    results = []
    for p in POSITIONS:
        ticker_obj = yf.Ticker(p["ticker"])
        # 最新の終値を取得
        current_price = ticker_obj.history(period="1d")['Close'].iloc[-1]
        
        # 損益計算
        diff = current_price - p["cost"]
        if p["currency"] == "USD":
            profit_jpy = diff * p["shares"] * current_usdjpy
        else:
            profit_jpy = diff * p["shares"]

        results.append({
            "銘柄": p["name"],
            "数量": p["shares"],
            "取得単価": f"{p['cost']:,.2f}",
            "現在値": f"{current_price:,.2f}",
            "損益(円)": profit_jpy
        })
    
    return results, current_usdjpy

# データ取得実行
with st.spinner('最新の市場データを取得中...'):
    data_list, rate_now = get_market_data()

# --- 4. メイン表示 (最初期の直感的なデザイン) ---
st.title("🚀 1%の投資家：出口戦略ボード")

# カウントダウン
days_left = (datetime(2026, 5, 29) - datetime.now()).days
st.metric("5/29 出口ターゲットまで", f"あと {days_left} 日")

st.divider()

# 総合損益サマリー (yfinanceによる正確な計算)
total_profit = sum(item["損益(円)"] for item in data_list)
st.header("💰 総合損益状況")
col1, col2 = st.columns(2)
col1.metric("総損益 (日本円計)", f"¥{total_profit:,.0f}", delta=f"{total_profit/10000:.1f}万円")
col2.metric("現在のドル円レート", f"¥{rate_now:.2f}")

st.divider()

# ポジション詳細
st.header("📊 ポジション詳細 (自動更新)")
df = pd.DataFrame(data_list)
# 見栄えのために損益(円)をフォーマット
df['損益(円)'] = df['損益(円)'].map('¥{:,.0f}'.format)
st.table(df)

st.divider()

# --- 5. AIコンシェルジュ解析セクション (必要な時だけGemini) ---
st.header("📸 AIチャート・画像診断")
uploaded_file = st.file_uploader("診断したい画像をアップロード", type=["png", "jpg", "jpeg"])

if uploaded_file:
    img = Image.open(uploaded_file)
    st.image(img, caption="診断対象の画像", use_container_width=True)

# AI診断実行ボタン (これを押した時だけAPIを叩く)
if uploaded_file and st.button("AIコンシェルジュに診断を依頼する"):
    with st.spinner('AIが画像と現在の資産状況を分析中...'):
        try:
            import google.generativeai as genai
            # SecretsからAPIキーを取得
            if "GEMINI_API_KEY" in st.secrets:
                genai.configure(api_key=st.secrets["GEMINI_API_KEY"])
            else:
                st.error("Secretsに 'GEMINI_API_KEY' が登録されていません。")
                st.stop()
            
            # モデル名は最も安定している 'gemini-1.5-flash' を使用
            model = genai.GenerativeModel('gemini-1.5-flash')
            
            # 現在の損益状況をテキストでAIに渡す (プロンプトの強化)
            prompt = f"""
            あなたは「1%の投資家」の専属コンシェルジュです。
            以下の状況を踏まえ、品格のある日本語で、アップロードされた画像（チャートやデータ）を分析し、アドバイスしてください。
            - 総損益(円): {total_profit:,.0f}円
            - 出口(5/29)まで残り: {days_left}日
            - 現在のポートフォリオ（MU, VRT, NEE, IHI）
            画像内のチャートがどの銘柄か特定できる場合は、その銘柄への具体的な次の一手を提示してください。
            """
            
            response = model.generate_content([prompt, img])
            st.info(response.text)
            
        except Exception as e:
            if "429" in str(e):
                st.warning("現在、Google側の無料枠制限（APIレート制限）にかかっています。数分待ってから再度ボタンを押してください。")
            else:
                st.error("AI診断中にエラーが発生しました。APIキーの設定を確認するか、しばらく時間をおいてお試しください。")
                st.write(f"詳細: {e}")
