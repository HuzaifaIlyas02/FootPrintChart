# app.py
import os
import csv
import json
import time
import threading
from collections import defaultdict
from flask import Flask, jsonify, send_file
import requests
import websocket
from flask_cors import CORS

app = Flask(__name__)

# Enable CORS for the Flask app
CORS(app)

# ----------------------------
# Configurations and Globals
# ----------------------------

BINANCE_WS_URL = "wss://fstream.binance.com/ws/xmrusdt@trade"

# We want separate timeframes.
TIMEFRAMES = ["1m", "3m", "5m", "15m", "1h", "4h"]
SYMBOL = "XMRUSDT"  # For REST API, uppercase; for WS URL we use lowercase.

# Directory for CSV files (one per timeframe)
DATA_DIR = os.path.join(os.path.dirname(__file__), 'data')
if not os.path.exists(DATA_DIR):
    os.mkdir(DATA_DIR)

# Global dictionaries to store data for each timeframe.
# For each timeframe (key), we store:
#   - finalized_data: list of finalized (completed) candle summaries.
#   - current_data: the in-progress candle summary (dictionary) including an extra key 'bucket'
#   - latest_footprint: the most recent finalized summary (for API use)
finalized_data = {tf: [] for tf in TIMEFRAMES}
current_data = {tf: None for tf in TIMEFRAMES}
latest_footprint = {tf: None for tf in TIMEFRAMES}
# Global cumulative delta per timeframe
cumulative_delta = {tf: 0 for tf in TIMEFRAMES}

# CSV headers for each timeframe file.
CSV_FIELDS = [
    "bucket", "total_volume", "buy_volume", "sell_volume",
    "buy_contracts", "sell_contracts",
    "open", "high", "low", "close",
    "delta", "max_delta", "min_delta", "CVD", "buy_sell_ratio",
    "pocs", "price_levels", "imbalances"
]

# ----------------------------
# Load Existing CSV Data (if any)
# ----------------------------
def load_existing_data():
    """
    Check each CSV file only once at startup. If the CSV file for a timeframe is not empty,
    load its content into finalized_data so that new data will be appended starting from the last line.
    """
    for tf in TIMEFRAMES:
        filename = os.path.join(DATA_DIR, f"footprint_{tf}.csv")
        if os.path.exists(filename) and os.path.getsize(filename) > 0:
            with open(filename, "r") as f:
                reader = csv.DictReader(f)
                for row in reader:
                    # Convert JSON string fields back to their native Python types.
                    for key in ["pocs", "price_levels", "imbalances"]:
                        if key in row and row[key]:
                            try:
                                row[key] = json.loads(row[key])
                            except Exception:
                                # If conversion fails, leave the value as is.
                                pass
                    finalized_data[tf].append(row)

# Call the load function once at startup.
load_existing_data()

# ----------------------------
# Helper Functions
# ----------------------------
def timeframe_to_seconds(tf):
    """Convert a timeframe string (e.g. '1m', '3m', '1h') to number of seconds."""
    unit = tf[-1]
    value = int(tf[:-1])
    if unit == "m":
        return value * 60
    elif unit == "h":
        return value * 3600
    else:
        return value

# ----------------------------
# CSV Helper – Write CSV file for a given timeframe.
# (DONOT change the saving functionality)
# ----------------------------
def write_csv(tf):
    """Rewrite the CSV file for timeframe tf with finalized data and the current candle (if exists)."""
    filename = os.path.join(DATA_DIR, f"footprint_{tf}.csv")
    all_data = finalized_data[tf][:]
    if current_data[tf]:
        all_data.append(current_data[tf])
    # Open file for overwriting.
    with open(filename, "w", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(CSV_FIELDS)
        for summary in all_data:
            writer.writerow([
                summary.get("bucket", ""),
                summary.get("total_volume", ""),
                summary.get("buy_volume", ""),
                summary.get("sell_volume", ""),
                summary.get("buy_contracts", ""),
                summary.get("sell_contracts", ""),
                summary.get("open", ""),
                summary.get("high", ""),
                summary.get("low", ""),
                summary.get("close", ""),
                summary.get("delta", ""),
                summary.get("max_delta", ""),
                summary.get("min_delta", ""),
                summary.get("CVD", ""),
                summary.get("buy_sell_ratio", ""),
                json.dumps(summary.get("pocs", [])) if not isinstance(summary.get("pocs", []), str) else summary.get("pocs", ""),
                json.dumps(summary.get("price_levels", {})) if not isinstance(summary.get("price_levels", {}), str) else summary.get("price_levels", ""),
                json.dumps(summary.get("imbalances", [])) if not isinstance(summary.get("imbalances", []), str) else summary.get("imbalances", "")
            ])

# ----------------------------
# Footprint Calculation Functions
# ----------------------------
def process_trade(trade):
    """Process a single trade coming from Binance WS.
       Update the current candle in each timeframe.
    """
    global current_data, cumulative_delta
    trade_timestamp = trade["T"] // 1000  # seconds
    price = float(trade["p"])
    volume = float(trade["q"])
    is_seller = trade["m"]

    for tf in TIMEFRAMES:
        seconds = timeframe_to_seconds(tf)
        bucket = (trade_timestamp // seconds) * seconds  # bucket start time in seconds for this timeframe
        cd = current_data[tf]
        if cd is None or cd.get("bucket") != bucket:
            # New candle for this timeframe
            if cd is not None:
                # Finalize the previous candle
                finalize_candle(tf, cd["bucket"])
            # Create new current candle
            current_data[tf] = {
                "bucket": bucket,
                "buy_volume": 0,
                "sell_volume": 0,
                "buy_contracts": 0,
                "sell_contracts": 0,
                "trade_prices": [],
                "price_levels": defaultdict(lambda: {"buy": 0, "sell": 0, "buy_trades": 0, "sell_trades": 0}),
                "delta_per_level": {},
                # For OHLC, we store open, high, low, close later.
                "open": price,
                "high": price,
                "low": price,
                "close": price
            }
            cd = current_data[tf]
        # Append trade price
        cd["trade_prices"].append(price)
        # Update OHLC
        cd["close"] = price
        if price > cd["high"]:
            cd["high"] = price
        if price < cd["low"]:
            cd["low"] = price
        # Update volumes and contracts
        if is_seller:
            cd["sell_volume"] += volume
            cd["sell_contracts"] += 1
            cd["price_levels"][price]["sell"] += volume
            cd["price_levels"][price]["sell_trades"] = cd["price_levels"][price].get("sell_trades", 0) + 1
        else:
            cd["buy_volume"] += volume
            cd["buy_contracts"] += 1
            cd["price_levels"][price]["buy"] += volume
            cd["price_levels"][price]["buy_trades"] = cd["price_levels"][price].get("buy_trades", 0) + 1
        # Update delta at this price level
        buy_vol = cd["price_levels"][price]["buy"]
        sell_vol = cd["price_levels"][price]["sell"]
        cd["delta_per_level"][price] = buy_vol - sell_vol

def finalize_candle(tf, bucket):
    """Compute summary for the candle identified by 'bucket' for timeframe tf,
       store it in finalized_data[tf], update cumulative delta, and update latest_footprint.
    """
    global cumulative_delta
    cd = current_data[tf]
    if cd is None:
        return
    # Compute OHLC are already in cd.
    trade_prices = cd.get("trade_prices", [])
    if not trade_prices:
        return
    open_price = cd["open"]
    high_price = cd["high"]
    low_price = cd["low"]
    close_price = cd["close"]

    total_buy_volume = cd["buy_volume"]
    total_sell_volume = cd["sell_volume"]
    total_volume = total_buy_volume + total_sell_volume
    delta = total_buy_volume - total_sell_volume
    cumulative_delta[tf] += delta

    buy_contracts = cd["buy_contracts"]
    sell_contracts = cd["sell_contracts"]

    buy_sell_ratio = (total_buy_volume / total_sell_volume) if total_sell_volume > 0 else float('inf')

    # Compute POC: Price level(s) with maximum total volume (buy+sell)
    pocs = []
    pl = cd["price_levels"]
    volume_per_price = {price: data["buy"] + data["sell"] for price, data in pl.items()}
    if volume_per_price:
        max_volume = max(volume_per_price.values())
        for price, total in volume_per_price.items():
            if total == max_volume:
                pocs.append({
                    "price": price,
                    "total_volume": total,
                    "buy_volume": pl[price]["buy"],
                    "sell_volume": pl[price]["sell"]
                })
    # Imbalances – for each price level where one side is at least 3x the other.
    imbalances = []
    for price, data in pl.items():
        if data["buy"] >= 3 * data["sell"] and data["sell"] > 0:
            imbalances.append({"price": price, "type": "Bullish", "buy": data["buy"], "sell": data["sell"]})
        elif data["sell"] >= 3 * data["buy"] and data["buy"] > 0:
            imbalances.append({"price": price, "type": "Bearish", "buy": data["buy"], "sell": data["sell"]})
    max_delta = max(cd["delta_per_level"].values(), default=0)
    min_delta = min(cd["delta_per_level"].values(), default=0)

    summary = {
        "bucket": bucket,
        "total_volume": round(total_volume, 2),
        "buy_volume": round(total_buy_volume, 2),
        "sell_volume": round(total_sell_volume, 2),
        "buy_contracts": buy_contracts,
        "sell_contracts": sell_contracts,
        "open": round(open_price, 2),
        "high": round(high_price, 2),
        "low": round(low_price, 2),
        "close": round(close_price, 2),
        "delta": round(delta, 2),
        "max_delta": round(max_delta, 2),
        "min_delta": round(min_delta, 2),
        "CVD": round(cumulative_delta[tf], 2),
        "buy_sell_ratio": round(buy_sell_ratio, 2),
        "pocs": pocs,
        # Convert price_levels to normal dict with rounded numbers.
        "price_levels": {price: {
                "buy_volume": round(data["buy"], 2),
                "sell_volume": round(data["sell"], 2),
                "buy_trades": data.get("buy_trades", 0),
                "sell_trades": data.get("sell_trades", 0)
            } for price, data in cd["price_levels"].items()},
        "imbalances": imbalances
    }
    finalized_data[tf].append(summary)
    latest_footprint[tf] = summary
    # After finalizing, clear the current candle for this timeframe.
    current_data[tf] = None

def update_csv_files():
    """Continuously update CSV files (for all timeframes) every second."""
    while True:
        for tf in TIMEFRAMES:
            write_csv(tf)
        time.sleep(1)

# Start the CSV update thread.
csv_thread = threading.Thread(target=update_csv_files, daemon=True)
csv_thread.start()

# ----------------------------
# WebSocket & Background Trade Processing
# ----------------------------
def on_message(ws, message):
    trade = json.loads(message)
    process_trade(trade)

def start_websocket():
    ws = websocket.WebSocketApp(BINANCE_WS_URL, on_message=on_message)
    ws.run_forever()

ws_thread = threading.Thread(target=start_websocket, daemon=True)
ws_thread.start()

# ----------------------------
# Flask API Endpoints
# ----------------------------
@app.route('/api/footprint/history/<tf>', methods=['GET'])
def get_footprint_history(tf):
    if tf not in TIMEFRAMES:
        return jsonify({"error": "Invalid timeframe"}), 400
    filename = os.path.join(DATA_DIR, f"footprint_{tf}.csv")
    if not os.path.exists(filename):
        return jsonify({"error": "Data not found for timeframe"}), 404
    with open(filename, "r") as f:
        reader = csv.DictReader(f)
        data = list(reader)
    return jsonify(data)

# ----------------------------
# Run Flask App
# ----------------------------
if __name__ == '__main__':
    app.run(port=5000)
