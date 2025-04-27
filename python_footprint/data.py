import websocket
import json
import csv
import os
from datetime import datetime

# === CONFIG ===
SYMBOL = "XMRUSDT"
WS_URL = f"wss://fstream.binance.com/ws/{SYMBOL.lower()}@trade"
CSV_FILENAME = f"tick_data_{SYMBOL}_{datetime.now().strftime('%Y-%m-%d')}.csv"

# === Ensure CSV file with headers exists ===
def init_csv_file():
    if not os.path.exists(CSV_FILENAME):
        with open(CSV_FILENAME, mode='w', newline='') as file:
            writer = csv.writer(file)
            writer.writerow(["timestamp_ms", "price", "quantity", "side", "symbol", "trade_id"])

# === Parse and save trade data ===
def save_trade_to_csv(data):
    timestamp_ms = data["T"]
    price = float(data["p"])
    quantity = float(data["q"])
    side = "sell" if data["m"] else "buy"
    trade_id = data["t"]
    symbol = data["s"]

    row = [timestamp_ms, price, quantity, side, symbol, trade_id]

    with open(CSV_FILENAME, mode='a', newline='') as file:
        writer = csv.writer(file)
        writer.writerow(row)

# === WebSocket Callbacks ===
def on_message(ws, message):
    trade = json.loads(message)
    save_trade_to_csv(trade)

def on_error(ws, error):
    print("WebSocket error:", error)

def on_close(ws, close_status_code, close_msg):
    print("WebSocket closed")

def on_open(ws):
    print(f"Connected to {WS_URL} and writing to {CSV_FILENAME}")

# === Main ===
if __name__ == "__main__":
    init_csv_file()
    ws = websocket.WebSocketApp(
        WS_URL,
        on_open=on_open,
        on_message=on_message,
        on_error=on_error,
        on_close=on_close
    )
    ws.run_forever()
