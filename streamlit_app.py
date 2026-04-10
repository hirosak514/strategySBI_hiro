import streamlit as st
import yfinance as yf
from datetime import datetime
import pandas as pd
from PIL import Image
import google.generativeai as genai

# --- 1. アプリ設定 ---
st.set_page_config(page_title="1% Investor Dashboard", layout="centered")

# --- 2. ポジションデータ (2026/04/10 精査) ---
# 米国株
US_POSITIONS = [
    {"ticker": "MU",   "name": "マイクロン",     "shares": 71,   "cost": 374.88},
    {"ticker": "VRT",  "name": "バーティブ",     "shares": 70,   "cost": 264.44},
    {"ticker": "NEE",  "name": "ネクステラ",     "shares": 105,  "cost": 93.75},
]

# 日本株 IHI (現物買い 1,400株 / 信用売り 300株)
IHI_LONG_SHARES = 1400
IHI_LONG_COST = 3425.4   # 平均取得単価
IHI_SHORT_SHARES = 300
IHI_SHORT_COST = 3350.0  # 仮の約定単価（画像に基づき調整してください）

# --- 3. 市場データの取得 (yfinance) ---
@st.cache_data(ttl=3600)
def get_market_data():
    forex = yf.Ticker("JPY=X").history(period="1d")
    rate = forex['Close'].iloc[-1]
    
    # 米国株計算
    us_results = []
    for p in US_POSITIONS:
        price = yf.Ticker(p["ticker"]).history(period="1d")['Close'].iloc[-1]
        profit_jpy = (price - p["cost"]) * p["shares"] * rate
        us_results.append({"銘柄": p["name"], "数量": p["shares"], "区分": "現物", "損益(円)": profit_jpy, "現在値": price})

    # IHI計算
    ihi_price = yf.Ticker("7013.T").history(period="1d")['Close'].iloc[-1]
    # 現物損益: (現在値 - 取得単価) * 数量
    ihi_long_profit = (ihi_price - IHI_LONG_COST) * IHI_LONG_SHARES
    # 信用売り損益: (売単価 - 現在値) * 数量 ※価格下落でプラス
    ihi_short_profit = (IHI_SHORT_COST - ihi_price) * IHI_SHORT_SHARES
    
    return us_results, ihi_long_profit, ihi_short_profit, ihi_price, rate

with st.spinner('データを取得中...'):
    us_data, ihi_l_profit, ihi_s_profit, ihi_now, current_rate = get_market_data()

# --- 4. メイン表示 ---
st.title("🚀 1%の投資家：出口戦略ボード")
days_left = (datetime(2026, 5, 29) - datetime.now()).days
st.metric("5/29 出口ターゲットまで", f"あと {days_left} 日")

st.divider()

# 総合計の計算
total_profit = sum(d["損益(円)"] for d in us_data) + ihi_l_profit + ihi_s_profit
st.header("💰 総合損益状況")
c1, c2 = st.columns(2)
c1.metric("総損益 (日本円計)", f"¥{total_profit:,.0f}", delta=f"実質保有 {IHI_LONG_SHARES - IHI_SHORT_SHARES}株")
c2.metric("現在のドル円", f"¥{current_rate:.2f}")

st.divider()

# --- 5. IHI詳細 (ヘッジ状況の可視化) ---
st.subheader("🏗️ IHI (7013) 戦略状況")
i1, i2, i3 = st.columns(3)
i1.write(f"**現物買い (1,400株)**\n\n¥{ihi_l_profit:,.0f}")
i2.write(f"**信用売り (300株)**\n\n¥{ihi_s_profit:,.0f}")
i3.write(f"**IHIトータル損益**\n\n**¥{ihi_l_profit + ihi_s_profit:,.0f}**")
st.caption(f"現在のIHI株価: ¥{ihi_now:,.1f}（信用売りが下落分を ¥{abs(ihi_s_profit):,.0f} カバー中）")

st.divider()

# --- 6. AI診断セクション ---
st.header("📸 AIチャート・画像診断")
uploaded_file = st.file_uploader("診断画像をアップロード", type=["png", "jpg", "jpeg"])
if uploaded_file and st.button("AIコンシェルジュに診断を依頼"):
    with st.spinner('分析中...'):
        try:
            genai.configure(api_key=st.secrets["GEMINI_API_KEY"])
            model = genai.GenerativeModel('gemini-2.0-flash')
            prompt = f"総損益 {total_profit:,.0f}円。IHIは現物1400株と信用売300株の両建て。出口まで{days_left}日。画像を分析して。"
            response = model.generate_content([prompt, Image.open(uploaded_file)])
            st.info(response.text)
        except Exception as e:
            st.warning("AIは現在制限中です。数分お待ちください。")
