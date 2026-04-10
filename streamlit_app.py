import streamlit as st
import yfinance as yf
import pandas as pd
from datetime import datetime
import google.generativeai as genai
from PIL import Image
import json
import re
import os

# --- 0. データの保存・読み込み ---
DB_FILE = "portfolio.json"
EVENT_FILE = "events.json"
REMINDER_FILE = "reminder.json"
CONFIG_FILE = "config.json"

def load_json(file_path, default_value):
    if os.path.exists(file_path):
        try:
            with open(file_path, "r", encoding="utf-8") as f:
                return json.load(f)
        except: pass
    return default_value

def save_json(file_path, data):
    with open(file_path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=4)

# --- 1. セッション状態の初期化 ---
if 'portfolio' not in st.session_state:
    st.session_state.portfolio = load_json(DB_FILE, {
        "MU": {"shares": 71, "cost": 374.88, "currency": "USD"},
        "VRT": {"shares": 70, "cost": 264.44, "currency": "USD"},
        "NEE": {"shares": 105, "cost": 93.75, "currency": "USD"},
        "IHI_LONG": {"shares": 1400, "cost": 3425.4, "currency": "JPY"},
        "IHI_SHORT": {"shares": 300, "cost": 3350.0, "currency": "JPY"}

    })

for key in ['events', 'reminder_text', 'api_key']:
    if key not in st.session_state:
        default = [] if key == 'events' else ""
        if key == 'reminder_text': default = "- 戦略メモ"
        st.session_state[key] = load_json(f"{key}.json", default)

if 'edit_mode' not in st.session_state: st.session_state.edit_mode = False

# --- 2. API設定 ---
if st.session_state.api_key:
    genai.configure(api_key=st.session_state.api_key)

# --- 3. 定数 ---
DATE_ANNOUNCEMENT = datetime(2026, 5, 12)
DATE_EXIT = datetime(2026, 5, 29)
TICKERS = {"MU": "MU", "VRT": "VRT", "NEE": "NEE", "IHI": "7013.T"}

# --- 4. 解析関数（究極の自動判別ロジック） ---
def analyze_multiple_images(uploaded_files):
    if not st.session_state.api_key:
        raise ValueError("APIキーが設定されていません。")
    
    # 【解決の鍵】利用可能なモデルをリストアップし、画像が読めるものを自動選択
    available_models = []
    try:
        for m in genai.list_models():
            if 'generateContent' in m.supported_generation_methods:
                # 'models/gemini-1.5-flash' のようなフルネームを保持
                available_models.append(m.name)
    except Exception as e:
        raise ValueError(f"モデルリストの取得に失敗しました: {e}")

    if not available_models:
        raise ValueError("画像解析に対応したモデルが見つかりません。ライブラリを更新してください。")

    # 優先順位（Flash系があれば優先、なければ最初に見つかったもの）
    target_model = next((m for m in available_models if "flash" in m), available_models[0])
    model = genai.GenerativeModel(target_model)
    
    prompt = """
    証券画面から MU, VRT, NEE, IHI(LONG/SHORT) の合計株数と取得単価を抽出し、以下のJSON形式のみで出力してください。
    {"MU": {"shares": 0, "cost": 0.0}, "VRT": {"shares": 0, "cost": 0.0}, "NEE": {"shares": 0, "cost": 0.0}, "IHI_LONG": {"shares": 0, "cost": 0.0}, "IHI_SHORT": {"shares": 0, "cost": 0.0}}
    """
    
    images = [Image.open(f) for f in uploaded_files]
    response = model.generate_content([prompt] + images)
    
    json_match = re.search(r'\{.*\}', response.text, re.DOTALL)
    if not json_match:
        raise ValueError("JSONを抽出できませんでした。")
        
    return json.loads(json_match.group())

# --- 5. UI構築 ---
st.set_page_config(page_title="MSCI Exit Strategy Dashboard", layout="wide")

# サイドバー: APIキー設定
st.sidebar.header("🔑 System Settings")
input_key = st.sidebar.text_input("Gemini API Key", value=st.session_state.api_key, type="password")
if st.sidebar.button("APIキーを保存"):
    st.session_state.api_key = input_key
    save_json("api_key.json", input_key)
    st.rerun()

st.sidebar.divider()

# サイドバー: 画像アップロード
st.sidebar.header("📸 Multi-Position Update")
uploaded_files = st.sidebar.file_uploader("スクショをドラッグ＆ドロップ", type=["png", "jpg", "jpeg"], accept_multiple_files=True)

if uploaded_files and st.sidebar.button("AIで全画像を解析・集計"):
    with st.sidebar.spinner(f"モデルを自動選択して解析中..."):
        try:
            aggregated_data = analyze_multiple_images(uploaded_files)
            for ticker, vals in aggregated_data.items():
                if ticker in st.session_state.portfolio:
                    st.session_state.portfolio[ticker].update(vals)
            save_json(DB_FILE, st.session_state.portfolio)
            st.rerun()
        except Exception as e:
            st.sidebar.error(f"解析エラー: {e}")

# ... (以降のUIパーツ：Event Manager, Portfolio Monitor, 更新ボタン配置は前回の仕様を完全踏襲) ...

# (以下、以前のメイン表示ロジックをそのまま継続)
def get_live_prices(tickers_dict):
    prices = {}
    for name, symbol in tickers_dict.items():
        try:
            stock = yf.Ticker(symbol)
            hist = stock.history(period="1d")
            prices[name] = hist['Close'].iloc[-1] if not hist.empty else None
        except: prices[name] = None
    try: prices["USDJPY"] = yf.Ticker("JPY=X").history(period="1d")['Close'].iloc[-1]
    except: prices["USDJPY"] = 159.2
    return prices

st.title("🚀 Strategist Dashboard: AI Scanner")
col_f1, col_f2 = st.columns(2)
with col_f1: st.metric("MSCI発表まで", f"{(DATE_ANNOUNCEMENT - datetime.now()).days} 日")
with col_f2: st.metric("出口戦略まで", f"{(DATE_EXIT - datetime.now()).days} 日", delta_color="inverse")

st.divider()
st.header("📉 Real-time Portfolio Monitor")
cp = get_live_prices(TICKERS)
rate = cp.get("USDJPY", 159.2)
rows = []
total_profit = 0
for n in ["MU", "VRT", "NEE"]:
    info = st.session_state.portfolio[n]
    if cp.get(n):
        p = (cp[n] - info['cost']) * info['shares'] * rate
        total_profit += p
        rows.append({"銘柄": n, "数量": info['shares'], "区分": "現物", "取得単価": f"${info['cost']:,}", "現在値": f"${cp[n]:,.2f}", "損益(円)": f"¥{p:,.0f}"})

i_cur = cp.get("IHI")
if i_cur:
    l_i, s_i = st.session_state.portfolio["IHI_LONG"], st.session_state.portfolio["IHI_SHORT"]
    lp, sp = (i_cur - l_i['cost']) * l_i['shares'], (s_i['cost'] - i_cur) * s_i['shares']
    total_profit += (lp + sp)
    rows.append({"銘柄": "IHI", "数量": l_i['shares'], "区分": "現物(LONG)", "取得単価": f"¥{l_i['cost']:,}", "現在値": f"¥{i_cur:,.0f}", "損益(円)": f"¥{lp:,.0f}"})
    rows.append({"銘柄": "IHI", "数量": s_i['shares'], "区分": "信用(SHORT)", "取得単価": f"¥{s_i['cost']:,}", "現在値": f"¥{i_cur:,.0f}", "損益(円)": f"¥{sp:,.0f}"})

m_col1, m_col2, _ = st.columns([3, 1, 6])
with m_col1: st.metric("総計損益 (JPY)", f"¥{total_profit:,.0f}", delta=f"USD/JPY: {rate:.2f}")
with m_col2: 
    st.write("##")
    if st.button('更新'): st.rerun()

if rows: st.table(pd.DataFrame(rows))
st.divider()
st.subheader("📋 1% Investor's Reminder")
st.info(st.session_state.reminder_text)
