import streamlit as st
import yfinance as yf
import pandas as pd
from datetime import datetime
import google.generativeai as genai
from PIL import Image
import json
import re
import os

# --- 0. データの保存・読み込み (配布・クラウド対応) ---
def init_session_state():
    if 'portfolio' not in st.session_state:
        st.session_state.portfolio = {}
    if 'events' not in st.session_state:
        st.session_state.events = []
    if 'reminder_text' not in st.session_state:
        st.session_state.reminder_text = "- ターゲット日程を入力してください"
    if 'show_help' not in st.session_state:
        st.session_state.show_help = False
    if 'edit_mode' not in st.session_state:
        st.session_state.edit_mode = False

init_session_state()

# --- 1. API設定 ---
api_key = st.session_state.get("custom_api_key", "")
if not api_key:
    # Streamlit CloudのSecrets対応
    try:
        api_key = st.secrets.get("GEMINI_API_KEY", "")
    except:
        api_key = ""

if api_key:
    genai.configure(api_key=api_key)

# --- 2. 重要日程 ---
DATE_ANNOUNCEMENT = datetime(2026, 5, 12)
DATE_EXIT = datetime(2026, 5, 29)

# --- 3. 解析・価格取得関数 ---
def analyze_multiple_images(uploaded_files):
    if not api_key:
        raise ValueError("APIキーが設定されていません。サイドバーから入力してください。")
    
    model = genai.GenerativeModel("gemini-1.5-flash")
    prompt = """
    証券口座の画像から、保有銘柄を抽出してください。
    【抽出ルール】
    1. 日本株(ETF含む)：codeは4桁コード、nameは銘柄名。
    2. 米国株：codeはティッカー、nameは企業名。
    3. 信用「売建」はcode末尾に "_SHORT" を付与。
    4. 日本円決済は currency: "JPY"、米ドル決済は currency: "USD"。
    JSON形式のみで回答：
    {"コード": {"name": "名前", "shares": 数量, "cost": 取得単価, "currency": "JPY/USD"}}
    """
    images = [Image.open(f) for f in uploaded_files]
    response = model.generate_content([prompt] + images)
    json_match = re.search(r'\{.*\}', response.text, re.DOTALL)
    if not json_match: raise ValueError("AI解析に失敗しました。")
    return json.loads(json_match.group())

def get_live_prices(portfolio_keys):
    prices = {}
    for key in portfolio_keys:
        symbol = key.split('_')[0]
        ticker_symbol = f"{symbol}.T" if symbol.isdigit() and len(symbol) == 4 else ( "7013.T" if symbol == "IHI" else symbol )
        try:
            stock = yf.Ticker(ticker_symbol)
            hist = stock.history(period="1d")
            prices[key] = hist['Close'].iloc[-1] if not hist.empty else None
        except: prices[key] = None
    try: prices["USDJPY"] = yf.Ticker("JPY=X").history(period="1d")['Close'].iloc[-1]
    except: prices["USDJPY"] = 159.2
    return prices

# --- 4. UI構築 ---
st.set_page_config(page_title="MSCI Exit Strategy Dashboard", layout="wide")

# サイドバー: System Settings
st.sidebar.header("🔑 System Settings")
input_key = st.sidebar.text_input("Gemini API Key", value=st.session_state.get("custom_api_key", ""), type="password")

col_api1, col_api2 = st.sidebar.columns(2)
if col_api1.button("APIキーを適用", use_container_width=True):
    st.session_state.custom_api_key = input_key
    st.rerun()

if col_api2.button("APIキーとは", use_container_width=True):
    st.session_state.show_help = not st.session_state.show_help
    st.rerun()

if st.session_state.show_help:
    st.sidebar.info("Google AI Studioで取得したAPIキーを入力すると、画像解析機能が有効になります。")

st.sidebar.divider()

# サイドバー: 📸 Portfolio Update
st.sidebar.header("📸 Portfolio Update")
uploaded_files = st.sidebar.file_uploader("スクショをアップロード", type=["png", "jpg", "jpeg"], accept_multiple_files=True)
if uploaded_files and st.sidebar.button("AI解析実行"):
    with st.sidebar.spinner("解析中..."):
        try:
            data = analyze_multiple_images(uploaded_files)
            st.session_state.portfolio.update(data)
            st.rerun()
        except Exception as e: st.sidebar.error(f"解析エラー: {e}")

# サイドバー: 📅 Event Manager (完全踏襲)
st.sidebar.divider()
st.sidebar.header("📅 Event Manager")
new_event_name = st.sidebar.text_input("イベント名を入力")
new_event_date = st.sidebar.date_input("日付を選択", value=datetime.now())
if st.sidebar.button("イベント登録"):
    if new_event_name:
        st.session_state.events.append({
            "id": len(st.session_state.events) + 1,
            "name": new_event_name,
            "date": new_event_date.strftime("%Y-%m-%d")
        })
        st.rerun()

if st.session_state.events:
    del_id = st.sidebar.number_input("削除するNo", min_value=1, step=1)
    if st.sidebar.button("選択したイベントを削除"):
        st.session_state.events = [e for e in st.session_state.events if e['id'] != del_id]
        for i, e in enumerate(st.session_state.events): e['id'] = i + 1
        st.rerun()

# サイドバー: 📝 Reminder Editor
st.sidebar.divider()
st.sidebar.header("📝 Reminder Editor")
col_ir1, col_ir2 = st.sidebar.columns(2)
if col_ir1.button("編集"): st.session_state.edit_mode = True; st.rerun()
if col_ir2.button("確定"): st.session_state.edit_mode = False; st.rerun()
if st.session_state.edit_mode:
    st.session_state.reminder_text = st.sidebar.text_area("内容を編集", value=st.session_state.reminder_text, height=150)

# --- 5. メイン画面表示 ---
st.title("🚀 Strategist Dashboard: AI Scanner")

# 固定イベント（MSCI日程）
col_f1, col_f2 = st.columns(2)
with col_f1: st.metric("MSCI発表まで", f"{(DATE_ANNOUNCEMENT - datetime.now()).days} 日")
with col_f2: st.metric("出口戦略まで", f"{(DATE_EXIT - datetime.now()).days} 日")

# 【修正点】登録済みイベントの表示エリアを復旧
if st.session_state.events:
    st.write("📌 **追加カスタムイベント**")
    event_cols = st.columns(min(len(st.session_state.events), 4)) # 最大4列で表示
    for i, event in enumerate(st.session_state.events):
        e_date = datetime.strptime(event['date'], "%Y-%m-%d")
        diff_days = (e_date - datetime.now()).days
        with event_cols[i % 4]:
            st.metric(f"No.{event['id']}: {event['name']}", f"{diff_days} 日")

st.divider()

# ポートフォリオ監視
st.header("📉 Real-time Portfolio Monitor")
current_prices = get_live_prices(st.session_state.portfolio.keys())
rate = current_prices.get("USDJPY", 159.2)
rows = []
total_profit_jpy = 0
total_profit_usd_only_us_stocks = 0

for key, info in st.session_state.portfolio.items():
    cur = current_prices.get(key)
    if cur and info['shares'] > 0:
        display_name = f"{key.split('_')[0]} {info.get('name', '')}"
        if info.get('currency') == "USD":
            p_usd = (cur - info['cost']) * info['shares']
            p_jpy = p_usd * rate
            total_profit_usd_only_us_stocks += p_usd
            total_profit_jpy += p_jpy
            rows.append({"銘柄": display_name, "数量": info['shares'], "区分": "米国株", "取得単価": f"${info['cost']:,}", "現在値": f"${cur:,.2f}", "損益(円)": f"¥{p_jpy:,.0f}"})
        else:
            p_jpy = (info['cost'] - cur if "_SHORT" in key else cur - info['cost']) * info['shares']
            total_profit_jpy += p_jpy
            rows.append({"銘柄": display_name, "数量": info['shares'], "区分": "日本株(売建)" if "_SHORT" in key else "日本株/ETF", "取得単価": f"¥{info['cost']:,}", "現在値": f"¥{cur:,.0f}", "損益(円)": f"¥{p_jpy:,.0f}"})

m_col1, m_col2, m_col3 = st.columns([3, 2, 5])
with m_col1: st.metric("総計損益 (JPY)", f"¥{total_profit_jpy:,.0f}", delta=f"USD/JPY: {rate:.2f}")
with m_col2: st.metric("米国株損益 (USD)", f"${total_profit_usd_only_us_stocks:,.2f}")
with m_col3: 
    st.write("##")
    if st.button('更新'): st.rerun()

if rows:
    st.table(pd.DataFrame(rows))
    st.download_button("JSONで保存", data=json.dumps(st.session_state.portfolio, ensure_ascii=False), file_name="portfolio.json")
else:
    st.info("サイドバーからスクショをアップロードしてください。")

st.divider()
st.subheader("📋 Reminder")
st.info(st.session_state.reminder_text)
