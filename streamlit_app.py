@st.cache_data(ttl=30) # キャッシュを30秒に短縮
def get_live_prices(portfolio_keys):
    prices = {}
    for key in portfolio_keys:
        symbol = key.split('_')[0]
        is_japan = symbol.isdigit() and len(symbol) == 4
        ticker_symbol = f"{symbol}.T" if is_japan else ("7013.T" if symbol == "IHI" else symbol)
        
        try:
            stock = yf.Ticker(ticker_symbol)
            # infoから複数の価格候補を取得し、最も適切なものを選択
            info = stock.info
            
            # currentPrice (米国株) または regularMarketPrice (日本株) を試行
            current = info.get('currentPrice') or info.get('regularMarketPrice')
            
            # それでも取れない場合はhistoryから最新1件を取得
            if current is None:
                hist = stock.history(period="1d")
                if not hist.empty:
                    current = hist['Close'].iloc[-1]
            
            # 前日終値の取得
            prev_close = info.get('previousClose') or info.get('regularMarketPreviousClose')
            if prev_close is None:
                hist_5d = stock.history(period="5d")
                if len(hist_5d) >= 2:
                    prev_close = hist_5d['Close'].iloc[-2]

            if current:
                prices[key] = {
                    "current": current,
                    "prev_close": prev_close
                }
            else:
                prices[key] = None
        except:
            prices[key] = None
            
    # 為替レート(USD/JPY)の取得
    try:
        usdjpy = yf.Ticker("JPY=X")
        # 為替もinfoから最新値を試行
        rate = usdjpy.info.get('regularMarketPrice') or usdjpy.history(period="1d")['Close'].iloc[-1]
        prices["USDJPY"] = rate
    except:
        prices["USDJPY"] = 159.2
    return prices
