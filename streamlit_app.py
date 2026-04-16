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
if 'portfolio' not in st.session_state: st.session_state.portfolio = load_json(DB_FILE, {})
if 'events' not in st.session_state: st.session_state.events = load_json(EVENT_FILE, [])
if 'reminder_text' not in st.session_state: st.session_state.reminder_text = load_json(REMINDER_FILE, "- ターゲット日程を入力してください")
if 'api_key' not in st.session_state: st.session_state.api_key = load_json(CONFIG_FILE, {"gemini_key": ""})["gemini_key"]
if 'edit_mode' not in st.session_state: st.session_state.edit_mode = False

# --- 2. API設定 ---
current_api_key = st.session_state.api_key
if not current_api_key:
    try: current_api_key = st.secrets.get("GEMINI_API_KEY", "")
    except: pass
if current_api_key: genai.configure(api_key=current_api_key)

# --- 3. 解析・価格取得関数 ---
def get_live_prices(portfolio_keys):
    prices = {}
    for key in portfolio_keys:
        symbol = key.split('_')[0]
        ticker = f"{symbol}.T" if symbol.isdigit() and len(symbol) == 4 else ( "7013.T" if symbol == "IHI" else symbol )
        try:
            hist = yf.Ticker(ticker).history(period="5d")
            if not hist.empty:
                prices[key] = {"current": hist['Close'].iloc[-1], "prev_close": hist['Close'].iloc[-2] if len(hist) >= 2 else None}
            else: prices[key] = None
        except: prices[key] = None
    try:
        usdjpy = yf.Ticker("JPY=X").history(period="5d")
        prices["USDJPY"] = usdjpy['Close'].iloc[-1] if not usdjpy.empty else 159.2
    except: prices["USDJPY"] = 159.2
    return prices

def analyze_multiple_images(uploaded_files):
    if not current_api_key: raise ValueError("APIキー未設定")
    model = genai.GenerativeModel("gemini-1.5-flash") # モデル名を直接指定
    prompt = """証券口座画像から銘柄抽出。JSON形式のみで回答: {"キー": {"name": "銘柄名", "shares": 数量, "cost": 取得単価, "currency": "JPY" or "USD"}}"""
    images = [Image.open(f) for f in uploaded_files]
    response = model.generate_content([prompt] + images)
    json_match = re.search(r'\{.*\}', response.text, re.DOTALL)
    if not json_match: raise ValueError("AI解析に失敗")
    return json.loads(json_match.group())

# --- 4. UI (サイドバー処理を優先) ---
st.set_page_config(page_title="Strategist Dashboard", layout="wide")

# サイドバー
st.sidebar.header("🔑 Settings")
input_key = st.sidebar.text_input("Gemini API Key", value=st.session_state.api_key, type="password")
if st.sidebar.button("APIキーを保存", key="btn_save_key"):
    st.session_state.api_key = input_key
    save_json(CONFIG_FILE, {"gemini_key": input_key})
    st.rerun()

st.sidebar.divider()
st.sidebar.subheader("💾 Backup")
backup_data = {"portfolio": st.session_state.portfolio, "events": st.session_state.events, "reminder_text": st.session_state.reminder_text}
st.sidebar.download_button("設定保存(Export)", json.dumps(backup_data, ensure_ascii=False, indent=4), f"backup_{datetime.now().strftime('%Y%m%d')}.json", "application/json")

uploaded_config = st.sidebar.file_uploader("設定読込(Import)", type=["json"])
if uploaded_config and st.sidebar.button("読込実行", key="btn_import"):
    try:
        loaded = json.load(uploaded_config)
        st.session_state.portfolio = loaded.get("portfolio", {})
        st.session_state.events = loaded.get("events", [])
        st.session_state.reminder_text = loaded.get("reminder_text", "")
        save_json(DB_FILE, st.session_state.portfolio)
        save_json(EVENT_FILE, st.session_state.events)
        save_json(REMINDER_FILE, st.session_state.reminder_text)
        st.rerun()
    except Exception as e: st.sidebar.error(f"Error: {e}")

st.sidebar.divider()
st.sidebar.header("📸 AI Scanner")
up_files = st.sidebar.file_uploader("スクショ", type=["png", "jpg", "jpeg"], accept_multiple_files=True)
if up_files and st.sidebar.button("AI解析実行", key="btn_ai_scan"):
    try:
        new_data = analyze_multiple_images(up_files)
        st.session_state.portfolio = new_data
        save_json(DB_FILE, new_data)
        st.rerun()
    except Exception as e: st.sidebar.error(f"Error: {e}")

# --- 5. メイン表示 ---
st.title("🚀 Strategist Dashboard")

if st.session_state.events:
    st.write("📌 **追加イベント**")
    cols = st.columns(len(st.session_state.events))
    for i, event in enumerate(st.session_state.events):
        e_date = datetime.strptime(event['date'], "%Y-%m-%d")
        with cols[i]: st.metric(f"{event['name']}", f"{(e_date - datetime.now()).days}日")

st.divider()
st.header("📉 Portfolio Monitor")

# 更新ボタン（固定キー）
if st.button('最新価格に更新', key="main_update_btn"):
    st.rerun()

current_data = get_live_prices(st.session_state.portfolio.keys())
rate = current_data.get("USDJPY", 159.2)
rows = []
total_profit_jpy = 0
total_profit_usd = 0

for key, info in st.session_state.portfolio.items():
    data = current_data.get(key)
    if data and info['shares'] > 0:
        cur, prev = data["current"], data["prev_close"]
        day_change = f"({(cur-prev)/prev*100:+.2f}%)" if prev else ""
        
        # 損益計算（踏襲）
        if "_SHORT" in key: p_jpy = (info['cost'] - cur) * info['shares']
        elif "_MARGIN_LONG" in key: p_jpy = (cur - info['cost']) * info['shares']
        else:
            if info.get('currency') == "USD":
                p_usd = (cur - info['cost']) * info['shares']
                p_jpy, total_profit_usd = p_usd * rate, total_profit_usd + p_usd
            else: p_jpy = (cur - info['cost']) * info['shares']
        
        total_profit_jpy += p_jpy
        symbol_only = key.split('_')[0]
        cur_disp = f"{('$' if info.get('currency') == 'USD' else '¥')}{cur:,.2f} {day_change}"
        rows.append({"銘柄": f"{symbol_only} {info.get('name','')}", "数量": info['shares'], "区分": "信用" if "MARGIN" in key or "SHORT" in key else "現物", "取得単価": f"{info['cost']:,}", "現在値": cur_disp, "損益(円)": f"¥{p_jpy:,.0f}"})

col_m1, col_m2 = st.columns(2)
col_m1.metric("総計損益 (JPY)", f"¥{total_profit_jpy:,.0f}", delta=f"USD/JPY: {rate:.2f}")
col_m2.metric("米国株損益 (USD)", f"${total_profit_usd:,.2f}")

if rows:
    st.table(pd.DataFrame(rows))
else:
    st.info("データがありません。サイドバーからインポートまたは解析してください。")

st.divider()
st.subheader("📋 Reminder")
st.info(st.session_state.reminder_text)
