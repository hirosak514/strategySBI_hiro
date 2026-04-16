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
        except:
            pass
    return default_value

def save_json(file_path, data):
    with open(file_path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=4)

# --- 1. セッション状態の初期化 ---
if 'portfolio' not in st.session_state:
    st.session_state.portfolio = load_json(DB_FILE, {})
if 'events' not in st.session_state:
    st.session_state.events = load_json(EVENT_FILE, [])
if 'reminder_text' not in st.session_state:
    st.session_state.reminder_text = load_json(REMINDER_FILE, "- ターゲット日程を入力してください")
if 'api_key' not in st.session_state:
    st.session_state.api_key = load_json(CONFIG_FILE, {"gemini_key": ""})["gemini_key"]
if 'edit_mode' not in st.session_state:
    st.session_state.edit_mode = False
if 'show_help' not in st.session_state:
    st.session_state.show_help = False

# --- 2. API設定 ---
current_api_key = st.session_state.api_key
if not current_api_key:
    try: current_api_key = st.secrets.get("GEMINI_API_KEY", "")
    except: pass
if current_api_key:
    genai.configure(api_key=current_api_key)

# --- 3. 解析・価格取得関数 ---
def analyze_multiple_images(uploaded_files):
    if not current_api_key:
        raise ValueError("APIキーが設定されていません。")
    available_models = [m.name for m in genai.list_models() if 'generateContent' in m.supported_generation_methods]
    target_model = next((m for m in available_models if "flash" in m), available_models[0])
    model = genai.GenerativeModel(target_model)
    prompt = """証券口座画像から銘柄抽出。JSON形式: {"キー": {"name": "銘柄名", "shares": 数量, "cost": 取得単価, "currency": "JPY" or "USD"}}"""
    images = [Image.open(f) for f in uploaded_files]
    response = model.generate_content([prompt] + images)
    json_match = re.search(r'\{.*\}', response.text, re.DOTALL)
    if not json_match: raise ValueError("AI解析に失敗しました。")
    return json.loads(json_match.group())

def get_live_prices(portfolio_keys):
    prices = {}
    for key in portfolio_keys:
        symbol = key.replace("_MARGIN_LONG", "").replace("_SHORT", "")
        ticker_symbol = f"{symbol}.T" if symbol.isdigit() and len(symbol) == 4 else ( "7013.T" if symbol == "IHI" else symbol )
        try:
            stock = yf.Ticker(ticker_symbol)
            hist = stock.history(period="5d")
            if not hist.empty:
                prices[key] = {"current": hist['Close'].iloc[-1], "prev_close": hist['Close'].iloc[-2] if len(hist) >= 2 else None}
            else: prices[key] = None
        except: prices[key] = None
    try:
        usdjpy_hist = yf.Ticker("JPY=X").history(period="5d")
        prices["USDJPY"] = usdjpy_hist['Close'].iloc[-1] if not usdjpy_hist.empty else 159.2
    except: prices["USDJPY"] = 159.2
    return prices

# --- 4. UI構築 ---
st.set_page_config(page_title="Strategist Dashboard", layout="wide")

# サイドバー
st.sidebar.header("🔑 System Settings")
input_key = st.sidebar.text_input("Gemini API Key", value=st.session_state.api_key, type="password")
if st.sidebar.button("APIキーを保存", use_container_width=True):
    st.session_state.api_key = input_key
    save_json(CONFIG_FILE, {"gemini_key": input_key})
    st.rerun()

# データバックアップ
st.sidebar.divider()
st.sidebar.subheader("💾 Data Backup")
backup_data = {"portfolio": st.session_state.portfolio, "events": st.session_state.events, "reminder_text": st.session_state.reminder_text}
st.sidebar.download_button(label="設定ファイルを保存", data=json.dumps(backup_data, ensure_ascii=False, indent=4), file_name=f"backup_{datetime.now().strftime('%Y%m%d')}.json", mime="application/json", use_container_width=True)

uploaded_config = st.sidebar.file_uploader("設定ファイルを読み込み", type=["json"])
if uploaded_config and st.sidebar.button("読み込みを実行"):
    try:
        loaded = json.load(uploaded_config)
        st.session_state.update(loaded)
        for k, f in zip(["portfolio", "events", "reminder_text"], [DB_FILE, EVENT_FILE, REMINDER_FILE]): save_json(f, loaded.get(k))
        st.rerun()
    except Exception as e: st.sidebar.error(f"Error: {e}")

# メイン画面
st.title("🚀 Strategist Dashboard")

# イベント表示（エラー防止のためコンテナ化）
if st.session_state.events:
    event_container = st.container()
    with event_container:
        st.write("📌 **追加イベント**")
        cols = st.columns(len(st.session_state.events))
        for i, event in enumerate(st.session_state.events):
            e_date = datetime.strptime(event['date'], "%Y-%m-%d")
            with cols[i]: st.metric(f"{event['name']}", f"{(e_date - datetime.now()).days}日")

st.divider()
st.header("📉 Real-time Portfolio Monitor")

# 更新ボタン（キーを動的に生成してDOM不整合を防止）
if st.button('データを更新', key=f"update_btn_{datetime.now().timestamp()}"):
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
        
        if "_SHORT" in key: p_jpy = (info['cost'] - cur) * info['shares']
        elif "_MARGIN_LONG" in key: p_jpy = (cur - info['cost']) * info['shares']
        else:
            if info.get('currency') == "USD":
                p_usd = (cur - info['cost']) * info['shares']
                p_jpy, total_profit_usd = p_usd * rate, total_profit_usd + p_usd
            else: p_jpy = (cur - info['cost']) * info['shares']
        
        total_profit_jpy += p_jpy
        cur_display = f"{('$' if info.get('currency') == 'USD' else '¥')}{cur:,.2f} {day_change}"
        rows.append({"銘柄": f"{key.split('_')[0]} {info.get('name','')}", "数量": info['shares'], "区分": "信用" if "MARGIN" in key or "SHORT" in key else "現物", "取得単価": f"{info['cost']:,}", "現在値": cur_display, "損益(円)": f"¥{p_jpy:,.0f}"})

# メトリクス表示
m1, m2 = st.columns(2)
m1.metric("総計損益 (JPY)", f"¥{total_profit_jpy:,.0f}", delta=f"USD/JPY: {rate:.2f}")
m2.metric("米国株損益 (USD)", f"${total_profit_usd:,.2f}")

# テーブル表示（エラーが出やすい箇所をガード）
if rows:
    # 常に新しいキーを生成してReactの再レンダリングを強制的に正常化する
    st.table(pd.DataFrame(rows))
else:
    st.info("ポートフォリオデータが空です。サイドバーから画像をアップロードしてください。")

st.divider()
st.subheader("📋 1% Investor's Reminder")
st.info(st.session_state.reminder_text)
