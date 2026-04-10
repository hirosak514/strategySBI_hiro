
import streamlit as st
import yfinance as yf
import pandas as pd
from datetime import datetime
import google.generativeai as genai
from PIL import Image
import json
import re
import os

# --- 0. データの保存・読み込み (リロード対策) ---
DB_FILE = "portfolio.json"

def load_data():
    if os.path.exists(DB_FILE):
        try:
            with open(DB_FILE, "r") as f:
                return json.load(f)
        except:
            pass
    # 初期値（解析前・精査済みデータ）
    return {
        "MU": {"shares": 71, "cost": 374.88, "currency": "USD"},
        "VRT": {"shares": 70, "cost": 264.44, "currency": "USD"},
        "NEE": {"shares": 105, "cost": 93.75, "currency": "USD"},
        "IHI_LONG": {"shares": 1400, "cost": 3425.4, "currency": "JPY"},
        "IHI_SHORT": {"shares": 300, "cost": 3350.0, "currency": "JPY"}
    }

def save_data(data):
    with open(DB_FILE, "w") as f:
        json.dump(data, f)

# --- 1. セキュリティ設定 (Gemini API) ---
try:
    genai.configure(api_key=st.secrets["GEMINI_API_KEY"])
except Exception:
    st.error("Secretsに 'GEMINI_API_KEY' が設定されていません。")
    st.stop()

# --- 2. 定数・重要日程の設定 ---
DATE_ANNOUNCEMENT = datetime(2026, 5, 12)
DATE_EXIT = datetime(2026, 5, 29)
TICKERS = {"MU": "MU", "VRT": "VRT", "NEE": "NEE", "IHI": "7013.T"}

# --- 3. セッション状態の初期化 ---
if 'portfolio' not in st.session_state:
    st.session_state.portfolio = load_data()

# --- 4. 関数定義 ---
def get_live_prices(tickers_dict):
    prices = {}
    for name, symbol in tickers_dict.items():
        try:
            stock = yf.Ticker(symbol)
            hist = stock.history(period="1d")
            prices[name] = hist['Close'].iloc[-1] if not hist.empty else None
        except:
            prices[name] = None
    # ドル円レートも取得
    try:
        prices["USDJPY"] = yf.Ticker("JPY=X").history(period="1d")['Close'].iloc[-1]
    except:
        prices["USDJPY"] = 159.0 # フォールバック
    return prices

def analyze_image(image):
    model = genai.GenerativeModel('gemini-2.0-flash')
    prompt = """
    あなたは証券アナリストです。添付されたスクリーンショットからMU, VRT, NEE, IHIの情報を抽出し、
    必ず以下の純粋なJSON形式のみで回答してください。
    IHIについては、現物(IHI_LONG)と信用売り(IHI_SHORT)を分けて抽出してください。
    出力例:
    {"MU": {"shares": 71, "cost": 374.88}, "IHI_LONG": {"shares": 1400, "cost": 3425.4}, "IHI_SHORT": {"shares": 300, "cost": 3350.0}}
    """
    response = model.generate_content([prompt, image])
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
            for ticker, vals in new_data.items():
                if ticker in st.session_state.portfolio:
                    st.session_state.portfolio[ticker].update(vals)
            # 解析結果を永続化
            save_data(st.session_state.portfolio)
            st.sidebar.success("解析完了！データを保存しました。")
            st.rerun()
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
rate = current_prices.get("USDJPY", 159.0)
 
rows = []
total_profit = 0

# 米国株の損益計算
for name in ["MU", "VRT", "NEE"]:
    info = st.session_state.portfolio[name]
    cur_price = current_prices.get(name)
    if cur_price:
        profit = (cur_price - info['cost']) * info['shares'] * rate
        total_profit += profit
        rows.append({
            "銘柄": name, "数量": info['shares'], "区分": "現物",
            "取得単価": f"${info['cost']:,}", "現在値": f"${cur_price:,.2f}",
            "損益(円)": f"¥{profit:,.0f}"
        })

# IHI(両建て)の損益計算
ihi_cur = current_prices.get("IHI")
if ihi_cur:
    l_info = st.session_state.portfolio["IHI_LONG"]
    s_info = st.session_state.portfolio["IHI_SHORT"]
    
    l_profit = (ihi_cur - l_info['cost']) * l_info['shares']
    s_profit = (s_info['cost'] - ihi_cur) * s_info['shares']
    total_profit += (l_profit + s_profit)
    
    rows.append({
        "銘柄": "IHI", "数量": l_info['shares'], "区分": "現物(LONG)",
        "取得単価": f"¥{l_info['cost']:,}", "現在値": f"¥{ihi_cur:,.0f}", "損益(円)": f"¥{l_profit:,.0f}"
    })
    rows.append({
        "銘柄": "IHI", "数量": s_info['shares'], "区分": "信用(SHORT)",
        "取得単価": f"¥{s_info['cost']:,}", "現在値": f"¥{ihi_cur:,.0f}", "損益(円)": f"¥{s_profit:,.0f}"
    })

# 総損益サマリー
st.metric("総計損益 (JPY)", f"¥{total_profit:,.0f}", delta=f"USD/JPY: {rate:.2f}")

if rows:
    st.table(pd.DataFrame(rows))
else:
    st.write("株価データ取得中...")

# --- 戦略メモ ---
st.divider()
st.subheader("📋 1% Investor's Reminder")
st.info(f"""
- **Exit Target:** 2026/05/29 終値リバランスの需要を狙い撃つ。
- **Focus:** MU, VRT, IHI の3銘柄に集中。IHIは信用売りを活用したヘッジを継続。
- **Cash Management:** 余力 $10,000 を適切なタイミングで投入。
""")

if st.button('画面を更新'):
    st.rerun()
