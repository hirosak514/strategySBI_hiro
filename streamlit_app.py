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
import gspread
from google.oauth2.service_account import Credentials
import requests
from bs4 import BeautifulSoup

# --- 0. データの保存・読み込み ---
DB_FILE = "portfolio.json"
EVENT_FILE = "events.json"
REMINDER_FILE = "reminder.json"
CONFIG_FILE = "config.json"

FIXED_SHEET_URL = "https://docs.google.com/spreadsheets/d/17kAFl14q8EaaQ6kvezlAe1Yzr71Yo673T61--_cyESQ/edit"

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

# --- Google Spreadsheet 連携 ---
def get_gspread_client():
    scopes = ["https://www.googleapis.com/auth/spreadsheets", "https://www.googleapis.com/auth/drive"]
    try:
        creds_dict = st.secrets["gcp_service_account"]
        credentials = Credentials.from_service_account_info(creds_dict, scopes=scopes)
        return gspread.authorize(credentials)
    except Exception as e:
        return None

def export_to_spreadsheet(data):
    gc = get_gspread_client()
    if not gc: return
    try:
        sh = gc.open_by_url(FIXED_SHEET_URL)
        ws = sh.get_worksheet(0)
        ws.clear()
        ws.update('A1', [[json.dumps(data, ensure_ascii=False)]])
        st.success("エクスポート完了")
    except Exception as e:
        st.error(f"エクスポート失敗: {e}")

def import_from_spreadsheet():
    gc = get_gspread_client()
    if not gc: return None
    try:
        sh = gc.open_by_url(FIXED_SHEET_URL)
        ws = sh.get_worksheet(0)
        content = ws.acell('A1').value
        return json.loads(content) if content else None
    except Exception as e:
        return None

# --- 1. セッション状態の初期化 ---
if 'portfolio' not in st.session_state:
    st.session_state.portfolio = load_json(DB_FILE, {})
if 'prev_portfolio' not in st.session_state:
    st.session_state.prev_portfolio = None
if 'events' not in st.session_state:
    st.session_state.events = load_json(EVENT_FILE, [])
if 'reminder_text' not in st.session_state:
    st.session_state.reminder_text = load_json(REMINDER_FILE, "- ターゲット日程を入力してください")
if 'api_key' not in st.session_state:
    st.session_state.api_key = load_json(CONFIG_FILE, {"gemini_key": ""}).get("gemini_key", "")

def backup_portfolio():
    st.session_state.prev_portfolio = copy.deepcopy(st.session_state.portfolio)

# --- 2. API設定 ---
current_api_key = st.session_state.api_key or st.secrets.get("GEMINI_API_KEY", "")
if current_api_key:
    genai.configure(api_key=current_api_key)

# --- 3. 【重要改修】ハイブリッド価格取得関数 ---
@st.cache_data(ttl=60)
def get_live_prices(portfolio_keys):
    prices = {}
    for key in portfolio_keys:
        symbol = key.split('_')[0]
        is_japan = bool(re.match(r'^\d{4}$', symbol))
        ticker_symbol = f"{symbol}.T" if is_japan else ("7013.T" if symbol == "IHI" else symbol)
        
        current = 0
        prev_close = 0
        
        # A. Yahoo Finance 試行
        try:
            stock = yf.Ticker(ticker_symbol)
            info = stock.info
            current = info.get('regularMarketPrice') or info.get('currentPrice')
            prev_close = info.get('previousClose')
        except:
            pass

        # B. 【解決策】日本株で価格が0の場合、株探(Kabu-tan)から取得
        if is_japan and (current is None or current == 0):
            try:
                url = f"https://kabutan.jp/stock/?code={symbol}"
                headers = {"User-Agent": "Mozilla/5.0"}
                res = requests.get(url, headers=headers, timeout=5)
                soup = BeautifulSoup(res.text, 'html.parser')
                
                # 現値の抽出
                price_tag = soup.find('span', class_='kabuka')
                if price_tag:
                    current = float(price_tag.text.replace(',', '').replace('円', ''))
                
                # 前日比から前日終値を逆算
                change_tag = soup.find('span', class_='zenjitsu_at')
                if change_tag and current:
                    change_text = change_tag.text.replace(',', '').replace('円', '')
                    # 数値部分だけを取り出す
                    match = re.search(r'[+-]?\d+\.?\d*', change_text)
                    if match:
                        change_val = float(match.group())
                        prev_close = current - change_val
            except:
                pass

        # C. 最終フォールバック
        if current is None or current == 0:
            try:
                hist = yf.Ticker(ticker_symbol).history(period="1d")
                current = hist['Close'].iloc[-1] if not hist.empty else 0
                prev_close = current # 取得できない場合は現値を入れる
            except:
                current = 0

        prices[key] = {"current": current, "prev_close": prev_close if prev_close else current}
            
    # 為替
    try:
        usdjpy = yf.Ticker("JPY=X")
        prices["USDJPY"] = usdjpy.history(period="1d")['Close'].iloc[-1]
    except:
        prices["USDJPY"] = 159.2
    return prices

def analyze_multiple_images(uploaded_files):
    if not current_api_key:
        raise ValueError("APIキーが設定されていません。")
    model = genai.GenerativeModel("gemini-1.5-flash")
    prompt = """証券口座のスクリーンショットから保有銘柄を抽出し、以下のJSON形式のみで回答。
    {"銘柄コード_区分": {"name": "銘柄名", "shares": 数量, "cost": 取得単価, "currency": "通貨"}}"""
    images = [Image.open(f) for f in uploaded_files]
    response = model.generate_content([prompt] + images)
    json_match = re.search(r'\{.*\}', response.text, re.DOTALL)
    if json_match: return json.loads(json_match.group())
    raise ValueError("解析失敗")

# --- 4. UI設定 (オリジナルに完全忠実) ---
st.set_page_config(page_title="Strategist Dashboard", layout="wide")

st.markdown("""
<style>
    [data-testid="stMetricDelta"] > div { color: white !important; }
    div[data-testid="column"]:nth-child(3) button {
        background-color: #ff4b4b !important;
        color: white !important;
    }
</style>
""", unsafe_allow_html=True)

with st.sidebar:
    st.header("🔑 Settings")
    new_api_key = st.text_input("Gemini API Key", value=st.session_state.api_key, type="password")
    if st.button("APIキーを保存"):
        st.session_state.api_key = new_api_key
        save_json(CONFIG_FILE, {"gemini_key": new_api_key})
        st.success("保存完了")
        st.rerun()

    st.divider()
    st.header("✏️ 銘柄情報の直接入力")
    portfolio_items = list(st.session_state.portfolio.keys())
    selected_no = None
    if portfolio_items:
        selected_no = st.selectbox("銘柄No.を選択", options=[i + 1 for i in range(len(portfolio_items))])
        target_key = portfolio_items[selected_no - 1]
        target_info = st.session_state.portfolio[target_key]
        new_shares = st.number_input(f"数量 ({target_key})", value=float(target_info.get('shares', 0)))
        new_cost = st.number_input(f"取得単価 ({target_key})", value=float(target_info.get('cost', 0)))
        
        c1, c2, c3 = st.columns(3)
        if c1.button("修正"):
            backup_portfolio()
            st.session_state.portfolio[target_key].update({'shares': new_shares, 'cost': new_cost})
            save_json(DB_FILE, st.session_state.portfolio)
            st.rerun()
        if c2.button("復元", type="primary"):
            if st.session_state.prev_portfolio:
                st.session_state.portfolio = copy.deepcopy(st.session_state.prev_portfolio)
                save_json(DB_FILE, st.session_state.portfolio)
                st.rerun()
        if c3.button("削除"):
            backup_portfolio()
            del st.session_state.portfolio[target_key]
            save_json(DB_FILE, st.session_state.portfolio)
            st.rerun()
    else:
        st.info("データなし")

    st.divider()
    st.header("📌 Event Manager")
    with st.expander("追加/削除"):
        ev_name = st.text_input("イベント名")
        ev_date = st.date_input("日付")
        if st.button("追加"):
            st.session_state.events.append({"name": ev_name, "date": ev_date.strftime("%Y-%m-%d")})
            save_json(EVENT_FILE, st.session_state.events)
            st.rerun()
        if st.session_state.events:
            idx = st.selectbox("削除対象", range(len(st.session_state.events)), format_func=lambda x: st.session_state.events[x]['name'])
            if st.button("選択削除"):
                st.session_state.events.pop(idx)
                save_json(EVENT_FILE, st.session_state.events)
                st.rerun()

    st.divider()
    st.header("📋 Reminder Edit")
    new_rem = st.text_area("内容", value=st.session_state.reminder_text, height=150)
    if st.button("リマインダー更新"):
        st.session_state.reminder_text = new_rem
        save_json(REMINDER_FILE, new_rem)
        st.rerun()

    st.divider()
    st.subheader("💾 Backup")
    if st.button("エクスポート"):
        export_to_spreadsheet({"portfolio": st.session_state.portfolio, "events": st.session_state.events, "reminder_text": st.session_state.reminder_text})
    if st.button("インポート"):
        data = import_from_spreadsheet()
        if data:
            st.session_state.portfolio = data.get("portfolio", {})
            st.session_state.events = data.get("events", [])
            st.session_state.reminder_text = data.get("reminder_text", "")
            save_json(DB_FILE, st.session_state.portfolio)
            st.rerun()

    st.divider()
    st.header("📸 AI Scanner")
    up = st.file_uploader("アップロード", type=["png", "jpg"], accept_multiple_files=True)
    if up and st.button("解析"):
        st.session_state.portfolio = analyze_multiple_images(up)
        save_json(DB_FILE, st.session_state.portfolio)
        st.rerun()

# --- 5. メイン画面 (オリジナル準拠) ---
st.title("🚀 Strategist Dashboard")

if st.session_state.events:
    cols = st.columns(len(st.session_state.events))
    for i, event in enumerate(st.session_state.events):
        d = (datetime.strptime(event['date'], "%Y-%m-%d") - datetime.now()).days
        cols[i].metric(event['name'], event['date'], f"あと {d} 日")

st.divider()
st.header("📉 Portfolio Monitor")
if st.button('最新価格に更新'):
    st.cache_data.clear()
    st.rerun()

prices_dict = get_live_prices(list(st.session_state.portfolio.keys()))
rate = prices_dict.get("USDJPY", 159.2)

rows = []
total_profit_jpy = 0
total_profit_usd = 0

for i, (key, info) in enumerate(st.session_state.portfolio.items()):
    p_data = prices_dict.get(key)
    if p_data:
        cur, prev = p_data["current"], p_data["prev_close"]
        chg_pct = f"({(cur - prev) / prev * 100:+.2f}%)" if prev and cur else ""
        
        if info['shares'] == 0:
            label, p_jpy = "決済済", 0
        else:
            if "_SHORT" in key:
                label, p_jpy = "信用(売建)", (info['cost'] - cur) * info['shares']
            elif "_MARGIN_LONG" in key:
                label, p_jpy = "信用(買建)", (cur - info['cost']) * info['shares']
            else:
                label = "現物"
                if info.get('currency') == "USD":
                    p_usd = (cur - info['cost']) * info['shares']
                    p_jpy = p_usd * rate
                    total_profit_usd += p_usd
                else: p_jpy = (cur - info['cost']) * info['shares']

        total_profit_jpy += p_jpy
        cost_disp = f"${info['cost']:,}" if info.get('currency') == "USD" else f"¥{info['cost']:,}"
        cur_disp = f"{('$' if info.get('currency') == 'USD' else '¥')}{cur:,.2f} {chg_pct}"
        
        rows.append({
            "No.": i + 1, "銘柄": f"{key.split('_')[0]} {info.get('name','')}", "数量": info['shares'], "区分": label,
            "取得単価": cost_disp, "現在値 (前日比)": cur_disp, "損益(円)": f"¥{p_jpy:,.0f}"
        })

m1, m2 = st.columns(2)
m1.metric("総合計損益 (JPY)", f"¥{total_profit_jpy:,.0f}", delta=f"USD/JPY: {rate:.2f}")
m2.metric("米国株合計損益 (USD)", f"${total_profit_usd:,.2f}")

if rows:
    st.table(pd.DataFrame(rows))
else:
    st.info("データなし")

st.divider()
st.subheader("📋 Reminder")
st.info(st.session_state.reminder_text)
