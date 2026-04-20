import streamlit as st
import yfinance as yf
import pandas as pd
from datetime import datetime
import google.generativeai as genai
from PIL import Image
import json
import re
import os
import copy
import gspread
from google.oauth2.service_account import Credentials

# --- 0. データの保存・読み込み ---
DB_FILE = "portfolio.json"
EVENT_FILE = "events.json"
REMINDER_FILE = "reminder.json"
CONFIG_FILE = "config.json"

FIXED_SHEET_URL = "https://docs.google.com/spreadsheets/d/17kAFl14q8EaaQ6kvezlAe1Yzr71Yo673T61--_cyESQ/edit"

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
    st.session_state.portfolio = load_json(DB_FILE, {})
if 'prev_portfolio' not in st.session_state:
    st.session_state.prev_portfolio = None
if 'events' not in st.session_state:
    st.session_state.events = load_json(EVENT_FILE, [])
if 'reminder_text' not in st.session_state:
    st.session_state.reminder_text = load_json(REMINDER_FILE, "- ターゲット日程を入力してください")
if 'api_key' not in st.session_state:
    st.session_state.api_key = load_json(CONFIG_FILE, {"gemini_key": ""}).get("gemini_key", "")

def backup_portfolio():
    st.session_state.prev_portfolio = copy.deepcopy(st.session_state.portfolio)

# --- 2. 価格取得関数 (エラー時もNoneを返さないよう調整) ---
@st.cache_data(ttl=60)
def get_live_prices(portfolio_keys):
    prices = {}
    for key in portfolio_keys:
        symbol = key.split('_')[0]
        is_japan = bool(re.match(r'^\d{4}$', symbol))
        ticker = f"{symbol}.T" if is_japan else ("7013.T" if symbol == "IHI" else symbol)
        try:
            stock = yf.Ticker(ticker)
            # infoが取れない場合はhistoryから補完
            info = stock.info
            current = info.get('regularMarketPrice') or info.get('currentPrice')
            if not current:
                hist = stock.history(period="5d")
                current = hist['Close'].iloc[-1] if not hist.empty else None
            
            prev = info.get('previousClose') or (stock.history(period="5d")['Close'].iloc[-2] if len(stock.history(period="5d"))>=2 else current)
            prices[key] = {"current": current, "prev_close": prev}
        except:
            prices[key] = {"current": None, "prev_close": None}
            
    try:
        usdjpy = yf.Ticker("JPY=X").history(period="1d")['Close'].iloc[-1]
        prices["USDJPY"] = usdjpy
    except:
        prices["USDJPY"] = 159.2
    return prices

# --- 3. UI 構成 (オリジナル完全準拠) ---
st.set_page_config(page_title="Strategist Dashboard", layout="wide")
st.markdown("""<style>[data-testid="stMetricDelta"] > div { color: white !important; }
div[data-testid="column"]:nth-child(3) button { background-color: #ff4b4b !important; color: white !important; }</style>""", unsafe_allow_html=True)

with st.sidebar:
    st.header("🔑 Settings")
    new_key = st.text_input("Gemini API Key", value=st.session_state.api_key, type="password")
    if st.button("APIキーを保存"):
        st.session_state.api_key = new_key
        save_json(CONFIG_FILE, {"gemini_key": new_key})
        st.rerun()

    st.divider()
    st.header("✏️ 銘柄情報の直接入力")
    items = list(st.session_state.portfolio.keys())
    selected_no = None
    if items:
        selected_no = st.selectbox("銘柄No.を選択", options=[i+1 for i in range(len(items))])
        target_key = items[selected_no - 1]
        target_info = st.session_state.portfolio[target_key]
        new_shares = st.number_input(f"数量 ({target_key})", value=float(target_info.get('shares', 0)))
        new_cost = st.number_input(f"取得単価 ({target_key})", value=float(target_info.get('cost', 0)))
        
        c1, c2, c3 = st.columns(3)
        if c1.button("修正"):
            backup_portfolio()
            st.session_state.portfolio[target_key].update({'shares': new_shares, 'cost': new_cost})
            save_json(DB_FILE, st.session_state.portfolio)
            st.rerun()
        if c2.button("復元", type="primary"):
            if st.session_state.prev_portfolio:
                st.session_state.portfolio = copy.deepcopy(st.session_state.prev_portfolio)
                save_json(DB_FILE, st.session_state.portfolio)
                st.rerun()
        if c3.button("削除"):
            backup_portfolio()
            del st.session_state.portfolio[target_key]
            save_json(DB_FILE, st.session_state.portfolio)
            st.rerun()

    st.divider()
    st.header("📌 Event Manager")
    with st.expander("イベント操作"):
        ev_n = st.text_input("名")
        ev_d = st.date_input("日")
        if st.button("追加"):
            st.session_state.events.append({"name": ev_n, "date": ev_d.strftime("%Y-%m-%d")})
            save_json(EVENT_FILE, st.session_state.events)
            st.rerun()

    st.divider()
    st.header("📋 Reminder Edit")
    rem_in = st.text_area("編集", value=st.session_state.reminder_text, height=100)
    if st.button("更新"):
        st.session_state.reminder_text = rem_in
        save_json(REMINDER_FILE, rem_in)
        st.rerun()

# --- 4. メイン画面 ---
st.title("🚀 Strategist Dashboard")

# イベント表示
if st.session_state.events:
    cols = st.columns(len(st.session_state.events))
    for i, ev in enumerate(st.session_state.events):
        d = (datetime.strptime(ev['date'], "%Y-%m-%d") - datetime.now()).days
        cols[i].metric(ev['name'], ev['date'], f"あと {d} 日")

st.divider()
st.header("📉 Portfolio Monitor")
if st.button('最新価格に更新'):
    st.cache_data.clear()
    st.rerun()

prices = get_live_prices(list(st.session_state.portfolio.keys()))
rate = prices.get("USDJPY", 159.2)

rows = []
total_jpy, total_usd = 0, 0

for i, (key, info) in enumerate(st.session_state.portfolio.items()):
    p_data = prices.get(key, {"current": None, "prev_close": None})
    cur = p_data["current"]
    prev = p_data["prev_close"]
    
    # 価格が取れない場合でも行を表示するための処理
    day_chg = f"({(cur-prev)/prev*100:+.2f}%)" if (cur and prev) else "---"
    cur_val = cur if cur else 0
    
    if "_SHORT" in key:
        label, p_jpy = "信用(売)", (info['cost'] - cur_val) * info['shares']
    elif "_MARGIN_LONG" in key:
        label, p_jpy = "信用(買)", (cur_val - info['cost']) * info['shares']
    else:
        label = "現物"
        if info.get('currency') == "USD":
            p_usd = (cur_val - info['cost']) * info['shares']
            p_jpy = p_usd * rate
            total_usd += p_usd
        else: p_jpy = (cur_val - info['cost']) * info['shares']

    total_jpy += p_jpy
    
    # テーブル表示用の整形
    cur_disp = f"{cur_val:,.2f} {day_chg}" if cur_val > 0 else "取得不可"
    rows.append({
        "No.": i+1, "銘柄": f"{key.split('_')[0]} {info.get('name','')}", "数量": info['shares'],
        "区分": label, "取得単価": f"{info['cost']:,}", "現在値": cur_disp, "損益(円)": f"¥{p_jpy:,.0f}"
    })

m1, m2 = st.columns(2)
m1.metric("総合計損益 (JPY)", f"¥{total_jpy:,.0f}", delta=f"USD/JPY: {rate:.2f}")
m2.metric("米国株損益 (USD)", f"${total_usd:,.2f}")

if rows: st.table(pd.DataFrame(rows))
st.divider()
st.subheader("📋 Reminder")
st.info(st.session_state.reminder_text)
