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

# --- 1. ブラウザ保存 (JavaScript) のための部品 ---
def save_to_browser(key, data):
    """ブラウザのlocalStorageにデータを保存するJSを実行"""
    js_code = f"""
    <script>
    localStorage.setItem('{key}', JSON.stringify({json.dumps(data, ensure_ascii=False)}));
    </script>
    """
    html(js_code, height=0)

def load_from_browser():
    """ブラウザからデータを読み込むためのJSとコールバック"""
    # JSでlocalStorageから取得し、StreamlitのURLパラメータ経由で戻す手法
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

# --- 2. データの初期化と自動復元ロジック ---
# URLパラメータにデータがある場合はそれを優先（自動復元）
query_params = st.query_params
if "data" in query_params and 'portfolio' not in st.session_state:
    try:
        saved_data = json.loads(query_params["data"])
        st.session_state.portfolio = saved_data.get("portfolio", {})
        st.session_state.events = saved_data.get("events", [])
        st.session_state.reminder_text = saved_data.get("reminder_text", "- ターゲット日程を入力してください")
        st.session_state.api_key = saved_data.get("api_key", "")
    except: pass

# 未初期化の場合のデフォルト値
if 'portfolio' not in st.session_state: st.session_state.portfolio = {}
if 'events' not in st.session_state: st.session_state.events = []
if 'reminder_text' not in st.session_state: st.session_state.reminder_text = "- ターゲット日程を入力してください"
if 'api_key' not in st.session_state: st.session_state.api_key = ""
if 'edit_mode' not in st.session_state: st.session_state.edit_mode = False

# --- 3. 共通関数 (ロジック完全踏襲) ---
def analyze_images(files):
    if not st.session_state.api_key: raise ValueError("APIキーが必要です")
    genai.configure(api_key=st.session_state.api_key)
    model = genai.GenerativeModel("gemini-1.5-flash")
    prompt = "証券口座の画像から保有銘柄を抽出してJSONで回答してください。同一銘柄は合算。日本株=JPY、米国株=USD。"
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

# --- 4. UI構築 ---
st.set_page_config(page_title="Strategist Dashboard", layout="wide")

# 起動時に一度だけブラウザから読み込みを試行
load_from_browser()

# サイドバー
st.sidebar.header("🔑 System & Auto Save")
input_key = st.sidebar.text_input("Gemini API Key", value=st.session_state.api_key, type="password")

# 【自動保存のトリガー】
if st.sidebar.button("設定をブラウザに自動保存"):
    st.session_state.api_key = input_key
    save_data = {
        "portfolio": st.session_state.portfolio,
        "events": st.session_state.events,
        "reminder_text": st.session_state.reminder_text,
        "api_key": st.session_state.api_key
    }
    save_to_browser('strategist_data', save_data)
    st.sidebar.success("ブラウザに保存しました！次回から自動で読み込まれます。")

st.sidebar.divider()
# 画像解析
up_imgs = st.sidebar.file_uploader("スクショをアップロード", type=["png", "jpg"], accept_multiple_files=True)
if up_imgs and st.sidebar.button("AIで解析実行"):
    with st.sidebar.spinner("解析中..."):
        st.session_state.portfolio = analyze_images(up_imgs)
        st.rerun()

# イベント管理
st.sidebar.header("📅 Event Manager")
e_name = st.sidebar.text_input("イベント名")
e_date = st.sidebar.date_input("日付")
if st.sidebar.button("イベント登録") and e_name:
    st.session_state.events.append({"id": len(st.session_state.events)+1, "name": e_name, "date": e_date.strftime("%Y-%m-%d")})
    st.rerun()

# --- メイン表示 ---
st.title("🚀 Strategist Dashboard")

# カウントダウン
if st.session_state.events:
    cols = st.columns(len(st.session_state.events))
    for i, ev in enumerate(st.session_state.events):
        d = datetime.strptime(ev['date'], "%Y-%m-%d")
        with cols[i]: st.metric(f"{d.strftime('%m/%d')} {ev['name']}", f"{(d - datetime.now()).days} 日")

st.divider()

# ポートフォリオ監視 (完全踏襲)
st.header("📉 Portfolio Monitor")
prices = get_prices(st.session_state.portfolio.keys())
rows, total_jpy, total_usd = [], 0, 0

for k, info in st.session_state.portfolio.items():
    cur = prices.get(k)
    if cur:
        if "_SHORT" in k: label, p_jpy = "信用(売)", (info['cost']-cur)*info['shares']
        elif "_MARGIN_LONG" in k: label, p_jpy = "信用(買)", (cur-info['cost'])*info['shares']
        else:
            label = "現物"
            if info['currency']=="USD":
                p_usd = (cur-info['cost'])*info['shares']
                p_jpy = p_usd * prices["USDJPY"]
                total_usd += p_usd
            else: p_jpy = (cur-info['cost'])*info['shares']
        
        total_jpy += p_jpy
        rows.append({
            "銘柄": f"{k.split('_')[0]} {info.get('name','')}",
            "区分": label, "数量": info['shares'],
            "取得単価": f"${info['cost']:,}" if info['currency']=="USD" else f"¥{info['cost']:,}",
            "現在値": f"${cur:,.2f}" if info['currency']=="USD" else f"¥{cur:,.0f}",
            "損益(円)": f"¥{p_jpy:,.0f}"
        })

c1, c2, c3 = st.columns([3, 2, 5])
c1.metric("総計損益 (JPY)", f"¥{total_jpy:,.0f}", delta=f"USD/JPY: {prices['USDJPY']:.2f}")
c2.metric("米国株損益 (USD)", f"${total_usd:,.2f}")
if c3.button("更新"): st.rerun()
if rows: st.table(pd.DataFrame(rows))

st.divider()
st.subheader("📋 Reminder")
col_r1, col_r2 = st.columns([8, 2])
if col_r2.button("編集"): st.session_state.edit_mode = not st.session_state.edit_mode
if st.session_state.edit_mode:
    st.session_state.reminder_text = st.text_area("内容を編集", value=st.session_state.reminder_text, height=200)
else:
    st.info(st.session_state.reminder_text)
