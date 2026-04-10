
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

def load_data():
    if os.path.exists(DB_FILE):
        try:
            with open(DB_FILE, "r") as f:
                return json.load(f)
        except:
            pass
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

def load_events():
    if os.path.exists(EVENT_FILE):
        try:
            with open(EVENT_FILE, "r") as f:
                return json.load(f)
        except:
            pass
    return []

def save_events(events):
    with open(EVENT_FILE, "w") as f:
        json.dump(events, f)

def load_reminder():
    if os.path.exists(REMINDER_FILE):
        try:
            with open(REMINDER_FILE, "r") as f:
                return json.load(f)
        except:
            pass
    return """- **Exit Target:** 2026/05/29 終値リバランスの需要を狙い撃つ。
- **Focus:** MU, VRT, IHI の3銘柄に集中。IHIは信用売りを活用したヘッジを継続。
- **Cash Management:** 余力 $10,000 を適切なタイミングで投入。"""

def save_reminder(text):
    with open(REMINDER_FILE, "w") as f:
        json.dump(text, f)

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
if 'events' not in st.session_state:
    st.session_state.events = load_events()
if 'reminder_text' not in st.session_state:
    st.session_state.reminder_text = load_reminder()
if 'edit_mode' not in st.session_state:
    st.session_state.edit_mode = False

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
        prices["USDJPY"] = 159.0
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

# --- サイドバー: 画像アップロード & イベント管理 ---
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
            save_data(st.session_state.portfolio)
            st.sidebar.success("解析完了！データを保存しました。")
            st.rerun()
        except Exception as e:
            st.sidebar.error(f"解析エラー: {e}")

st.sidebar.divider()
st.sidebar.header("📅 Event Manager")

new_event_name = st.sidebar.text_input("イベント名を入力")
new_event_date = st.sidebar.date_input("日付を選択", value=datetime.now())

if st.sidebar.button("登録"):
    if new_event_name:
        event_id = len(st.session_state.events) + 1
        new_event = {"id": event_id, "name": new_event_name, "date": new_event_date.strftime("%Y-%m-%d")}
        st.session_state.events.append(new_event)
        save_events(st.session_state.events)
        st.rerun()

st.sidebar.divider()
del_id = st.sidebar.number_input("削除するイベントNo", min_value=1, step=1)
if st.sidebar.button("削除"):
    st.session_state.events = [e for e in st.session_state.events if e['id'] != del_id]
    for i, e in enumerate(st.session_state.events):
        e['id'] = i + 1
    save_events(st.session_state.events)
    st.rerun()

# --- IR編集機能の追加 ---
st.sidebar.divider()
st.sidebar.header("📝 Reminder Editor")
col_ir1, col_ir2 = st.sidebar.columns(2)
if col_ir1.button("IR編集"):
    st.session_state.edit_mode = True
    st.rerun()

if col_ir2.button("登録", key="save_ir"):
    save_reminder(st.session_state.reminder_text)
    st.session_state.edit_mode = False
    st.sidebar.success("Reminderを更新しました")
    st.rerun()

if st.session_state.edit_mode:
    st.session_state.reminder_text = st.sidebar.text_area("内容を編集", value=st.session_state.reminder_text, height=200)

# --- メイン画面: カウントダウン ---
col_fixed1, col_fixed2 = st.columns(2)
days_to_ann = (DATE_ANNOUNCEMENT - datetime.now()).days
days_to_exit = (DATE_EXIT - datetime.now()).days

with col_fixed1:
    st.metric("MSCI発表 (5/12) まで", f"{days_to_ann} 日")
with col_fixed2:
    st.metric("出口戦略 (5/29) まで", f"{days_to_exit} 日", delta_color="inverse")

if st.session_state.events:
    st.write("📌 **追加イベント**")
    cols = st.columns(len(st.session_state.events))
    for i, event in enumerate(st.session_state.events):
        e_date = datetime.strptime(event['date'], "%Y-%m-%d")
        e_days = (e_date - datetime.now()).days
        with cols[i]:
            st.metric(f"No.{event['id']}: {event['name']}", f"{e_days} 日")

st.divider()

# --- メイン画面: ポートフォリオ監視 ---
st.header("📉 Real-time Portfolio Monitor")
current_prices = get_live_prices(TICKERS)
rate = current_prices.get("USDJPY", 159.0)
 
rows = []
total_profit = 0

for name in ["MU", "VRT", "NEE"]:
    info = st.session_state.portfolio[name]
    cur_price = current_prices.get(name)
    if cur_price:
        profit = (cur_price - info['cost']) * info['shares'] * rate
        total_profit += profit
        rows.append({"銘柄": name, "数量": info['shares'], "区分": "現物", "取得単価": f"${info['cost']:,}", "現在値": f"${cur_price:,.2f}", "損益(円)": f"¥{profit:,.0f}"})

ihi_cur = current_prices.get("IHI")
if ihi_cur:
    l_info = st.session_state.portfolio["IHI_LONG"]
    s_info = st.session_state.portfolio["IHI_SHORT"]
    l_profit = (ihi_cur - l_info['cost']) * l_info['shares']
    s_profit = (s_info['cost'] - ihi_cur) * s_info['shares']
    total_profit += (l_profit + s_profit)
    rows.append({"銘柄": "IHI", "数量": l_info['shares'], "区分": "現物(LONG)", "取得単価": f"¥{l_info['cost']:,}", "現在値": f"¥{ihi_cur:,.0f}", "損益(円)": f"¥{l_profit:,.0f}"})
    rows.append({"銘柄": "IHI", "数量": s_info['shares'], "区分": "信用(SHORT)", "取得単価": f"¥{s_info['cost']:,}", "現在値": f"¥{ihi_cur:,.0f}", "損益(円)": f"¥{s_profit:,.0f}"})

st.metric("総計損益 (JPY)", f"¥{total_profit:,.0f}", delta=f"USD/JPY: {rate:.2f}")

if rows:
    st.table(pd.DataFrame(rows))
else:
    st.write("株価データ取得中...")

st.divider()
st.subheader("📋 1% Investor's Reminder")
st.info(st.session_state.reminder_text)

if st.button('画面を更新'):
    st.rerun()
