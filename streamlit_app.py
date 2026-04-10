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
EVENT_FILE = "events.json"
REMINDER_FILE = "reminder.json"
CONFIG_FILE = "config.json"

def load_json(file_path, default_value):
    if os.path.exists(file_path):
        try:
            with open(file_path, "r", encoding="utf-8") as f:
                return json.load(f)
        except:
            pass
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

if 'events' not in st.session_state:
    st.session_state.events = load_json(EVENT_FILE, [])

if 'reminder_text' not in st.session_state:
    st.session_state.reminder_text = load_json(REMINDER_FILE, "- ターゲット日程を入力してください\n- 戦略をメモしてください")

if 'api_key' not in st.session_state:
    st.session_state.api_key = load_json(CONFIG_FILE, {"gemini_key": ""})["gemini_key"]

if 'edit_mode' not in st.session_state:
    st.session_state.edit_mode = False

# --- 2. API設定 ---
if st.session_state.api_key:
    genai.configure(api_key=st.session_state.api_key)

# --- 3. 定数・重要日程 ---
DATE_ANNOUNCEMENT = datetime(2026, 5, 12)
DATE_EXIT = datetime(2026, 5, 29)
TICKERS = {"MU": "MU", "VRT": "VRT", "NEE": "NEE", "IHI": "7013.T"}

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
    try:
        prices["USDJPY"] = yf.Ticker("JPY=X").history(period="1d")['Close'].iloc[-1]
    except:
        prices["USDJPY"] = 159.2
    return prices

def analyze_multiple_images(uploaded_files):
    if not st.session_state.api_key:
        raise ValueError("APIキーが設定されていません。")
    model = genai.GenerativeModel('gemini-2.0-flash')
    prompt = """提供されたすべての証券画面からMU, VRT, NEE, IHI(LONG/SHORT)の合計ポジションを抽出しJSONで返してください。"""
    images = [Image.open(f) for f in uploaded_files]
    response = model.generate_content([prompt] + images)
    json_str = re.search(r'\{.*\}', response.text, re.DOTALL).group()
    return json.loads(json_str)

# --- 5. UI構築 ---
st.set_page_config(page_title="MSCI Exit Strategy Dashboard", layout="wide")

# サイドバー: APIキー設定
st.sidebar.header("🔑 System Settings")
input_key = st.sidebar.text_input("Gemini API Key", value=st.session_state.api_key, type="password")
if st.sidebar.button("APIキーを保存"):
    st.session_state.api_key = input_key
    save_json(CONFIG_FILE, {"gemini_key": input_key})
    st.rerun()

st.sidebar.divider()

# サイドバー: 画像アップロード
st.sidebar.header("📸 Multi-Position Update")
uploaded_files = st.sidebar.file_uploader("スクショをドラッグ＆ドロップ (複数可)", type=["png", "jpg", "jpeg"], accept_multiple_files=True)

if uploaded_files and st.sidebar.button("AIで全画像を解析・集計"):
    with st.sidebar.spinner("解析中..."):
        try:
            aggregated_data = analyze_multiple_images(uploaded_files)
            for ticker, vals in aggregated_data.items():
                if ticker in st.session_state.portfolio:
                    st.session_state.portfolio[ticker].update(vals)
            save_json(DB_FILE, st.session_state.portfolio)
            st.rerun()
        except Exception as e:
            st.sidebar.error(f"解析エラー: {e}")

# サイドバー: 📅 Event Manager
st.sidebar.divider()
st.sidebar.header("📅 Event Manager")
new_event_name = st.sidebar.text_input("イベント名を入力")
new_event_date = st.sidebar.date_input("日付を選択", value=datetime.now())
if st.sidebar.button("登録"):
    if new_event_name:
        event_id = len(st.session_state.events) + 1
        st.session_state.events.append({"id": event_id, "name": new_event_name, "date": new_event_date.strftime("%Y-%m-%d")})
        save_json(EVENT_FILE, st.session_state.events)
        st.rerun()

del_id = st.sidebar.number_input("削除するイベントNo", min_value=1, step=1)
if st.sidebar.button("削除"):
    st.session_state.events = [e for e in st.session_state.events if e['id'] != del_id]
    for i, e in enumerate(st.session_state.events): e['id'] = i + 1
    save_json(EVENT_FILE, st.session_state.events)
    st.rerun()

# サイドバー: 📝 Reminder Editor
st.sidebar.divider()
st.sidebar.header("📝 Reminder Editor")
col_ir1, col_ir2 = st.sidebar.columns(2)
if col_ir1.button("IR編集"):
    st.session_state.edit_mode = True
    st.rerun()
if col_ir2.button("登録", key="save_ir"):
    save_json(REMINDER_FILE, st.session_state.reminder_text)
    st.session_state.edit_mode = False
    st.rerun()
if st.session_state.edit_mode:
    st.session_state.reminder_text = st.sidebar.text_area("内容を編集", value=st.session_state.reminder_text, height=200)

# --- メイン画面表示 ---
st.title("🚀 Strategist Dashboard: AI Scanner & Exit Path")

col_fixed1, col_fixed2 = st.columns(2)
days_to_ann = (DATE_ANNOUNCEMENT - datetime.now()).days
days_to_exit = (DATE_EXIT - datetime.now()).days
with col_fixed1: st.metric("MSCI発表まで", f"{days_to_ann} 日")
with col_fixed2: st.metric("出口戦略まで", f"{days_to_exit} 日", delta_color="inverse")

if st.session_state.events:
    st.write("📌 **追加イベント**")
    cols = st.columns(len(st.session_state.events))
    for i, event in enumerate(st.session_state.events):
        e_date = datetime.strptime(event['date'], "%Y-%m-%d")
        with cols[i]: st.metric(f"No.{event['id']}: {event['name']}", f"{(e_date - datetime.now()).days} 日")

st.divider()

# --- ポートフォリオ監視セクション ---
st.header("📉 Real-time Portfolio Monitor")
current_prices = get_live_prices(TICKERS)
rate = current_prices.get("USDJPY", 159.2)
 
rows = []
total_profit = 0
for name in ["MU", "VRT", "NEE"]:
    info = st.session_state.portfolio[name]
    cur = current_prices.get(name)
    if cur:
        profit = (cur - info['cost']) * info['shares'] * rate
        total_profit += profit
        rows.append({"銘柄": name, "数量": info['shares'], "区分": "現物", "取得単価": f"${info['cost']:,}", "現在値": f"${cur:,.2f}", "損益(円)": f"¥{profit:,.0f}"})

ihi_cur = current_prices.get("IHI")
if ihi_cur:
    l_info = st.session_state.portfolio["IHI_LONG"]
    s_info = st.session_state.portfolio["IHI_SHORT"]
    l_profit = (ihi_cur - l_info['cost']) * l_info['shares']
    s_profit = (s_info['cost'] - ihi_cur) * s_info['shares']
    total_profit += (l_profit + s_profit)
    rows.append({"銘柄": "IHI", "数量": l_info['shares'], "区分": "現物(LONG)", "取得単価": f"¥{l_info['cost']:,}", "現在値": f"¥{ihi_cur:,.0f}", "損益(円)": f"¥{l_profit:,.0f}"})
    rows.append({"銘柄": "IHI", "数量": s_info['shares'], "区分": "信用(SHORT)", "取得単価": f"¥{s_info['cost']:,}", "現在値": f"¥{ihi_cur:,.0f}", "損益(円)": f"¥{s_profit:,.0f}"})

# --- 改修ポイント: メトリクスとボタンを横並びに配置 ---
# カラム比率 [3, 1, 6] で左側にメトリクス、そのすぐ右に更新ボタンを置く
m_col1, m_col2, m_col3 = st.columns([3, 1, 6])
with m_col1:
    st.metric("総計損益 (JPY)", f"¥{total_profit:,.0f}", delta=f"USD/JPY: {rate:.2f}")
with m_col2:
    st.write("##") # 位置調整用の余白
    if st.button('更新'):
        st.rerun()

if rows: st.table(pd.DataFrame(rows))

st.divider()
st.subheader("📋 1% Investor's Reminder")
st.info(st.session_state.reminder_text)
