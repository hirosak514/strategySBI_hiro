import streamlit as st
import yfinance as yf
import pandas as pd
from datetime import datetime
import google.generativeai as genai
from PIL import Image
import json
import re
import io
from streamlit.components.v1 import html

# --- 1. ブラウザ自動保存・復元 (JavaScript) ---
def save_to_browser(key, data):
    js_code = f"""
    <script>
    localStorage.setItem('{key}', JSON.stringify({json.dumps(data, ensure_ascii=False)}));
    </script>
    """
    html(js_code, height=0)

def load_from_browser():
    js_code = """
    <script>
    const data = localStorage.getItem('strategist_data');
    if (data) {
        const url = new URL(window.location);
        if (!url.searchParams.get('loaded')) {
            window.parent.postMessage({type: 'streamlit:set_query_params', query_params: {data: data, loaded: 'true'}}, '*');
        }
    }
    </script>
    """
    html(js_code, height=0)

# --- 2. データのエクスポート・インポート (手動ファイル操作) ---
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
        except: return False
    return False

# --- 3. セッション状態の初期化と自動復元 ---
query_params = st.query_params
if "data" in query_params and 'portfolio' not in st.session_state:
    try:
        saved_data = json.loads(query_params["data"])
        st.session_state.portfolio = saved_data.get("portfolio", {})
        st.session_state.events = saved_data.get("events", [])
        st.session_state.reminder_text = saved_data.get("reminder_text", "- ターゲット日程を入力してください")
        st.session_state.api_key = saved_data.get("api_key", "")
    except: pass

if 'portfolio' not in st.session_state: st.session_state.portfolio = {}
if 'events' not in st.session_state: st.session_state.events = []
if 'reminder_text' not in st.session_state: st.session_state.reminder_text = "- ターゲット日程を入力してください"
if 'api_key' not in st.session_state: st.session_state.api_key = ""
if 'edit_mode' not in st.session_state: st.session_state.edit_mode = False
if 'show_help' not in st.session_state: st.session_state.show_help = False

# --- 4. 解析・価格取得 (ロジック完全踏襲) ---
def analyze_images(files):
    if not st.session_state.api_key: raise ValueError("APIキーが必要です")
    genai.configure(api_key=st.session_state.api_key)
    model = genai.GenerativeModel("gemini-1.5-flash")
    prompt = """
    証券口座の画像から、保有しているすべての銘柄を抽出してください。
    【集計ルール】
    1. 銘柄名と種別（現物、信用買、信用売）が同じものは、数量を合計し、取得単価を平均してください。
    2. キー：現物=コード、信用買=コード_MARGIN_LONG、信用売=コード_SHORT。
    3. 日本株=JPY、米国株=USD。
    JSON形式のみで回答：{"キー": {"name": "銘柄名", "shares": 数量, "cost": 取得単価, "currency": "JPY/USD"}}
    """
    response = model.generate_content([prompt] + [Image.open(f) for f in files])
    return json.loads(re.search(r'\{.*\}', response.text, re.DOTALL).group())

def get_prices(keys):
    prices = {"USDJPY": 159.2}
    try: prices["USDJPY"] = yf.Ticker("JPY=X").history(period="1d")['Close'].iloc[-1]
    except: pass
    for k in keys:
        s = k.split('_')[0]
        t = f"{s}.T" if s.isdigit() and len(s)==4 else s
        try:
            h = yf.Ticker(t).history(period="1d")
            prices[k] = h['Close'].iloc[-1] if not h.empty else None
        except: prices[k] = None
    return prices

# --- 5. UI構築 ---
st.set_page_config(page_title="Strategist Dashboard", layout="wide")
load_from_browser()

# サイドバー
st.sidebar.header("🔑 System & Data Management")
# APIキー設定
input_key = st.sidebar.text_input("Gemini API Key", value=st.session_state.api_key, type="password")
if st.sidebar.button("APIキーを適用", use_container_width=True):
    st.session_state.api_key = input_key
    st.rerun()

# ★【自動保存ボタン】
if st.sidebar.button("✨ 現在の設定をブラウザに自動保存", use_container_width=True):
    save_data = {"portfolio": st.session_state.portfolio, "events": st.session_state.events, "reminder_text": st.session_state.reminder_text, "api_key": st.session_state.api_key}
    save_to_browser('strategist_data', save_data)
    st.sidebar.success("ブラウザに保存完了！次回から自動読込されます。")

st.sidebar.divider()

# ★【手動バックアップ・復元：完全踏襲】
st.sidebar.subheader("💾 手動ファイル保存・読込")
st.sidebar.download_button(label="現在の全データをファイルに保存", data=export_data(), file_name="strategy_dashboard_backup.json", mime="application/json", use_container_width=True)
uploaded_json = st.sidebar.file_uploader("保存ファイルを読み込む", type="json")
if uploaded_json and st.sidebar.button("データを復元する", use_container_width=True):
    if import_data(uploaded_json): st.rerun()

st.sidebar.divider()

# 画像解析 (完全踏襲)
st.sidebar.header("📸 Multi-Position Update")
up_imgs = st.sidebar.file_uploader("スクショをアップロード", type=["png", "jpg"], accept_multiple_files=True)
if up_imgs and st.sidebar.button("AIで全画像を解析・集計"):
    with st.sidebar.spinner("解析中..."):
        try:
            st.session_state.portfolio = analyze_images(up_imgs)
            st.rerun()
        except Exception as e: st.sidebar.error(f"解析エラー: {e}")

# イベント管理 (完全踏襲)
st.sidebar.divider()
st.sidebar.header("📅 Event Manager")
new_e_name = st.sidebar.text_input("イベント名を入力")
new_e_date = st.sidebar.date_input("日付を選択", value=datetime.now())
if st.sidebar.button("登録"):
    if new_e_name:
        st.session_state.events.append({"id": len(st.session_state.events)+1, "name": new_e_name, "date": new_e_date.strftime("%Y-%m-%d")})
        st.rerun()
if st.session_state.events:
    del_id = st.sidebar.number_input("削除No", min_value=1, step=1)
    if st.sidebar.button("削除"):
        st.session_state.events = [e for e in st.session_state.events if e['id'] != del_id]
        for i, e in enumerate(st.session_state.events): e['id'] = i + 1
        st.rerun()

st.sidebar.divider()
# リマインダー編集 (完全踏襲)
st.sidebar.header("📝 Reminder Editor")
col_e1, col_e2 = st.sidebar.columns(2)
if col_e1.button("IR編集"): st.session_state.edit_mode = True; st.rerun()
if col_e2.button("登録", key="save_ir"): st.session_state.edit_mode = False; st.rerun()
if st.session_state.edit_mode:
    st.session_state.reminder_text = st.sidebar.text_area("内容を編集", value=st.session_state.reminder_text, height=200)

# --- メイン表示 ---
st.title("🚀 Strategist Dashboard: AI Scanner")

# イベント表示 (完全踏襲)
if st.session_state.events:
    st.write("📌 **追加イベント**")
    cols = st.columns(len(st.session_state.events))
    for i, event in enumerate(st.session_state.events):
        e_date = datetime.strptime(event['date'], "%Y-%m-%d")
        with cols[i]: st.metric(f"No.{event['id']}: {e_date.strftime('%Y/%m/%d')} {event['name']}", f"{(e_date - datetime.now()).days} 日")

st.divider()
st.header("📉 Real-time Portfolio Monitor")

current_prices = get_prices(st.session_state.portfolio.keys())
rate = current_prices.get("USDJPY", 159.2)
rows, total_jpy, total_usd = [], 0, 0

for key, info in st.session_state.portfolio.items():
    cur = current_prices.get(key)
    if cur and info['shares'] > 0:
        raw_code = key.split('_')[0]
        display_name = f"{raw_code} {info.get('name', '')}"
        
        # 区分・損益計算 (完全踏襲)
        if "_SHORT" in key: label, p_jpy = "信用(売建)", (info['cost'] - cur) * info['shares']
        elif "_MARGIN_LONG" in key: label, p_jpy = "信用(買建)", (cur - info['cost']) * info['shares']
        else:
            label = "現物"
            if info.get('currency') == "USD":
                p_usd = (cur - info['cost']) * info['shares']
                p_jpy, total_usd = p_usd * rate, total_usd + p_usd
            else: p_jpy = (cur - info['cost']) * info['shares']

        total_jpy += p_jpy
        cost_disp = f"${info['cost']:,}" if info.get('currency') == "USD" else f"¥{info['cost']:,}"
        cur_disp = f"${cur:,.2f}" if info.get('currency') == "USD" else f"¥{cur:,.0f}"
        rows.append({"銘柄": display_name, "数量": info['shares'], "区分": label, "取得単価": cost_disp, "現在値": cur_disp, "損益(円)": f"¥{p_jpy:,.0f}"})

m_c1, m_c2, m_c3 = st.columns([3, 2, 5])
m_c1.metric("総計損益 (JPY)", f"¥{total_jpy:,.0f}", delta=f"USD/JPY: {rate:.2f}")
m_c2.metric("米国株損益 (USD)", f"${total_usd:,.2f}")
if m_c3.button('更新', key='main_update'): st.rerun()

if rows: st.table(pd.DataFrame(rows))
else: st.info("画像をアップロードしてください。")

st.divider()
st.subheader("📋 1% Investor's Reminder")
st.info(st.session_state.reminder_text)
