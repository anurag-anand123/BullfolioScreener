from flask import Flask, jsonify, request
import yfinance as yf
import datetime
from flask_cors import CORS
import sys
import traceback
import csv
import time

app = Flask(__name__)
CORS(app)

# In-memory cache for the watchlist data
_watchlist_cache = None

# In-memory cache for stock data with a timestamp for expiration
_stock_data_cache = {}
CACHE_DURATION_SECONDS = 30 * 60  # Cache data for 30 minutes

def load_watchlist_data():
    """
    Loads and caches the watchlist data from the CSV file.
    """
    global _watchlist_cache
    if _watchlist_cache is not None:
        return _watchlist_cache

    try:
        data = []
        with open('watchlist.csv', mode='r') as file:
            reader = csv.DictReader(file)
            for row in reader:
                # Convert string returns to float and store them
                row['1 Year Returns'] = float(row.get('1 Year Returns', 0))
                row['2 Year Returns'] = float(row.get('2 Year Returns', 0))
                row['5 Year Returns'] = float(row.get('5 Year Returns', 0))
                row['10 Year Returns'] = float(row.get('10 Year Returns', 0))
                data.append(row)
        _watchlist_cache = data
        return data
    except FileNotFoundError:
        return None
    except Exception as e:
        print(f"Error loading watchlist data: {e}", file=sys.stderr)
        return None

# Route to serve the watchlist from the cached data
@app.route('/api/watchlist')
def get_watchlist():
    watchlist_data = load_watchlist_data()
    if watchlist_data is None:
        return jsonify({"error": "watchlist.csv not found or could not be processed."}), 500

    try:
        sort_order = request.args.get('sort', 'asc')
        sort_by = request.args.get('sortBy')
        
        start_rank = int(request.args.get('start_rank', 1))
        end_rank = int(request.args.get('end_rank', 50))
        
        if start_rank < 1 or end_rank < start_rank:
            return jsonify({"error": "Invalid rank range."}), 400

        # Create a mutable copy of the cached list for sorting/slicing
        filtered_data = list(watchlist_data)
        
        # Slice the list to get the desired rank range
        filtered_data = filtered_data[start_rank - 1:end_rank]
        
        # Only sort the data if a 'sortBy' parameter is provided
        if sort_by:
            # Check if the sort key exists to prevent a TypeError
            if sort_by not in filtered_data[0]:
                return jsonify({"error": f"Invalid sort key: {sort_by}."}), 400
            
            if sort_order == 'desc':
                filtered_data.sort(key=lambda x: x[sort_by], reverse=True)
            else:
                filtered_data.sort(key=lambda x: x[sort_by], reverse=False)

        return jsonify(filtered_data)
    except Exception as e:
        print(f"An error occurred in get_watchlist: {e}", file=sys.stderr)
        return jsonify({"error": "Internal server error."}), 500

# Route to fetch stock data from yfinance (this is now optimized)
@app.route('/api/stock_data')
def get_stock_data():
    try:
        ticker = request.args.get('ticker', 'AAPL').upper()
        period = request.args.get('period', '6mo')
        interval = request.args.get('interval', '1d')

        if not ticker:
            return jsonify({"error": "Stock ticker cannot be empty."}), 400
        
        # Create a unique cache key for this request
        cache_key = f"{ticker}_{period}_{interval}"
        
        # Check if the data is already in the cache and has not expired
        if cache_key in _stock_data_cache and \
           time.time() - _stock_data_cache[cache_key]['timestamp'] < CACHE_DURATION_SECONDS:
            print(f"Serving {cache_key} from cache.")
            return jsonify(_stock_data_cache[cache_key]['data'])

        # If not in cache or expired, fetch new data
        print(f"Fetching fresh data for {cache_key}...")
        data = yf.download(ticker, period=period, interval=interval, progress=False)
        
        if data.empty:
            print(f"Warning: No data found for {ticker} with period={period}, interval={interval}", file=sys.stderr)
            return jsonify({"error": f"No data found for the ticker: {ticker}. Please check the symbol."}), 404

        candlestick_data = []
        for index, row in data.iterrows():
            candlestick_data.append({
                "x": index.strftime('%Y-%m-%d'),
                "y": [
                    float(row['Open']),
                    float(row['High']),
                    float(row['Low']),
                    float(row['Close'])
                ]
            })
            
        # Store the new data in the cache with a timestamp
        _stock_data_cache[cache_key] = {
            'data': candlestick_data,
            'timestamp': time.time()
        }

        return jsonify(candlestick_data)

    except Exception as e:
        error_traceback = traceback.format_exc()
        print(f"An error occurred while fetching data:\n{error_traceback}", file=sys.stderr)
        return jsonify({"error": "An internal server error occurred. Check the server log for details."}), 500

if __name__ == '__main__':
    # Load data on app startup
    load_watchlist_data()
    app.run(port=5000, debug=True)