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

# --- 1. ブラウザストレージ操作 (JavaScriptによる自動保存・復元) ---
def trigger_auto_save():
    """現在の全データをlocalStorageにサイレント保存"""
    save_data = {
        "portfolio": st.session_state.portfolio,
        "events": st.session_state.events,
        "reminder_text": st.session_state.reminder_text,
        "api_key": st.session_state.api_key
    }
    js_code = f"""
    <script>
    const data = {json.dumps(save_data, ensure_ascii=False)};
    localStorage.setItem('strategist_storage_v4', JSON.stringify(data));
    console.log("Strategist: Auto-saved successfully.");
    </script>
    """
    html(js_code, height=0)

def load_from_browser_js():
    """起動時にlocalStorageからデータを取得し、Streamlitに渡す"""
    js_code = """
    <script>
    const savedData = localStorage.getItem('strategist_storage_v4');
    if (savedData) {
        const url = new URL(window.location);
        if (!url.searchParams.get('init')) {
            window.parent.postMessage({
                type: 'streamlit:set_query_params', 
                query_params: {data: savedData, init: 'true'}
            }, '*');
        }
    }
    </script>
    """
    html(js_code, height=0)

# --- 2. データの初期化と自動復元ロジック ---
st.set_page_config(page_title="Strategist Dashboard", layout="wide")

# URLパラメータからデータを復元
query_params = st.query_params
if "data" in query_params and 'initialized' not in st.session_state:
    try:
        loaded = json.loads(query_params["data"])
        st.session_state.portfolio = loaded.get("portfolio", {})
        st.session_state.events = loaded.get("events", [])
        st.session_state.reminder_text = loaded.get("reminder_text", "- ターゲット日程を入力してください")
        st.session_state.api_key = loaded.get("api_key", "")
        st.session_state.initialized = True
    except: pass

# デフォルト値の設定
if 'portfolio' not in st.session_state: st.session_state.portfolio = {}
if 'events' not in st.session_state: st.session_state.events = []
if 'reminder_text' not in st.session_state: st.session_state.reminder_text = "- ターゲット日程を入力してください"
if 'api_key' not in st.session_state: st.session_state.api_key = ""
if 'edit_mode' not in st.session_state: st.session_state.edit_mode = False

# 起動時にJSを実行してデータを拾いに行く
load_from_browser_js()

# --- 3. AI解析関数 (404エラー対策・軽量化版) ---
def analyze_images(files):
    if not st.session_state.api_key: 
        st.error("APIキーを入力してください")
        return {}
    
    try:
        genai.configure(api_key=st.session_state.api_key)
        # 修正ポイント: プレフィックスを付けてモデルを明示指定
        model = genai.GenerativeModel(model_name="models/gemini-1.5-flash")
        
        prompt = "証券口座の画像から保有銘柄を抽出してJSONで回答してください。キー：現物=コード、信用買=コード_MARGIN_LONG、信用売=コード_SHORT。通貨=JPY/USD。"
        
        processed_images = []
        for f in files:
            img = Image.open(f)
            # 安定性のための軽量化
            img.thumbnail((1600, 1600))
            if img.mode != 'RGB':
                img = img.convert('RGB')
            processed_images.append(img)

        if not processed_images: return {}

        response = model.generate_content([prompt] + processed_images)
        json_match = re.search(r'\{.*\}', response.text, re.DOTALL)
        if json_match:
            return json.loads(json_match.group())
        else:
            st.error("AIの回答を解析できませんでした。")
            return {}
    except Exception as e:
        st.error(f"AI解析エラー: {str(e)}")
        return {}

# --- 4. 市場データ取得 (yfinance) ---
def get_prices(keys):
    prices = {"USDJPY": 159.07} # デフォルト
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

# --- 5. メインUI ---
st.title("🚀 Strategist Dashboard")

# サイドバー
st.sidebar.header("🔑 System & Data")
new_key = st.sidebar.text_input("Gemini API Key", value=st.session_state.api_key, type="password")
if new_key != st.session_state.api_key:
    st.session_state.api_key = new_key
    trigger_auto_save()

# バックアップ機能
st.sidebar.divider()
st.sidebar.subheader("💾 手動ファイル保存・読込")
export_json = json.dumps({"portfolio": st.session_state.portfolio, "events": st.session_state.events, "reminder_text": st.session_state.reminder_text, "api_key": st.session_state.api_key}, ensure_ascii=False, indent=4)
st.sidebar.download_button("設定をファイルに保存", data=export_json, file_name="strategy_backup.json", mime="application/json", use_container_width=True)

up_file = st.sidebar.file_uploader("保存ファイルを読み込む", type="json")
if up_file and st.sidebar.button("データを復元", use_container_width=True):
    try:
        data = json.load(up_file)
        st.session_state.portfolio = data.get("portfolio", {})
        st.session_state.events = data.get("events", [])
        st.session_state.reminder_text = data.get("reminder_text", "")
        st.session_state.api_key = data.get("api_key", "")
        trigger_auto_save()
        st.rerun()
    except: st.sidebar.error("形式が正しくありません")

# 画像解析
st.sidebar.divider()
st.sidebar.header("📸 Multi-Position Update")
up_imgs = st.sidebar.file_uploader("スクショをアップロード", type=["png", "jpg", "jpeg"], accept_multiple_files=True)
if up_imgs and st.sidebar.button("AIで解析実行"):
    with st.sidebar.spinner("解析中..."):
        res = analyze_images(up_imgs)
        if res:
            st.session_state.portfolio = res
            trigger_auto_save()
            st.rerun()

# イベント管理
st.sidebar.divider()
st.sidebar.header("📅 Event Manager")
e_n = st.sidebar.text_input("イベント名")
e_d = st.sidebar.date_input("日付")
if st.sidebar.button("登録"):
    if e_n:
        st.session_state.events.append({"id": len(st.session_state.events)+1, "name": e_n, "date": e_d.strftime("%Y-%m-%d")})
        trigger_auto_save()
        st.rerun()

# --- メインコンテンツ表示 ---
if st.session_state.events:
    st.write("📌 **今後の予定**")
    cols = st.columns(len(st.session_state.events))
    for i, ev in enumerate(st.session_state.events):
        d = datetime.strptime(ev['date'], "%Y-%m-%d")
        with cols[i]: st.metric(f"{ev['name']}", f"{(d - datetime.now()).days} 日")

st.divider()

# ポートフォリオ表示
st.header("📉 Real-time Portfolio Monitor")
prices = get_prices(st.session_state.portfolio.keys())
rate = prices.get("USDJPY", 159.07)
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
                p_jpy, total_usd = p_usd * rate, total_usd + p_usd
            else: p_jpy = (cur-info['cost'])*info['shares']
        
        total_jpy += p_jpy
        rows.append({"銘柄": f"{k.split('_')[0]} {info.get('name','')}", "区分": label, "数量": info['shares'], "取得単価": f"${info['cost']:,}" if info['currency']=="USD" else f"¥{info['cost']:,}", "現在値": f"${cur:,.2f}" if info['currency']=="USD" else f"¥{cur:,.0f}", "損益(円)": f"¥{p_jpy:,.0f}"})

c1, c2, c3 = st.columns([3, 2, 5])
c1.metric("総計損益 (JPY)", f"¥{total_jpy:,.0f}", delta=f"USD/JPY: {rate:.2f}")
c2.metric("米国株損益 (USD)", f"${total_usd:,.2f}")
if c3.button("🔄 更新"): st.rerun()
if rows: st.table(pd.DataFrame(rows))
else: st.info("ポートフォリオが空です。")

st.divider()
st.subheader("📋 1% Investor's Reminder")
col_r1, col_r2 = st.columns([8, 2])
if col_r2.button("編集"): st.session_state.edit_mode = not st.session_state.edit_mode
if st.session_state.edit_mode:
    st.session_state.reminder_text = st.text_area("内容を編集", value=st.session_state.reminder_text, height=150)
    if st.button("リマインダーを保存"):
        st.session_state.edit_mode = False
        trigger_auto_save()
        st.rerun()
else:
    st.info(st.session_state.reminder_text)
