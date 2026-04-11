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
# ローカル実行時はjson、クラウド実行時はSessionStateを優先するハイブリッド仕様
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
# Secrets(配布用)または保存済みKey(ローカル用)を使用
current_api_key = st.session_state.api_key
if not current_api_key:
    try: current_api_key = st.secrets.get("GEMINI_API_KEY", "")
    except: pass

if current_api_key:
    genai.configure(api_key=current_api_key)

# --- 3. 重要日程 ---
DATE_ANNOUNCEMENT = datetime(2026, 5, 12)
DATE_EXIT = datetime(2026, 5, 29)

# --- 4. 解析・価格取得関数 (完全踏襲ロジック) ---
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
    【抽出ルール】
    1. 日本株(ETF含む)の場合：codeは4桁コード、nameは銘柄名。
    2. 米国株の場合：codeはティッカーシンボル、nameは企業名。
    3. 信用取引の「売建」の場合は、codeの末尾に "_SHORT" を付与してください。
    4. 日本円決済なら currency: "JPY"、米ドル決済なら currency: "USD" としてください。
    
    必ず以下のJSON形式のみで回答してください：
    {"コード": {"name": "名前", "shares": 数量, "cost": 取得単価, "currency": "JPY" or "USD"}}
    """
    
    images = [Image.open(f) for f in uploaded_files]
    response = model.generate_content([prompt] + images)
    json_match = re.search(r'\{.*\}', response.text, re.DOTALL)
    if not json_match:
        raise ValueError("AIが画像を正しく解析できませんでした。")
    return json.loads(json_match.group())

def get_live_prices(portfolio_keys):
    prices = {}
    for key in portfolio_keys:
        symbol = key.split('_')[0]
        if symbol.isdigit() and len(symbol) == 4:
            ticker_symbol = f"{symbol}.T"
        elif symbol == "IHI":
            ticker_symbol = "7013.T"
        else:
            ticker_symbol = symbol

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

# サイドバー: System Settings (完全踏襲)
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
    **Gemini APIキーの取得方法**
    1. [Google AI Studio](https://aistudio.google.com/app/apikey) にアクセス。
    2. 'Create API key' をクリック。
    3. 生成されたキーをコピーして貼り付けてください。
    """)

st.sidebar.divider()
st.sidebar.header("📸 Multi-Position Update")
uploaded_files = st.sidebar.file_uploader("スクショをドラッグ＆ドロップ", type=["png", "jpg", "jpeg"], accept_multiple_files=True)

if uploaded_files and st.sidebar.button("AIで全画像を解析・集計"):
    with st.sidebar.spinner("解析中..."):
        try:
            aggregated_data = analyze_multiple_images(uploaded_files)
            for key, vals in aggregated_data.items():
                st.session_state.portfolio[key] = vals
            save_json(DB_FILE, st.session_state.portfolio)
            st.rerun()
        except Exception as e: st.sidebar.error(f"解析エラー: {e}")

# サイドバー: Event Manager (完全踏襲)
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
    del_id = st.sidebar.number_input("削除するイベントNo", min_value=1, step=1)
    if st.sidebar.button("削除"):
        st.session_state.events = [e for e in st.session_state.events if e['id'] != del_id]
        for i, e in enumerate(st.session_state.events): e['id'] = i + 1
        save_json(EVENT_FILE, st.session_state.events)
        st.rerun()

# サイドバー: Reminder Editor (完全踏襲)
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

# カウントダウン表示
col_f1, col_f2 = st.columns(2)
with col_f1: st.metric("MSCI発表まで", f"{(DATE_ANNOUNCEMENT - datetime.now()).days} 日")
with col_f2: st.metric("出口戦略まで", f"{(DATE_EXIT - datetime.now()).days} 日")

# 登録済みイベントの表示 (復旧完了)
if st.session_state.events:
    st.write("📌 **追加イベント**")
    cols = st.columns(len(st.session_state.events))
    for i, event in enumerate(st.session_state.events):
        e_date = datetime.strptime(event['date'], "%Y-%m-%d")
        with cols[i]: st.metric(f"No.{event['id']}: {event['name']}", f"{(e_date - datetime.now()).days} 日")

st.divider()
st.header("📉 Real-time Portfolio Monitor")

# ポートフォリオ計算
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

# 損益メトリクス表示
m_col1, m_col2, m_col3 = st.columns([3, 2, 5])
with m_col1: st.metric("総計損益 (JPY)", f"¥{total_profit_jpy:,.0f}", delta=f"USD/JPY: {rate:.2f}")
with m_col2: st.metric("米国株損益 (USD)", f"${total_profit_usd_only_us_stocks:,.2f}")
with m_col3: 
    st.write("##")
    if st.button('更新'): st.rerun()

# ポートフォリオテーブル
if rows: 
    st.table(pd.DataFrame(rows))
    # 配布用：必要に応じてJSONでダウンロード可能
    st.download_button("JSONで保存", data=json.dumps(st.session_state.portfolio, ensure_ascii=False), file_name="portfolio_backup.json")
else:
    st.info("サイドバーからスクショをアップロードしてください。")

st.divider()
st.subheader("📋 1% Investor's Reminder")
st.info(st.session_state.reminder_text)
