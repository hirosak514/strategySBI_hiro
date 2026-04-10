
import streamlit as st
import yfinance as yf
import pandas as pd
from datetime import datetime
import google.generativeai as genai
from PIL import Image
import json
import re
import os  # ファイル確認用に追加

# --- 0. データの保存・読み込み関数 ---
DB_FILE = "portfolio.json"

def load_data():
    """保存されたデータを読み込む。なければ初期値を返す"""
    if os.path.exists(DB_FILE):
        with open(DB_FILE, "r") as f:
            return json.load(f)
    return {
        "MU": {"shares": 71, "cost": 374.88, "currency": "USD"},
        "VRT": {"shares": 70, "cost": 264.44, "currency": "USD"},
        "IHI": {"shares": 1400, "cost": 3425.4, "currency": "JPY"}
    }

def save_data(data):
    """データをJSONファイルに保存する"""
    with open(DB_FILE, "w") as f:
        json.dump(data, f)

# --- 1. セッション状態の初期化 (ここを修正) ---
if 'portfolio' not in st.session_state:
    st.session_state.portfolio = load_data()

# --- (中略: get_live_prices, analyze_image 関数はそのまま) ---

# --- 5. Streamlit UI 構築 ---
# (サイドバーの解析成功時の処理に保存を追加)
if uploaded_file:
    if st.sidebar.button("AIでポジションを更新"):
        try:
            img = Image.open(uploaded_file)
            new_data = analyze_image(img)
            
            # セッションに反映
            for ticker, vals in new_data.items():
                if ticker in st.session_state.portfolio:
                    st.session_state.portfolio[ticker]["shares"] = vals["shares"]
                    st.session_state.portfolio[ticker]["cost"] = vals["cost"]
            
            # 【重要】解析直後にファイルへ保存
            save_data(st.session_state.portfolio)
            
            st.sidebar.success("解析完了！データを保存しました。")
            st.rerun() # 画面をリフレッシュして反映
        except Exception as e:
            st.sidebar.error(f"解析エラー: {e}")

# --- (以下、メイン表示部分はそのまま) ---
