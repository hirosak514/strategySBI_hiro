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

# --- 3. 重要日程 ---
DATE_ANNOUNCEMENT = datetime(2026, 5, 12)
DATE_EXIT = datetime(2026, 5, 29)

# --- 4. 解析・価格取得関数 ---
def analyze_multiple_images(uploaded_files):
    if not current_api_key:
        raise ValueError("APIキーが設定されていません。")
    
    available_models = []
    try:
        for m in genai.list_models():
            if 'generateContent' in m.supported_generation_methods:
                available_models.append(m.name)
    except Exception as e:
        raise ValueError(f"モデルリスト取得エラー: {e}")

    target_model = next((m for m in available_models if "flash" in m), available_models[0])
    model = genai.GenerativeModel(target_model)
    
    prompt = """
    証券口座の画像から、保有しているすべての銘柄を抽出してください。
    【集計ルール】
    1. 銘柄名と種別（現物、信用買、信用売）が同じものは、数量を合計し、取得単価を平均（加重平均）してください。
    2. キーの付け方：
       - 現物：銘柄コード（例: 7013）
       - 信用買：コード + "_MARGIN_LONG"（例: 7013_MARGIN_LONG）
       - 信用売：コード + "_SHORT"（例: 7013_SHORT）
    3. 日本株は currency: "JPY"、米国株は currency: "USD" としてください。
    
    必ず以下のJSON形式のみで回答してください：
    {"キー": {"name": "銘柄名", "shares": 数量, "cost": 取得単価, "currency": "JPY" or "USD"}}
    """
    
    images = [Image.open(f) for f in uploaded_files]
    response = model.generate_content([prompt] + images)
    json_match = re.search(r'\{.*\}', response.text, re.DOTALL)
    if not json_match:
        raise ValueError("AI解析に失敗しました。")
    return json.loads(json_match.group())

def get_live_prices(portfolio_keys):
    prices = {}
    for key in portfolio_keys:
        symbol = key.replace("_MARGIN_LONG", "").replace("_SHORT", "")
        ticker_symbol = f"{symbol}.T" if symbol.isdigit() and len(symbol) == 4 else ( "7013.T" if symbol == "IHI" else symbol )
        try:
            stock = yf.Ticker(ticker_symbol)
            hist = stock.history(period="1d")
            prices[key] = hist['Close'].iloc[-1] if not hist.empty else None
        except:
            prices[key] = None
            
    try:
        prices["USDJPY"] = yf.Ticker("JPY=X").history(period="1d")['Close'].iloc[-1]
    except:
        prices["USDJPY"] = 159.2
    return prices

# --- 5. UI構築 ---
st.set_page_config(page_title="MSCI Exit Strategy Dashboard", layout="wide")

# サイドバー設定
st.sidebar.header("🔑 System Settings")
input_key = st.sidebar.text_input("Gemini API Key", value=st.session_state.api_key, type="password")
col_api1, col_api2 = st.sidebar.columns(2)
if col_api1.button("APIキーを保存", use_container_width=True):
    st.session_state.api_key = input_key
    save_json(CONFIG_FILE, {"gemini_key": input_key})
    st.sidebar.success("Key saved!")
    st.rerun()

if col_api2.button("APIキーとは", use_container_width=True):
    st.session_state.show_help = not st.session_state.show_help
    st.rerun()

if st.session_state.show_help:
    st.sidebar.info("""
    **APIキーとは？（初心者向け案内）**
    
    このツールが「証券会社の画像を読み取る」ために必要な、**GoogleのAI（Gemini）を利用するための「鍵」**です。
    
    **取得方法（完全無料）**
    1.  以下のリンクをクリックして、Google AI Studioのページを開きます。
        * 👉 **[APIキーを取得する (Google AI Studio)](https://aistudio.google.com/app/apikey)**
    2.  ページ内にある **'Create API key'** をクリックします。
    3.  生成されたコードをコピーして、上の入力欄に貼り付けてください。
    """)

st.sidebar.divider()
st.sidebar.header("📸 Multi-Position Update")
uploaded_files = st.sidebar.file_uploader("スクショをアップロード", type=["png", "jpg", "jpeg"], accept_multiple_files=True)

if uploaded_files and st.sidebar.button("AIで全画像を解析・集計"):
    with st.sidebar.spinner("解析中..."):
        try:
            new_data = analyze_multiple_images(uploaded_files)
            st.session_state.portfolio = new_data
            save_json(DB_FILE, st.session_state.portfolio)
            st.rerun()
        except Exception as e: st.sidebar.error(f"解析エラー: {e}")

# イベント・リマインダー管理
st.sidebar.divider()
st.sidebar.header("📅 Event Manager")
new_event_name = st.sidebar.text_input("イベント名を入力")
new_event_date = st.sidebar.date_input("日付を選択", value=datetime.now())
if st.sidebar.button("登録"):
    if new_event_name:
        st.session_state.events.append({"id": len(st.session_state.events)+1, "name": new_event_name, "date": new_event_date.strftime("%Y-%m-%d")})
        save_json(EVENT_FILE, st.session_state.events)
        st.rerun()
if st.session_state.events:
    del_id = st.sidebar.number_input("削除No", min_value=1, step=1)
    if st.sidebar.button("削除"):
        st.session_state.events = [e for e in st.session_state.events if e['id'] != del_id]
        for i, e in enumerate(st.session_state.events): e['id'] = i + 1
        save_json(EVENT_FILE, st.session_state.events)
        st.rerun()

st.sidebar.divider()
st.sidebar.header("📝 Reminder Editor")
col_ir1, col_ir2 = st.sidebar.columns(2)
if col_ir1.button("IR編集"): st.session_state.edit_mode = True; st.rerun()
if col_ir2.button("登録", key="save_ir"):
    save_json(REMINDER_FILE, st.session_state.reminder_text)
    st.session_state.edit_mode = False; st.rerun()
if st.session_state.edit_mode:
    st.session_state.reminder_text = st.sidebar.text_area("内容を編集", value=st.session_state.reminder_text, height=200)

# --- メイン表示 ---
st.title("🚀 Strategist Dashboard: AI Scanner")
col_f1, col_f2 = st.columns(2)
with col_f1: st.metric("MSCI発表まで", f"{(DATE_ANNOUNCEMENT - datetime.now()).days} 日")
with col_f2: st.metric("出口戦略まで", f"{(DATE_EXIT - datetime.now()).days} 日")

# 【修正箇所】年月日を表示に追加
if st.session_state.events:
    st.write("📌 **追加イベント**")
    cols = st.columns(len(st.session_state.events))
    for i, event in enumerate(st.session_state.events):
        e_date = datetime.strptime(event['date'], "%Y-%m-%d")
        display_date = e_date.strftime("%Y/%m/%d") # 年月日フォーマット
        with cols[i]: st.metric(f"No.{event['id']}: {display_date} {event['name']}", f"{(e_date - datetime.now()).days} 日")

st.divider()
st.header("📉 Real-time Portfolio Monitor")

current_prices = get_live_prices(st.session_state.portfolio.keys())
rate = current_prices.get("USDJPY", 159.2)
rows = []
total_profit_jpy = 0
total_profit_usd_only_us_stocks = 0

for key, info in st.session_state.portfolio.items():
    cur = current_prices.get(key)
    if cur and info['shares'] > 0:
        raw_code = key.split('_')[0]
        if raw_code.isdigit() and len(raw_code) == 4:
            display_name = f"{raw_code} {info.get('name', '')}"
        else:
            display_name = f"{raw_code} {info.get('name', '')}"
        
        if "_SHORT" in key:
            label = "信用(売建)"
            p_jpy = (info['cost'] - cur) * info['shares']
        elif "_MARGIN_LONG" in key:
            label = "信用(買建)"
            p_jpy = (cur - info['cost']) * info['shares']
        else:
            label = "現物"
            if info.get('currency') == "USD":
                p_usd = (cur - info['cost']) * info['shares']
                p_jpy = p_usd * rate
                total_profit_usd_only_us_stocks += p_usd
            else:
                p_jpy = (cur - info['cost']) * info['shares']

        total_profit_jpy += p_jpy
        cost_display = f"${info['cost']:,}" if info.get('currency') == "USD" else f"¥{info['cost']:,}"
        cur_display = f"${cur:,.2f}" if info.get('currency') == "USD" else f"¥{cur:,.0f}"
        
        rows.append({"銘柄": display_name, "数量": info['shares'], "区分": label, "取得単価": cost_display, "現在値": cur_display, "損益(円)": f"¥{p_jpy:,.0f}"})

m_col1, m_col2, m_col3 = st.columns([3, 2, 5])
with m_col1: st.metric("総計損益 (JPY)", f"¥{total_profit_jpy:,.0f}", delta=f"USD/JPY: {rate:.2f}")
with m_col2: st.metric("米国株損益 (USD)", f"${total_profit_usd_only_us_stocks:,.2f}")
with m_col3: 
    st.write("##")
    if st.button('更新'): st.rerun()

if rows: st.table(pd.DataFrame(rows))
else: st.info("画像（SBI証券の保有残高など）をアップロードしてください。")

st.divider()
st.subheader("📋 1% Investor's Reminder")
st.info(st.session_state.reminder_text)
