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
if 'reminder_text' not in st.session_state: st.session_state.reminder_text = load_json(REMINDER_FILE, "- 日程を入力してください")
if 'api_key' not in st.session_state: st.session_state.api_key = load_json(CONFIG_FILE, {"gemini_key": ""}).get("gemini_key", "")

# --- 2. API設定 ---
current_api_key = st.session_state.api_key or st.secrets.get("GEMINI_API_KEY", "")
if current_api_key: genai.configure(api_key=current_api_key)

# --- 3. 価格取得関数 ---
def get_live_prices(portfolio_keys):
    prices = {}
    for key in portfolio_keys:
        symbol = key.split('_')[0]
        ticker = f"{symbol}.T" if symbol.isdigit() and len(symbol) == 4 else ( "7013.T" if symbol == "IHI" else symbol )
        try:
            hist = yf.Ticker(ticker).history(period="1d")
            prices[key] = {"current": hist['Close'].iloc[-1]} if not hist.empty else None
        except: prices[key] = None
    try:
        usdjpy = yf.Ticker("JPY=X").history(period="1d")
        prices["USDJPY"] = usdjpy['Close'].iloc[-1] if not usdjpy.empty else 159.2
    except: prices["USDJPY"] = 159.2
    return prices

# --- 4. UI設定 ---
st.set_page_config(page_title="Strategist Dashboard", layout="wide")

# サイドバー処理
with st.sidebar:
    st.header("🔑 Settings")
    input_key = st.text_input("Gemini API Key", value=st.session_state.api_key, type="password")
    if st.button("保存", key="save_api"):
        st.session_state.api_key = input_key
        save_json(CONFIG_FILE, {"gemini_key": input_key})
        st.rerun()

    st.divider()
    
    # 銘柄情報の直接編集フォーム (Event Managerの上に挿入)
    st.header("✏️ 銘柄情報の直接入力")
    portfolio_items = list(st.session_state.portfolio.keys())
    
    if portfolio_items:
        # 1から始まるナンバーのリストを作成
        no_options = [i + 1 for i in range(len(portfolio_items))]
        selected_no = st.selectbox("銘柄No.を選択", options=no_options)
        
        # 選択されたNoに対応する現在のデータを取得
        target_key = portfolio_items[selected_no - 1]
        target_info = st.session_state.portfolio[target_key]
        
        new_shares = st.number_input(f"数量 ({target_key})", value=float(target_info.get('shares', 0)))
        new_cost = st.number_input(f"取得単価 ({target_key})", value=float(target_info.get('cost', 0)))
        
        if st.button("修正"):
            # データの書き換え
            st.session_state.portfolio[target_key]['shares'] = new_shares
            st.session_state.portfolio[target_key]['cost'] = new_cost
            save_json(DB_FILE, st.session_state.portfolio)
            st.success(f"No.{selected_no} ({target_key}) を更新しました")
            st.rerun()
    else:
        st.info("編集する銘柄がありません")

    st.divider()
    st.subheader("💾 Backup")
    backup_data = {"portfolio": st.session_state.get("portfolio", {}), "events": st.session_state.get("events", []), "reminder_text": st.session_state.get("reminder_text", "")}
    st.download_button("Export (JSON)", json.dumps(backup_data, ensure_ascii=False, indent=4), "backup.json", "application/json")

    up_config = st.file_uploader("Import (JSON)", type=["json"])
    if up_config and st.button("実行", key="do_import"):
        try:
            loaded = json.load(up_config)
            st.session_state.portfolio = loaded.get("portfolio", {})
            st.session_state.events = loaded.get("events", [])
            st.session_state.reminder_text = loaded.get("reminder_text", "- 日程を入力してください")
            save_json(DB_FILE, st.session_state.portfolio)
            save_json(EVENT_FILE, st.session_state.events)
            save_json(REMINDER_FILE, st.session_state.reminder_text)
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
st.header("📉 Portfolio")
if st.button('最新価格に更新', key="refresh"): st.rerun()

# データ取得
prices_dict = get_live_prices(st.session_state.portfolio.keys())
rate = prices_dict.get("USDJPY", 159.2)
rows = []
total_jpy = 0

# 銘柄リストをループしてテーブル行を作成
for i, (key, info) in enumerate(st.session_state.portfolio.items()):
    p_data = prices_dict.get(key)
    if p_data and info.get('shares', 0) > 0:
        cur = p_data["current"]
        
        # 損益計算
        if "_SHORT" in key: p_jpy = (info['cost'] - cur) * info['shares']
        elif "_MARGIN_LONG" in key: p_jpy = (cur - info['cost']) * info['shares']
        else:
            if info.get('currency') == "USD": p_jpy = (cur - info['cost']) * info['shares'] * rate
            else: p_jpy = (cur - info['cost']) * info['shares']
        
        total_jpy += p_jpy
        unit = "$" if info.get('currency') == "USD" else "¥"
        
        # 行データの追加 (No.を先頭に追加)
        rows.append({
            "No.": i + 1,
            "銘柄": f"{key.split('_')[0]} {info.get('name','')}",
            "数量": info['shares'],
            "区分": "信用" if "MARGIN" in key or "SHORT" in key else "現物",
            "現在値": f"{unit}{cur:,.2f}",
            "損益(円)": f"¥{p_jpy:,.0f}"
        })

# メトリクス表示
st.metric("総損益 (JPY)", f"¥{total_jpy:,.0f}", delta=f"USD/JPY: {rate:.2f}")

# テーブル表示
if rows:
    df_display = pd.DataFrame(rows)
    st.table(df_display)
else:
    st.info("データがありません。")

st.divider()
st.subheader("📋 Reminder")
st.info(st.session_state.reminder_text)
