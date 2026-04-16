import streamlit as st
import yfinance as yf
import pandas as pd
from datetime import datetime
import google.generativeai as genai
from PIL import Image
import json
import re
import os

# --- 0. データの保存・読み込み (安全版) ---
DB_FILE = "portfolio.json"
EVENT_FILE = "events.json"
REMINDER_FILE = "reminder.json"
CONFIG_FILE = "config.json"

def load_json(file_path, default_value):
    try:
        if os.path.exists(file_path):
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
if 'reminder_text' not in st.session_state: st.session_state.reminder_text = load_json(REMINDER_FILE, "- ターゲット日程を入力")
if 'api_key' not in st.session_state: st.session_state.api_key = load_json(CONFIG_FILE, {"gemini_key": ""}).get("gemini_key", "")
if 'edit_mode' not in st.session_state: st.session_state.edit_mode = False

# --- 2. API設定 ---
current_api_key = st.session_state.api_key or st.secrets.get("GEMINI_API_KEY", "")
if current_api_key: genai.configure(api_key=current_api_key)

# --- 3. 解析・価格取得関数 ---
def get_live_prices(portfolio_keys):
    prices = {}
    for key in portfolio_keys:
        symbol = key.split('_')[0]
        is_japan = symbol.isdigit() and len(symbol) == 4
        ticker = f"{symbol}.T" if is_japan else ( "7013.T" if symbol == "IHI" else symbol )
        
        try:
            # 前日比を出さないため、period="1d" で現在値のみ取得
            stock = yf.Ticker(ticker)
            hist = stock.history(period="1d")
            if not hist.empty:
                prices[key] = {"current": hist['Close'].iloc[-1]}
            else: prices[key] = None
        except: prices[key] = None
        
    try:
        usdjpy = yf.Ticker("JPY=X").history(period="1d")
        prices["USDJPY"] = usdjpy['Close'].iloc[-1] if not usdjpy.empty else 159.2
    except: prices["USDJPY"] = 159.2
    return prices

def analyze_multiple_images(uploaded_files):
    if not current_api_key: raise ValueError("APIキー未設定")
    model = genai.GenerativeModel("gemini-1.5-flash")
    prompt = """証券口座画像から銘柄抽出。JSON形式のみ回答: {"キー": {"name": "銘柄名", "shares": 数量, "cost": 取得単価, "currency": "JPY" or "USD"}}"""
    images = [Image.open(f) for f in uploaded_files]
    response = model.generate_content([prompt] + images)
    json_match = re.search(r'\{.*\}', response.text, re.DOTALL)
    if not json_match: raise ValueError("解析失敗")
    return json.loads(json_match.group())

# --- 4. UI ---
st.set_page_config(page_title="Strategist Dashboard", layout="wide")

# サイドバー処理
with st.sidebar:
    st.header("🔑 Settings")
    new_key = st.text_input("Gemini API Key", value=st.session_state.api_key, type="password")
    if st.button("保存", key="save_api"):
        st.session_state.api_key = new_key
        save_json(CONFIG_FILE, {"gemini_key": new_key})
        st.rerun()

    st.divider()
    st.subheader("💾 Backup")
    backup_data = {
        "portfolio": st.session_state.get("portfolio", {}),
        "events": st.session_state.get("events", []),
        "reminder_text": st.session_state.get("reminder_text", "")
    }
    st.download_button("Export (JSON)", json.dumps(backup_data, ensure_ascii=False, indent=4), "backup.json", "application/json")

    up_config = st.file_uploader("Import (JSON)", type=["json"])
    if up_config and st.button("実行", key="do_import"):
        try:
            loaded = json.load(up_config)
            st.session_state.portfolio = loaded.get("portfolio", {})
            st.session_state.events = loaded.get("events", [])
            st.session_state.reminder_text = loaded.get("reminder_text", "- ターゲット日程を入力")
            save_json(DB_FILE, st.session_state.portfolio)
            save_json(EVENT_FILE, st.session_state.events)
            save_json(REMINDER_FILE, st.session_state.reminder_text)
            st.rerun()
        except Exception as e: st.error(f"Error: {e}")

    st.divider()
    st.header("📸 AI Scanner")
    up_files = st.file_uploader("スクショ", type=["png", "jpg", "jpeg"], accept_multiple_files=True)
    if up_files and st.button("解析実行", key="do_ai"):
        try:
            res = analyze_multiple_images(up_files)
            st.session_state.portfolio = res
            save_json(DB_FILE, res)
            st.rerun()
        except Exception as e: st.error(f"Error: {e}")

# --- 5. メイン画面 ---
st.title("🚀 Strategist Dashboard")

# イベントエリア
if st.session_state.events:
    st.write("📌 **追加イベント**")
    ev_cols = st.columns(len(st.session_state.events))
    for i, ev in enumerate(st.session_state.events):
        try:
            diff = (datetime.strptime(ev['date'], "%Y-%m-%d") - datetime.now()).days
            ev_cols[i].metric(ev['name'], f"{diff}日")
        except: pass

st.divider()
st.header("📉 Portfolio Monitor")

if st.button('最新価格に更新', key="refresh"): st.rerun()

# データ取得
prices_dict = get_live_prices(st.session_state.portfolio.keys())
rate = prices_dict.get("USDJPY", 159.2)
rows = []
total_jpy = 0
total_usd = 0

for key, info in st.session_state.portfolio.items():
    p_data = prices_dict.get(key)
    if p_data and info.get('shares', 0) > 0:
        cur = p_data["current"]
        
        # 損益計算
        if "_SHORT" in key: p_jpy = (info['cost'] - cur) * info['shares']
        elif "_MARGIN_LONG" in key: p_jpy = (cur - info['cost']) * info['shares']
        else:
            if info.get('currency') == "USD":
                p_usd = (cur - info['cost']) * info['shares']
                p_jpy = p_usd * rate
                total_usd += p_usd
            else: p_jpy = (cur - info['cost']) * info['shares']
        
        total_jpy += p_jpy
        cur_unit = "$" if info.get('currency') == "USD" else "¥"
        
        # 前日比表示部分を削除
        rows.append({
            "銘柄": f"{key.split('_')[0]} {info.get('name','')}",
            "数量": info['shares'],
            "区分": "信用" if any(x in key for x in ["MARGIN", "SHORT"]) else "現物",
            "取得単価": f"{info['cost']:,}",
            "現在値": f"{cur_unit}{cur:,.2f}",
            "損益(円)": f"¥{p_jpy:,.0f}"
        })

# メトリクス
c1, c2 = st.columns(2)
c1.metric("総損益 (JPY)", f"¥{total_jpy:,.0f}", delta=f"USD/JPY: {rate:.2f}")
c2.metric("米国株損益 (USD)", f"${total_usd:,.2f}")

if rows: st.table(pd.DataFrame(rows))
else: st.info("データがありません。")

st.divider()
st.subheader("📋 Reminder")
st.info(st.session_state.reminder_text)
