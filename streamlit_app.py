import streamlit as st
import yfinance as yf
import pandas as pd
from datetime import datetime
import google.generativeai as genai
from PIL import Image
import json
import re
import os
import io

# --- 0. データの保存・読み込みロジック (ファイルベースからメモリ＋手動保存へ) ---
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
        try:
            data = json.load(uploaded_json)
            st.session_state.portfolio = data.get("portfolio", {})
            st.session_state.events = data.get("events", [])
            st.session_state.reminder_text = data.get("reminder_text", "- ターゲット日程を入力してください")
            st.session_state.api_key = data.get("api_key", "")
            return True
        except:
            return False
    return False

# --- 1. セッション状態の初期化 ---
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

# --- 2. API設定 ---
current_api_key = st.session_state.api_key
if current_api_key:
    genai.configure(api_key=current_api_key)

# --- 3. 解析・価格取得関数 (完全踏襲ロジック) ---
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

# --- 4. UI構築 ---
st.set_page_config(page_title="Strategist Dashboard", layout="wide")

# サイドバー設定
st.sidebar.header("🔑 System & Data Management")

# APIキー設定
input_key = st.sidebar.text_input("Gemini API Key", value=st.session_state.api_key, type="password")
col_api1, col_api2 = st.sidebar.columns(2)
if col_api1.button("APIキーを適用", use_container_width=True):
    st.session_state.api_key = input_key
    st.sidebar.success("Key applied!")
    st.rerun()

if col_api2.button("APIキーとは", use_container_width=True):
    st.session_state.show_help = not st.session_state.show_help
    st.rerun()

if st.session_state.show_help:
    st.sidebar.info("""
    **APIキーとは？**
    GoogleのAI（Gemini）を利用するための鍵です。
    **取得方法（無料）**
    1. 👉 [APIキー取得ページ](https://aistudio.google.com/app/apikey)
    2. 'Create API key' をクリックし、生成されたコードを貼り付けてください。
    """)

st.sidebar.divider()

# 配布用：データ保存・復元
st.sidebar.subheader("💾 バックアップ")
st.sidebar.download_button(
    label="現在の全データを保存",
    data=export_data(),
    file_name="strategy_dashboard_backup.json",
    mime="application/json",
    use_container_width=True
)

uploaded_json = st.sidebar.file_uploader("保存ファイルを読み込む", type="json")
if uploaded_json:
    if st.sidebar.button("データを復元する", use_container_width=True):
        if import_data(uploaded_json):
            st.sidebar.success("復元完了！")
            st.rerun()
        else:
            st.sidebar.error("形式が正しくありません")

st.sidebar.divider()

# 画像解析 (完全踏襲)
st.sidebar.header("📸 Multi-Position Update")
uploaded_files = st.sidebar.file_uploader("スクショをアップロード", type=["png", "jpg", "jpeg"], accept_multiple_files=True)

if uploaded_files and st.sidebar.button("AIで全画像を解析・集計"):
    with st.sidebar.spinner("解析中..."):
        try:
            new_data = analyze_multiple_images(uploaded_files)
            st.session_state.portfolio = new_data
            st.rerun()
        except Exception as e: st.sidebar.error(f"解析エラー: {e}")

# イベント・リマインダー管理 (完全踏襲)
st.sidebar.divider()
st.sidebar.header("📅 Event Manager")
new_event_name = st.sidebar.text_input("イベント名を入力")
new_event_date = st.sidebar.date_input("日付を選択", value=datetime.now())
if st.sidebar.button("登録"):
    if new_event_name:
        st.session_state.events.append({"id": len(st.session_state.events)+1, "name": new_event_name, "date": new_event_date.strftime("%Y-%m-%d")})
        st.rerun()
if st.session_state.events:
    del_id = st.sidebar.number_input("削除No", min_value=1, step=1)
    if st.sidebar.button("削除"):
        st.session_state.events = [e for e in st.session_state.events if e['id'] != del_id]
        for i, e in enumerate(st.session_state.events): e['id'] = i + 1
        st.rerun()

st.sidebar.divider()
st.sidebar.header("📝 Reminder Editor")
col_ir1, col_ir2 = st.sidebar.columns(2)
if col_ir1.button("IR編集"): st.session_state.edit_mode = True; st.rerun()
if col_ir2.button("登録", key="save_ir"):
    st.session_state.edit_mode = False; st.rerun()
if st.session_state.edit_mode:
    st.session_state.reminder_text = st.sidebar.text_area("内容を編集", value=st.session_state.reminder_text, height=200)

# --- メイン表示 ---
st.title("🚀 Strategist Dashboard: AI Scanner")

# 登録済みイベントの表示 (完全踏襲：年月日 + カウントダウン)
if st.session_state.events:
    st.write("📌 **追加イベント**")
    cols = st.columns(len(st.session_state.events))
    for i, event in enumerate(st.session_state.events):
        e_date = datetime.strptime(event['date'], "%Y-%m-%d")
        display_date = e_date.strftime("%Y/%m/%d")
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
        # 【機能踏襲】日本株の銘柄表示を「コード + 名前」に
        raw_code = key.split('_')[0]
        display_name = f"{raw_code} {info.get('name', '')}"
        
        # 【機能踏襲】詳細な区分判定と損益計算
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
