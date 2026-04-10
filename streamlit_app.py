import streamlit as st
import yfinance as yf
from datetime import datetime
import pandas as pd
from PIL import Image
import google.generativeai as genai

# --- 1. アプリ設定 ---
st.set_page_config(page_title="1% Investor Dashboard", layout="centered")

# --- 2. 確定済みポジションデータ (2026/04/10 精査) ---
# 米国株
US_POSITIONS = [
    {"ticker": "MU",   "name": "マイクロン",     "shares": 71,   "cost": 374.88},
    {"ticker": "VRT",  "name": "バーティブ",     "shares": 70,   "cost": 264.44},
    {"ticker": "NEE",  "name": "ネクステラ",     "shares": 105,  "cost": 93.75},
]

# 日本株 IHI (現物 1,400株 / 信用売 300株)
IHI_LONG_SHARES = 1400
IHI_LONG_COST = 3425.4
IHI_SHORT_SHARES = 300
IHI_SHORT_COST = 3350.0  # ※実際の約定単価に合わせて調整してください

# --- 3. 市場データの取得 (yfinance) ---
@st.cache_data(ttl=3600)
def get_market_data():
    forex = yf.Ticker("JPY=X").history(period="1d")
    rate = forex['Close'].iloc[-1]
    
    # 米国株の計算
    us_display_list = []
    total_us_profit = 0
    for p in US_POSITIONS:
        price = yf.Ticker(p["ticker"]).history(period="1d")['Close'].iloc[-1]
        p_profit = (price - p["cost"]) * p["shares"] * rate
        total_us_profit += p_profit
        us_display_list.append({
            "銘柄": p["name"],
            "数量": p["shares"],
            "取得単価": f"${p['cost']:,.2f}",
            "現在値": f"${price:,.2f}",
            "損益(円)": p_profit
        })

    # IHIの計算
    ihi_price = yf.Ticker("7013.T").history(period="1d")['Close'].iloc[-1]
    ihi_l_profit = (ihi_price - IHI_LONG_COST) * IHI_LONG_SHARES
    ihi_s_profit = (IHI_SHORT_COST - ihi_price) * IHI_SHORT_SHARES
    
    return us_display_list, ihi_l_profit, ihi_s_profit, ihi_price, rate

with st.spinner('全銘柄の最新データを取得中...'):
    us_results, ihi_l_prof, ihi_s_prof, ihi_now, current_rate = get_market_data()

# --- 4. メイン表示 ---
st.title("🚀 1%の投資家：出口戦略ボード")
days_left = (datetime(2026, 5, 29) - datetime.now()).days
st.metric("5/29 出口ターゲットまで", f"あと {days_left} 日")

st.divider()

# 総合計の計算
total_profit = sum(d["損益(円)"] for d in us_results) + ihi_l_prof + ihi_s_prof
st.header("💰 総合損益状況")
c1, c2 = st.columns(2)
c1.metric("総損益 (日本円計)", f"¥{total_profit:,.0f}", delta=f"{total_profit/10000:.1f}万円")
c2.metric("現在のドル円", f"¥{current_rate:.2f}")

st.divider()

# --- 5. 米国株セクション ---
st.subheader("🇺🇸 米国株ポートフォリオ")
df_us = pd.DataFrame(us_results)
df_us['損益(円)'] = df_us['損益(円)'].map('¥{:,.0f}'.format)
st.table(df_us)

# --- 6. 日本株セクション (IHI両建て対応) ---
st.subheader("🇯🇵 日本株：IHI (7013) 戦略状況")
i1, i2, i3 = st.columns(3)
i1.metric("現物買い (1,400株)", f"¥{ihi_l_prof:,.0f}")
i2.metric("信用売り (300株)", f"¥{ihi_s_prof:,.0f}")
i3.metric("IHI合計損益", f"¥{ihi_l_prof + ihi_s_prof:,.0f}")
st.caption(f"現在のIHI株価: ¥{ihi_now:,.1f} / 実質リスク保有数: {IHI_LONG_SHARES - IHI_SHORT_SHARES}株")

st.divider()

# --- 7. AI診断セクション ---
st.header("📸 AIチャート・画像診断")
uploaded_file = st.file_uploader("診断画像をアップロード", type=["png", "jpg", "jpeg"])
if uploaded_file and st.button("AIコンシェルジュに診断を依頼"):
    with st.spinner('最新のGemini 2.0 Flashで分析中...'):
        try:
            genai.configure(api_key=st.secrets["GEMINI_API_KEY"])
            model = genai.GenerativeModel('gemini-2.0-flash')
            prompt = f"""
            あなたは「1%の投資家」の専属コンシェルジュです。
            状況：総損益 {total_profit:,.0f}円、出口まで残り {days_left}日。
            保有：MU, VRT, NEE、および IHI（現物1400/信用売300の両建て）。
            この画像を分析し、品格ある日本語でアドバイスしてください。
            """
            response = model.generate_content([prompt, Image.open(uploaded_file)])
            st.info(response.text)
        except Exception as e:
            st.warning("AIは現在、無料枠の制限（429）により休憩中です。数分お待ちください。")
