import streamlit as st
import yfinance as yf
import pandas as pd
from datetime import datetime
import google.generativeai as genai
from PIL import Image
import json
import re

# --- 1. セキュリティ設定 (Gemini API) ---
try:
    # Streamlit CloudのSecretsからAPIキーを取得
    genai.configure(api_key=st.secrets["GEMINI_API_KEY"])
except Exception:
    st.error("Secretsに 'GEMINI_API_KEY' が設定されていません。管理画面から設定してください。")
    st.stop()

# --- 2. 定数・重要日程の設定 ---
DATE_ANNOUNCEMENT = datetime(2026, 5, 12)
DATE_EXIT = datetime(2026, 5, 29)
TICKERS = {"MU": "MU", "VRT": "VRT", "IHI": "7013.T"}

# --- 3. セッション状態の初期化 (ポジションデータの保持) ---
if 'portfolio' not in st.session_state:
    # 初期値（解析前）
    st.session_state.portfolio = {
        "MU": {"shares": 27, "cost": 364.78, "currency": "USD"},
        "VRT": {"shares": 32, "cost": 257.77, "currency": "USD"},
        "IHI": {"shares": 300, "cost": 3492.0, "currency": "JPY"}
    }

# --- 4. 関数定義 ---
def get_live_prices(tickers_dict):
    """Yahoo Financeから最新株価を取得"""
    prices = {}
    for name, symbol in tickers_dict.items():
        try:
            stock = yf.Ticker(symbol)
            hist = stock.history(period="1d")
            prices[name] = hist['Close'].iloc[-1] if not hist.empty else None
        except:
            prices[name] = None
    return prices

def analyze_image(image):
    """Gemini APIを使用して画像からポジション情報を抽出"""
    model = genai.GenerativeModel('gemini-1.5-flash')
    prompt = """
    あなたは証券アナリストです。添付されたスクリーンショットから以下の銘柄の情報を抽出し、
    必ず以下の純粋なJSON形式のみで回答してください。
    対象銘柄: MU (Micron), VRT (Vertiv), 7013 (IHI)
    
    出力例:
    {"MU": {"shares": 10, "cost": 350.0}, "VRT": {"shares": 20, "cost": 250.0}, "IHI": {"shares": 100, "cost": 3400.0}}
    """
    response = model.generate_content([prompt, image])
    # JSON部分のみを抽出（```json ... ``` などの装飾を除去）
    json_str = re.search(r'\{.*\}', response.text, re.DOTALL).group()
    return json.loads(json_str)

# --- 5. Streamlit UI 構築 ---
st.set_page_config(page_title="MSCI Exit Strategy Dashboard", layout="wide")

st.title("🚀 Strategist Dashboard: AI Scanner & Exit Path")

# --- サイドバー: 画像アップロード ---
st.sidebar.header("📸 Position Update")
uploaded_file = st.sidebar.file_uploader("証券口座のスクショをアップロード", type=["png", "jpg", "jpeg"])

if uploaded_file:
    if st.sidebar.button("AIでポジションを更新"):
        try:
            img = Image.open(uploaded_file)
            new_data = analyze_image(img)
            # 取得したデータをセッションに反映
            for ticker, vals in new_data.items():
                if ticker in st.session_state.portfolio:
                    st.session_state.portfolio[ticker]["shares"] = vals["shares"]
                    st.session_state.portfolio[ticker]["cost"] = vals["cost"]
            st.sidebar.success("解析完了！データを更新しました。")
        except Exception as e:
            st.sidebar.error(f"解析エラー: {e}")

# --- メイン画面: カウントダウン ---
col1, col2 = st.columns(2)
days_to_ann = (DATE_ANNOUNCEMENT - datetime.now()).days
days_to_exit = (DATE_EXIT - datetime.now()).days

with col1:
    st.metric("MSCI発表 (5/12) まで", f"{days_to_ann} 日")
with col2:
    st.metric("出口戦略 (5/29) まで", f"{days_to_exit} 日", delta_color="inverse")

st.divider()

# --- メイン画面: ポートフォリオ監視 ---
st.header("📉 Real-time Portfolio Monitor")
current_prices = get_live_prices(TICKERS)
 
rows = []
for name, info in st.session_state.portfolio.items():
    cur_price = current_prices.get(name)
    if cur_price:
        profit_loss = (cur_price - info['cost']) / info['cost'] * 100
        rows.append({
            "銘柄": name,
            "保有数": info['shares'],
            "取得単価": f"{info['cost']:,} {info['currency']}",
            "現在値": f"{cur_price:,.2f} {info['currency']}",
            "損益率": f"{profit_loss:+.2f}%"
        })

if rows:
    st.table(pd.DataFrame(rows))
else:
    st.write("株価データ取得中...")

# --- 戦略メモ ---
st.divider()
st.subheader("📋 1% Investor's Reminder")
st.info(f"""
- **Exit Target:** 2026/05/29 終値リバランスの需要を狙い撃つ。
- **Focus:** MU, VRT, IHI の3銘柄に集中。ノイズに惑わされない。
- **Cash Management:** 余力 $10,000 を適切なタイミング（MU押し目など）で投入。
""")

if st.button('画面を更新'):
    st.rerun()
