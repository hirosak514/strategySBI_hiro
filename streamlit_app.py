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
if 'backup_portfolio' not in st.session_state:
    st.session_state.backup_portfolio = None
if 'events' not in st.session_state:
    st.session_state.events = load_json(EVENT_FILE, [])
if 'reminder_text' not in st.session_state:
    st.session_state.reminder_text = load_json(REMINDER_FILE, "- ターゲット日程を入力してください")
if 'api_key' not in st.session_state:
    st.session_state.api_key = load_json(CONFIG_FILE, {"gemini_key": ""}).get("gemini_key", "")

def create_backup():
    st.session_state.backup_portfolio = copy.deepcopy(st.session_state.portfolio)

# --- 2. API設定 ---
current_api_key = st.session_state.api_key or st.secrets.get("GEMINI_API_KEY", "")
if current_api_key:
    genai.configure(api_key=current_api_key)

# --- 3. 解析・価格取得関数 ---
def get_live_prices(portfolio_keys):
    prices = {}
    for key in portfolio_keys:
        symbol = key.split('_')[0]
        is_japan = symbol.isdigit() and len(symbol) == 4
        ticker = f"{symbol}.T" if is_japan else ("7013.T" if symbol == "IHI" else symbol)
        try:
            stock = yf.Ticker(ticker)
            hist = stock.history(period="5d")
            if not hist.empty:
                prices[key] = {
                    "current": hist['Close'].iloc[-1],
                    "prev_close": hist['Close'].iloc[-2] if len(hist) >= 2 else None
                }
            else:
                prices[key] = None
        except:
            prices[key] = None
    try:
        usdjpy = yf.Ticker("JPY=X").history(period="5d")
        prices["USDJPY"] = usdjpy['Close'].iloc[-1] if not usdjpy.empty else 159.2
    except:
        prices["USDJPY"] = 159.2
    return prices

def analyze_multiple_images(uploaded_files):
    if not current_api_key:
        raise ValueError("APIキーが設定されていません。")
    available_models = [m.name for m in genai.list_models() if "generateContent" in m.supported_generation_methods]
    target_model = next((m for m in available_models if "flash" in m), available_models[0])
    model = genai.GenerativeModel(target_model)
    prompt = "証券口座のスクショから銘柄情報をJSONで抽出してください。..." # プロンプト詳細は以前と同様
    images = [Image.open(f) for f in uploaded_files]
    response = model.generate_content([prompt] + images)
    json_match = re.search(r'\{.*\}', response.text, re.DOTALL)
    return json.loads(json_match.group()) if json_match else {}

# --- 4. UI ---
st.set_page_config(page_title="Strategist Dashboard", layout="wide")

st.markdown("""
<style>
    /* スケジュール表示用 */
    .event-card { background-color: rgba(255, 255, 255, 0.05); border-radius: 5px; padding: 10px; text-align: center; }
    .event-date { font-size: 0.8rem; color: #ccc; }
    .event-days { font-size: 1rem; color: #ffffff; font-weight: bold; }
    
    /* 削除ボタン赤色化：カラムの3番目のボタンに適用 */
    div[data-testid="column"]:nth-child(3) button {
        background-color: #ff4b4b !important;
        color: white !important;
        border: none;
    }
</style>
""", unsafe_allow_html=True)

with st.sidebar:
    st.header("🔑 Settings")
    new_api_key = st.text_input("Gemini API Key", value=st.session_state.api_key, type="password")
    if st.button("APIキーを保存"):
        st.session_state.api_key = new_api_key
        save_json(CONFIG_FILE, {"gemini_key": new_api_key})
        st.success("APIキーを保存しました")
        st.rerun()

    st.divider()

    # --- ✏️ 銘柄情報の直接入力 (ボタン常時表示版) ---
    st.header("✏️ 銘柄情報の直接入力")
    portfolio_items = list(st.session_state.portfolio.keys())
    
    selected_no = None
    if portfolio_items:
        no_options = [i + 1 for i in range(len(portfolio_items))]
        selected_no = st.selectbox("銘柄No.を選択", options=no_options)
        target_key = portfolio_items[selected_no - 1]
        target_info = st.session_state.portfolio[target_key]
        
        new_shares = st.number_input(f"数量 ({target_key})", value=float(target_info.get('shares', 0)))
        new_cost = st.number_input(f"取得単価 ({target_key})", value=float(target_info.get('cost', 0)))
    else:
        st.info("編集する銘柄がありません")
        new_shares, new_cost = 0, 0

    col_mod, col_rev, col_del = st.columns(3)
    
    # ボタン自体は常に配置
    mod_btn = col_mod.button("修正")
    rev_btn = col_rev.button("復元", type="primary")
    del_btn = col_del.button("削除")

    if selected_no:
        if mod_btn:
            create_backup()
            if new_shares == 0:
                st.session_state.portfolio[target_key].update({"shares": 0, "cost": 0})
            else:
                st.session_state.portfolio[target_key].update({"shares": new_shares, "cost": new_cost})
            save_json(DB_FILE, st.session_state.portfolio)
            st.rerun()
            
        if rev_btn:
            if st.session_state.backup_portfolio is not None:
                st.session_state.portfolio = copy.deepcopy(st.session_state.backup_portfolio)
                st.session_state.backup_portfolio = None
                save_json(DB_FILE, st.session_state.portfolio)
                st.success("復元しました")
                st.rerun()
            else:
                st.error("履歴なし")

        if del_btn:
            create_backup()
            del st.session_state.portfolio[target_key]
            save_json(DB_FILE, st.session_state.portfolio)
            st.rerun()

    st.divider()
    
    # --- 📌 Event Manager ---
    st.header("📌 Event Manager")
    with st.expander("イベントの追加/削除"):
        ev_name = st.text_input("イベント名")
        ev_date = st.date_input("日付")
        if st.button("イベント追加"):
            st.session_state.events.append({"name": ev_name, "date": ev_date.strftime("%Y-%m-%d")})
            save_json(EVENT_FILE, st.session_state.events)
            st.rerun()
        
        if st.session_state.events:
            idx = st.selectbox("削除するイベント", range(len(st.session_state.events)), format_func=lambda x: st.session_state.events[x]['name'])
            if st.button("選択したイベントを削除"):
                st.session_state.events.pop(idx)
                save_json(EVENT_FILE, st.session_state.events)
                st.rerun()

    st.divider()

    # --- 📋 Reminder Edit ---
    st.header("📋 Reminder Edit")
    new_reminder = st.text_area("リマインダー内容", value=st.session_state.reminder_text)
    if st.button("リマインダー更新"):
        st.session_state.reminder_text = new_reminder
        save_json(REMINDER_FILE, new_reminder)
        st.rerun()

    st.divider()

    # --- 💾 Backup (Export/Import) ---
    st.subheader("💾 Backup")
    full_config = {
        "portfolio": st.session_state.portfolio,
        "events": st.session_state.events,
        "reminder_text": st.session_state.reminder_text
    }
    st.download_button("設定をエクスポート(JSON)", json.dumps(full_config, ensure_ascii=False, indent=4), "my_config.json", "application/json")
    
    uploaded_config = st.file_uploader("設定をインポート(JSON)", type=["json"])
    if uploaded_config is not None and st.button("インポート実行"):
        try:
            config_data = json.load(uploaded_config)
            create_backup()
            st.session_state.portfolio = config_data.get("portfolio", {})
            st.session_state.events = config_data.get("events", [])
            st.session_state.reminder_text = config_data.get("reminder_text", "")
            save_json(DB_FILE, st.session_state.portfolio)
            save_json(EVENT_FILE, st.session_state.events)
            save_json(REMINDER_FILE, st.session_state.reminder_text)
            st.rerun()
        except: st.error("失敗")

    st.divider()

    # --- 📸 AI Scanner ---
    st.header("📸 AI Scanner")
    up_files = st.file_uploader("スクショ", type=["png", "jpg", "jpeg"], accept_multiple_files=True)
    if up_files and st.button("AI解析実行"):
        with st.spinner("解析中..."):
            try:
                create_backup()
                extracted_data = analyze_multiple_images(up_files)
                st.session_state.portfolio = extracted_data
                save_json(DB_FILE, st.session_state.portfolio)
                st.rerun()
            except Exception as e: st.error(e)

# --- 5. メイン画面 ---
st.title("🚀 Strategist Dashboard")

if st.session_state.events:
    st.write("📌 **重要スケジュール**")
    event_cols = st.columns(len(st.session_state.events))
    for i, event in enumerate(st.session_state.events):
        with event_cols[i]:
            try:
                target_date = datetime.strptime(event['date'], "%Y-%m-%d")
                days_left = (target_date - datetime.now()).days
                st.markdown(f"""
                    <div class="event-card">
                        <div style="font-weight:bold; font-size:0.9rem;">{event['name']}</div>
                        <div class="event-date">{event['date']}</div>
                        <div class="event-days">あと {days_left} 日</div>
                    </div>
                """, unsafe_allow_html=True)
            except: pass

st.divider()
st.header("📉 Portfolio Monitor")

# (以降、テーブル表示等は以前のロジックを完全踏襲)
prices_dict = get_live_prices(st.session_state.portfolio.keys())
rate = prices_dict.get("USDJPY", 159.2)

rows = []
total_jpy = 0
total_usd = 0

for i, (key, info) in enumerate(st.session_state.portfolio.items()):
    p_data = prices_dict.get(key)
    if p_data:
        cur = p_data["current"]
        prev = p_data["prev_close"]
        change_pct = f"({(cur - prev) / prev * 100:+.2f}%)" if prev else ""
        
        if info['shares'] > 0:
            if "_SHORT" in key: p_jpy = (info['cost'] - cur) * info['shares']
            elif "_MARGIN_LONG" in key: p_jpy = (cur - info['cost']) * info['shares']
            else:
                if info.get('currency') == "USD":
                    p_usd = (cur - info['cost']) * info['shares']
                    p_jpy = p_usd * rate
                    total_usd += p_usd
                else: p_jpy = (cur - info['cost']) * info['shares']
            total_jpy += p_jpy
        else: p_jpy = 0

        rows.append({
            "No.": i + 1,
            "銘柄": f"{key.split('_')[0]} {info.get('name','')}",
            "数量": info['shares'],
            "区分": "現物" if "_" not in key else key.split('_')[1],
            "取得単価": f"${info['cost']:,}" if info.get('currency') == "USD" else f"¥{info['cost']:,}",
            "現在値": f"{cur:,.2f} {change_pct}",
            "損益(円)": f"¥{p_jpy:,.0f}"
        })

col_m1, col_m2 = st.columns(2)
col_m1.metric("総合計損益", f"¥{total_jpy:,.0f}", f"USD/JPY: {rate:.2f}")
col_m2.metric("米国株損益", f"${total_usd:,.2f}")

if rows: st.table(pd.DataFrame(rows))
else: st.info("銘柄がありません")

st.divider()
st.subheader("📋 Reminder")
st.info(st.session_state.reminder_text)
