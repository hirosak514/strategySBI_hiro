import requests
from bs4 import BeautifulSoup

@st.cache_data(ttl=60)
def get_live_prices(portfolio_keys):
    prices = {}
    for key in portfolio_keys:
        symbol = key.split('_')[0]
        is_japan = bool(re.match(r'^\d{4}$', symbol))
        ticker_symbol = f"{symbol}.T" if is_japan else ("7013.T" if symbol == "IHI" else symbol)
        
        current = 0
        prev_close = 0
        
        # --- Step 1: Yahoo Financeで取得を試みる ---
        try:
            stock = yf.Ticker(ticker_symbol)
            info = stock.info
            current = info.get('regularMarketPrice') or info.get('currentPrice') or info.get('bid')
            prev_close = info.get('previousClose') or info.get('regularMarketPreviousClose')
        except:
            pass

        # --- Step 2: 日本株でYahooが失敗した場合、株探（Kabu-tan）から取得 ---
        if is_japan and (current is None or current == 0):
            try:
                url = f"https://kabutan.jp/stock/?code={symbol}"
                res = requests.get(url, timeout=5)
                soup = BeautifulSoup(res.text, 'html.parser')
                
                # 株探のHTMLから現値と前日比を抽出
                price_tag = soup.find('span', class_='kabuka')
                if price_tag:
                    current = float(price_tag.text.replace(',', '').replace('円', ''))
                
                # 前日終値も取得（比較用）
                prev_tag = soup.find('dd', {'id': 'stock_info_d1'}) # 前日比などが含まれるエリア
                if prev_tag:
                    # 前日終値を直接取得するのが難しい場合は、現在の価格と前日比から逆算
                    change_tag = soup.find('span', class_='zenjitsu_at')
                    if change_tag:
                        change_text = change_tag.text.replace(',', '').replace('円', '')
                        change_val = float(re.findall(r'[+-]?\d+\.?\d*', change_text)[0])
                        prev_close = current - change_val
            except Exception as e:
                # ログが必要な場合は st.write(e)
                pass

        # --- Step 3: それでもダメな場合はHistoryから最後の足を取得 ---
        if current is None or current == 0:
            try:
                hist = yf.Ticker(ticker_symbol).history(period="1d")
                current = hist['Close'].iloc[-1] if not hist.empty else 0
            except:
                current = 0

        prices[key] = {"current": current, "prev_close": prev_close if prev_close else current}
            
    # 為替取得
    try:
        usdjpy = yf.Ticker("JPY=X")
        prices["USDJPY"] = usdjpy.info.get('regularMarketPrice') or usdjpy.history(period="1d")['Close'].iloc[-1]
    except:
        prices["USDJPY"] = 159.2
        
    return prices
