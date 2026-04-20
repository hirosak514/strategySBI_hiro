@st.cache_data(ttl=60)
def get_live_prices(portfolio_keys):
    prices = {}
    for key in portfolio_keys:
        symbol = key.split('_')[0]
        is_japan = symbol.isdigit() and len(symbol) == 4
        ticker_symbol = f"{symbol}.T" if is_japan else ("7013.T" if symbol == "IHI" else symbol)
        
        try:
            stock = yf.Ticker(ticker_symbol)
            # infoから最新の市場価格を直接取得（これが最も正確です）
            info = stock.info
            current_price = info.get('regularMarketPrice')
            
            # もしinfoで取れない場合は、historyの最新行を使用
            if current_price is None:
                hist = stock.history(period="1d")
                if not hist.empty:
                    current_price = hist['Close'].iloc[-1]
            
            # 前日終値の取得
            prev_close = info.get('previousClose')
            if prev_close is None:
                hist_5d = stock.history(period="5d")
                if len(hist_5d) >= 2:
                    prev_close = hist_5d['Close'].iloc[-2]

            if current_price:
                prices[key] = {
                    "current": current_price,
                    "prev_close": prev_close
                }
            else:
                prices[key] = None
        except:
            prices[key] = None
            
    # 為替レートの取得
    try:
        usdjpy_ticker = yf.Ticker("JPY=X")
        rate = usdjpy_ticker.info.get('regularMarketPrice') or usdjpy_ticker.history(period="1d")['Close'].iloc[-1]
        prices["USDJPY"] = rate
    except:
        prices["USDJPY"] = 159.2
    return prices
