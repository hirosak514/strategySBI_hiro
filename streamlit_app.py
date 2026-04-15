import streamlit as st
impoimport streamlit as st
import yfinance as yf
import pandas as pd
from datetime import datetime
import google.generativeai as genai
from PIL import Image
import json
import re
import io

# --- 1. セッション状態の初期化 ---
# 外部ファイルに依存せず、まずメモリ上（Session State）で管理します
if 'portfolio' not in st.session_state:
    st.session_state.portfolio = {}
if 'events' not in st.session_state:
    st.session_state.events = []
if 'reminder_text' not in st.session_state:
    st.session_state.reminder_text = "- ターゲット日程を入力してください"
if 'api_key' not in st.session_state:
    st.session_state.api_key = ""
if 'edit_mode' not in st.session_state:
    st.session_state.edit_mode = False
if 'show_help' not in st.session_state:
    st.session_state.show_help = False

# --- 2. データのエクスポート・インポート機能 (配布用) ---
def export_data():
    data = {
        "portfolio": st.session_state.portfolio,
        "events": st.session_state.events,
        "reminder_text": st.session_state.reminder_text,
        "api_key": st.session_state.api_key
    }
    return json.dumps(data, ensure_ascii=False, indent=4)

def import_data(uploaded_json):
    if uploaded_json is not None:
        data = json.load(uploaded_json)
        st.session_state.portfolio = data.get("portfolio", {})
        st.session_state.events = data.get("events", [])
        st.session_state.reminder_text = data.get("reminder_text", "")
        st.session_state.api_key = data.get("api_key", "")
        st.rerun()

# --- 3. API設定 ---
if st.session_state.api_key:
    genai.configure(api_key=st.session_state.api_key)

# --- 4. 解析・価格取得関数 (完全踏襲) ---
def analyze_multiple_images(uploaded_files):
    if not st.session_state.api_key:
        raise ValueError("APIキーが設定されていません。")
    model = genai.GenerativeModel("gemini-1.5-flash")
    prompt = """
    証券口座の画像から、保有しているすべての銘柄を抽出してJSONで回答してください。
    日本株はコードと銘柄名を併記してください（例: 7013 IHI）。
    {"キー": {"name": "銘柄名", "shares": 数量, "cost": 取得単価, "currency": "JPY" or "USD"}}
    """
    images = [Image.open(f) for f in uploaded_files]
    response = model.generate_content([prompt] + images)
    json_match = re.search(r'\{.*\}', response.text, re.DOTALL)
    return json.loads(json_match.group())

def get_live_prices(portfolio_keys):
    prices = {}
    for key in portfolio_keys:
        symbol = key.replace("_MARGIN_LONG", "").replace("_SHORT", "")
        ticker_symbol = f"{symbol}.T" if symbol.isdigit() and len(symbol) == 4 else symbol
        try:
            stock = yf.Ticker(ticker_symbol)
            hist = stock.history(period="1d")
            prices[key] = hist['Close'].iloc[-1] if not hist.empty else None
        except: prices[key] = None
    try: prices["USDJPY"] = yf.Ticker("JPY=X").history(period="1d")['Close'].iloc[-1]
    except: prices["USDJPY"] = 159.2
    return prices

# --- 5. UI構築 ---
st.set_page_config(page_title="Strategist Dashboard", layout="wide")

# サイドバー：設定とデータ管理
st.sidebar.header("⚙️ System & Data")

# APIキー設定
input_key = st.sidebar.text_input("Gemini API Key", value=st.session_state.api_key, type="password")
if st.sidebar.button("APIキーを適用"):
    st.session_state.api_key = input_key
    st.rerun()

if st.sidebar.button("APIキーとは"):
    st.session_state.show_help = not st.session_state.show_help
if st.session_state.show_help:
    st.sidebar.info("AI studioから無料で取得できる「鍵」です。 [取得リンク](https://aistudio.google.com/app/apikey)")

st.sidebar.divider()

# ★配布用：データの保存と読込
st.sidebar.subheader("💾 データの保存・復元")
st.sidebar.download_button(
    label="現在の設定をファイルに保存",
    data=export_data(),
    file_name="my_strategy_data.json",
    mime="application/json",
    use_container_width=True
)

uploaded_json = st.sidebar.file_uploader("保存したファイルを読み込む", type="json")
if uploaded_json:
    if st.sidebar.button("データを復元する", use_container_width=True):
        import_data(uploaded_json)

st.sidebar.divider()

# 📸 画像解析
st.sidebar.header("📸 Position Update")
uploaded_files = st.sidebar.file_uploader("スクショをアップロード", type=["png", "jpg", "jpeg"], accept_multiple_files=True)
if uploaded_files and st.sidebar.button("AIで解析・更新"):
    with st.sidebar.spinner("解析中..."):
        st.session_state.portfolio = analyze_multiple_images(uploaded_files)
        st.rerun()

# 📅 イベント管理
st.sidebar.header("📅 Event Manager")
new_event_name = st.sidebar.text_input("イベント名")
new_event_date = st.sidebar.date_input("日付", value=datetime.now())
if st.sidebar.button("イベント登録"):
    st.session_state.events.append({"id": len(st.session_state.events)+1, "name": new_event_name, "date": new_event_date.strftime("%Y-%m-%d")})
    st.rerun()

# --- メイン画面 ---
st.title("🚀 Strategist Dashboard")

# イベント表示
if st.session_state.events:
    cols = st.columns(len(st.session_state.events))
    for i, event in enumerate(st.session_state.events):
        e_date = datetime.strptime(event['date'], "%Y-%m-%d")
        with cols[i]: st.metric(f"{e_date.strftime('%Y/%m/%d')} {event['name']}", f"{(e_date - datetime.now()).days} 日")

st.divider()

# ポートフォリオ表示
st.header("📉 Portfolio Monitor")
current_prices = get_live_prices(st.session_state.portfolio.keys())
rate = current_prices.get("USDJPY", 159.2)
rows = []
total_jpy = 0

for key, info in st.session_state.portfolio.items():
    cur = current_prices.get(key)
    if cur:
        raw_code = key.split('_')[0]
        # 【機能踏襲】コードと銘柄名の併記
        name = info.get('name', '')
        display_name = f"{raw_code} {name}" if name else raw_code
        
        # 損益計算（踏襲）
        if "_SHORT" in key: p_jpy = (info['cost'] - cur) * info['shares']
        elif "_MARGIN_LONG" in key: p_jpy = (cur - info['cost']) * info['shares']
        else:
            if info.get('currency') == "USD": p_jpy = (cur - info['cost']) * info['shares'] * rate
            else: p_jpy = (cur - info['cost']) * info['shares']
        
        total_jpy += p_jpy
        rows.append({
            "銘柄": display_name, 
            "数量": info['shares'], 
            "現在値": f"¥{cur:,.0f}" if info.get('currency') != "USD" else f"${cur:,.2f}",
            "損益(円)": f"¥{p_jpy:,.0f}"
        })

if rows:
    st.metric("総計損益", f"¥{total_jpy:,.0f}")
    st.table(pd.DataFrame(rows))
    if st.button("更新"): st.rerun()

st.divider()
st.subheader("📋 Reminder")
st.info(st.session_state.reminder_text)
