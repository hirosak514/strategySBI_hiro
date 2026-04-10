
import streamlit as st
import yfinance as yf
import pandas as pd
from datetime import datetime
import google.generativeai as genai
from PIL import Image
import json
import re
import os

# --- 0. データの永続化（保存・読み込み）ロジック ---
DB_FILE = "portfolio.json"

def load_data():
    """保存されたデータを読み込む。なければ初期値を返す"""
    if os.path.exists(DB_FILE):
        try:
            with open(DB_FILE, "r") as f:
                return json.load(f)
        except:
            pass
    # 初期の精査済みデータ (2026/04/10時点)
    return {
        "MU": {"shares": 71, "cost": 374.88, "currency": "USD"},
        "VRT": {"shares": 70, "cost": 264.44, "currency": "USD"},
        "NEE": {"shares": 105, "cost": 93.75, "currency": "USD"},
        "IHI_LONG": {"shares": 1400, "cost": 3425.4, "currency": "JPY"},
        "IHI_SHORT": {"shares": 300, "cost": 3350.0, "currency": "JPY"}
    }

def save_data(data):
    """データをJSONファイルに保存する"""
    with open(DB_FILE, "w") as f:
        json.dump(data, f)

# --- 1. セッション状態の初期化 ---
if 'portfolio' not in st.session_state:
    st.session_state.portfolio = load_data()

# --- 2. 重要日程・API設定 ---
DATE_EXIT = datetime(2026, 5, 29)
try:
    genai.configure(api_key=st.secrets["GEMINI_API_KEY"])
except:
    st.error("APIキーが設定されていません。")

# --- 3. 関数定義 ---
def get_live_prices():
    """Yahoo Financeから最新株価と為替を取得"""
    tickers = {"MU": "MU", "VRT": "VRT", "NEE": "NEE", "IHI": "7013.T", "USDJPY": "JPY=X"}
    prices = {}
    for name, symbol in tickers.items():
        try:
            stock = yf.Ticker(symbol)
            prices[name] = stock.history(period="1d")['Close'].iloc[-1]
        except:
            prices[name] = 1.0 # エラー時のフォールバック
    return prices

def analyze_image(image):
    """Gemini 2.0 Flashを使用して画像からポジション情報を抽出"""
    model = genai.GenerativeModel('gemini-2.0-flash')
    prompt = """
    あなたは証券アナリストです。添付されたスクリーンショットからMU, VRT, NEE, IHI(7013)の情報を抽出し、
    必ず以下の純粋なJSON形式のみで回答してください。
    IHIについては、現物(LONG)と信用売り(SHORT)を分けて抽出してください。
    出力例:
    {"MU": {"shares": 71, "cost": 374.88}, "IHI_LONG": {"shares": 1400, "cost": 3425.4}, "IHI_SHORT": {"shares": 300, "cost": 3350.0}}
    """
    response = model.generate_content([prompt, image])
    json_str = re.search(r'\{.*\}', response.text, re.DOTALL).group()
    return json.loads(json_str)

# --- 4. Streamlit UI 構築 ---
st.set_page_config(page_title="1% Investor Dashboard", layout="wide")

st.title("🚀 Strategist Dashboard: Hybrid Edition")

# サイドバー: 画像解析
st.sidebar.header("📸 Position Auto-Scanner")
uploaded_file = st.sidebar.file_uploader("スクショをアップロード", type=["png", "jpg", "jpeg"])

if uploaded_file and st.sidebar.button("AIで解析・保存"):
    with st.sidebar.spinner("解析中..."):
        try:
            new_data = analyze_image(Image.open(uploaded_file))
            for k, v in new_data.items():
                if k in st.session_state.portfolio:
                    st.session_state.portfolio[k].update(v)
            save_data(st.session_state.portfolio)
            st.sidebar.success("保存完了！リロードしても保持されます。")
            st.rerun()
        except Exception as e:
            st.sidebar.error(f"解析失敗: {e}")

# メイン画面: カウントダウン
days_left = (DATE_EXIT - datetime.now()).days
st.metric("5/29 出口戦略ターゲットまで", f"あと {days_left} 日")

st.divider()

# 株価取得
prices = get_live_prices()
rate = prices["USDJPY"]

# --- 5. 損益計算と表示 ---
st.header("📉 Real-time Monitor")
p = st.session_state.portfolio

# 米国株データ作成
us_rows = []
total_profit = 0
for ticker in ["MU", "VRT", "NEE"]:
    cur = prices[ticker]
    cost = p[ticker]["cost"]
    shares = p[ticker]["shares"]
    profit = (cur - cost) * shares * rate
    total_profit += profit
    us_rows.append({"銘柄": ticker, "数量": shares, "取得単価": f"${cost:,.2f}", "現在値": f"${cur:,.2f}", "損益(円)": profit})

# IHI(両建て)計算
ihi_cur = prices["IHI"]
ihi_l_profit = (ihi_cur - p["IHI_LONG"]["cost"]) * p["IHI_LONG"]["shares"]
ihi_s_profit = (p["IHI_SHORT"]["cost"] - ihi_cur) * p["IHI_SHORT"]["shares"]
total_profit += (ihi_l_profit + ihi_s_profit)

# サマリー表示
c1, c2 = st.columns(2)
c1.metric("総損益 (日本円計)", f"¥{total_profit:,.0f}")
c2.metric("現在のドル円", f"¥{rate:.2f}")

st.subheader("🇺🇸 米国株")
st.table(pd.DataFrame(us_rows))

st.subheader("🇯🇵 日本株 (IHI 7013 両建て)")
i1, i2, i3 = st.columns(3)
i1.metric("現物買い", f"¥{ihi_l_profit:,.0f}", f"{p['IHI_LONG']['shares']}株")
i2.metric("信用売り", f"¥{ihi_s_profit:,.0f}", f"{p['IHI_SHORT']['shares']}株")
i3.metric("IHI合計", f"¥{ihi_l_profit + ihi_s_profit:,.0f}", "Hedged")

st.divider()
if st.button('データを更新'):
    st.rerun()
