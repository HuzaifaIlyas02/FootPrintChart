import websockets
import json
import requests
import asyncio
from collections import defaultdict
from typing import Dict, List, Optional
import time

class OrderBookManager:
    def __init__(self, symbol: str):
        self.symbol = symbol
        self.bids: Dict[float, float] = {}  # price -> quantity
        self.asks: Dict[float, float] = {}  # price -> quantity
        self.last_update_id: Optional[int] = None
        self.previous_final_update_id: Optional[int] = None
        self.ws_url = f"wss://fstream.binance.com/stream?streams={symbol.lower()}@depth"
        self.snapshot_url = f"https://fapi.binance.com/fapi/v1/depth?symbol={symbol}&limit=1000"

    async def initialize(self):
        """Initialize the order book with a snapshot and start processing updates."""
        await self.get_snapshot()
        await self.process_stream()

    async def get_snapshot(self):
        """Get the initial order book snapshot."""
        print("Getting order book snapshot...")
        response = requests.get(self.snapshot_url)
        snapshot = response.json()

        self.last_update_id = snapshot['lastUpdateId']
        self.bids = {float(price): float(qty) for price, qty in snapshot['bids']}
        self.asks = {float(price): float(qty) for price, qty in snapshot['asks']}
        print(f"Snapshot received. Last update ID: {self.last_update_id}")

    def update_order_book(self, bids: List[List[str]], asks: List[List[str]]):
        """Update the order book with new bids and asks."""
        # Update bids
        for bid in bids:
            price, quantity = float(bid[0]), float(bid[1])
            if quantity == 0:
                self.bids.pop(price, None)  # Remove the price level if it exists
            else:
                self.bids[price] = quantity

        # Update asks
        for ask in asks:
            price, quantity = float(ask[0]), float(ask[1])
            if quantity == 0:
                self.asks.pop(price, None)  # Remove the price level if it exists
            else:
                self.asks[price] = quantity

    def print_order_book(self):
        """Print the entire order book."""
        print("\n" + "="*50)
        print(f"Order Book for {self.symbol}")
        print("="*50)
        
        # Sort all asks (ascending order)
        sorted_asks = sorted(self.asks.items())
        print(f"\nAsks ({len(sorted_asks)} levels):")
        for price, qty in sorted_asks[::-1]:  # Print in descending order
            print(f"Price: {price:.2f}\tQuantity: {qty:.6f}")
            
        # Sort all bids (descending order)
        sorted_bids = sorted(self.bids.items(), reverse=True)
        print(f"\nBids ({len(sorted_bids)} levels):")
        for price, qty in sorted_bids:
            print(f"Price: {price:.2f}\tQuantity: {qty:.6f}")
        
        print("\nSpread:", end=" ")
        if sorted_asks and sorted_bids:
            spread = sorted_asks[0][0] - sorted_bids[0][0]
            print(f"{spread:.2f}")
        else:
            print("N/A")
        
        print(f"Total Levels: {len(sorted_asks) + len(sorted_bids)}")
        print("="*50)

    async def process_stream(self):
        """Process the websocket stream for order book updates."""
        while True:
            try:
                async with websockets.connect(
                    self.ws_url,
                    ping_interval=20,  # Send ping every 20 seconds
                    ping_timeout=10,   # Wait 10 seconds for pong response
                    close_timeout=10   # Wait 10 seconds for close response
                ) as websocket:
                    print("Connected to websocket stream")
                    while True:
                        msg = await websocket.recv()
                        data = json.loads(msg)
                        event = data['data']

                        # Check if we need to drop this event
                        if event['u'] <= self.last_update_id:
                            continue

                        # For first processed event after snapshot
                        if self.previous_final_update_id is None:
                            if not (event['U'] <= self.last_update_id + 1 <= event['u']):
                                print("Out of sync, reinitializing...")
                                await self.get_snapshot()
                                continue
                        else:
                            # Check if event is properly sequenced
                            if event['pu'] != self.previous_final_update_id:
                                print("Out of sync, reinitializing...")
                                await self.get_snapshot()
                                continue

                        # Update the order book
                        self.update_order_book(event['b'], event['a'])
                        self.previous_final_update_id = event['u']
                        
                        # Print the updated order book
                        self.print_order_book()
                        
                        # Add a small delay to make the output readable
                        await asyncio.sleep(1)

            except websockets.exceptions.ConnectionClosed as e:
                print(f"Connection closed ({e}). Reconnecting...")
                self.previous_final_update_id = None  # Reset the update ID
                await asyncio.sleep(1)
            except Exception as e:
                print(f"Error: {e}")
                print("Reconnecting...")
                self.previous_final_update_id = None  # Reset the update ID
                await asyncio.sleep(1)
            # Add a small delay before reconnecting
            await asyncio.sleep(0.1)

async def main():
    manager = OrderBookManager("XMRUSDT")
    await manager.initialize()

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\nShutting down...")