import sys
from PyQt5.QtWidgets import QApplication, QMainWindow, QWidget, QVBoxLayout, QPushButton, QComboBox, QFileDialog, QLabel, QHBoxLayout
import pyqtgraph as pg
import pandas as pd
import numpy as np
from collections import defaultdict
from pyqtgraph.Qt import QtWidgets, QtGui, QtCore
from PyQt5.QtWidgets import QToolTip
from PyQt5.QtCore import QTimer
from PyQt5.QtCore import QThread, pyqtSignal
from pyqtgraph.Qt import QtGui



class DataWorker(QThread):
    # will emit a dict of drawing instructions back to the GUI
    data_ready = pyqtSignal(object)

    def __init__(self, file_path, freq, bin_size, candle_width, x_spacing, parent=None):
        super().__init__(parent)
        self.file_path    = file_path
        self.freq         = freq
        self.bin_size     = bin_size
        self.candle_width = candle_width
        self.x_spacing    = x_spacing

    def run(self):
        import pandas as pd
        from collections import defaultdict

        # 1) Read & bucket
        df = pd.read_csv(self.file_path)

        # drop any rows with price <= 0 or quantity <= 0
        df = df.loc[(df["price"] > 0) & (df["quantity"] > 0)]
        df["timestamp"] = pd.to_datetime(df["timestamp_ms"], unit='ms')
        df["timestamp"] = pd.to_datetime(df["timestamp_ms"], unit='ms')
        df.set_index("timestamp", inplace=True)
        df["bucket"] = df.index.floor(self.freq)
        grouped = df.groupby("bucket")

        instr = []
        for idx, (ts, grp) in enumerate(grouped):
            x = idx * self.x_spacing
            o = grp.iloc[0]["price"]
            c = grp.iloc[-1]["price"]
            h = grp["price"].max()
            l = grp["price"].min()
            total_v = grp["quantity"].sum()

            # volume bins + POC
            volume_bins = defaultdict(lambda: {"buy":0.0, "sell":0.0, "buy_count":0, "sell_count":0})
            for _, r in grp.iterrows():
                pb = round(r["price"] / self.bin_size) * self.bin_size
                volume_bins[pb][r["side"]] += r["quantity"]
                volume_bins[pb][f"{r['side']}_count"] += 1
            totals = {pb: v["buy"]+v["sell"] for pb,v in volume_bins.items()}
            poc = max(totals, key=totals.get) if totals else None

            instr.append({
                "x": x, "open": o, "close": c, "high": h, "low": l,
                "total_vol": total_v, "vol_bins": volume_bins,
                "poc": poc, "timestamp": ts
            })

        # emit back to GUI
        self.data_ready.emit({
            "instructions": instr,
            "price_min": df["price"].min(),
            "price_max": df["price"].max(),
            "count": len(instr)
        })


class FootprintGUI(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Footprint Chart - XMRUSDT")
        self.setGeometry(100, 100, 1000, 550)
        self.current_file_path = None
        self.bin_size_map = {
                            "1m": 0.03,
                            "3m": 0.03,
                            "5m": 0.05,
                            "15m": 0.1,
                            "30m": 0.2,
                            "1h": 0.2,
                            "4h": 0.5
                        }

        # Central widget
        self.central_widget = QWidget()
        self.setCentralWidget(self.central_widget)

        # Main layout
        self.main_layout = QVBoxLayout()
        self.central_widget.setLayout(self.main_layout)

        # === Chart area ===
        self.plot_widget = pg.PlotWidget()
        self.plot_widget.showGrid(x=True, y=True)
        self.plot_widget.setLabel('left', 'Price')
        self.plot_widget.setLabel('bottom', 'Time')
        self.main_layout.addWidget(self.plot_widget)

        # === Control panel ===
        self.control_panel = QHBoxLayout()

        self.timeframe_dropdown = QComboBox()
        self.timeframe_dropdown.addItems(["1m", "3m", "5m", "15m", "30m", "1h", "4h"])
        self.control_panel.addWidget(QLabel("Timeframe:"))
        self.control_panel.addWidget(self.timeframe_dropdown)
        self.timeframe_dropdown.currentTextChanged.connect(self.on_timeframe_change)

        self.load_button = QPushButton("Load CSV")
        self.load_button.clicked.connect(self.load_csv)
        self.control_panel.addWidget(self.load_button)

        # Live-feed toggle
        self.live_button = QPushButton("Start Live Feed")
        self.control_panel.addWidget(self.live_button)

        # ➊ Create a QTimer but don’t start it yet
        self.timer = QTimer(self)
        self.timer.setInterval(1000)                    # poll every 1000 ms
        self.timer.timeout.connect(self._on_timer)      # call our handler

        # ➋ Hook the button up to start/stop the timer
        self.live_button.clicked.connect(self.toggle_live_feed)

        # placeholder for our background worker
        self.worker = None

        self.main_layout.addLayout(self.control_panel)

    def load_csv(self):
        file_path, _ = QFileDialog.getOpenFileName(self, "Open CSV File", "", "CSV files (*.csv)")
        if file_path:
            print(f"Loaded: {file_path}")
            self.current_file_path = file_path    # ← store for later
            self.load_and_plot_csv(file_path)

             # ➌ auto-start live updates on load
            self.timer.start()
            self.live_button.setText("Stop Live Feed")

    def _on_timer(self):
        """Called every interval—re-plot if we have a CSV loaded."""
        if self.current_file_path:
            self.load_and_plot_csv(self.current_file_path)

    def toggle_live_feed(self):
        """Start or stop the QTimer and update button text."""
        if self.timer.isActive():
            self.timer.stop()
            self.live_button.setText("Start Live Feed")
        else:
            if self.current_file_path:
                self.timer.start()
                self.live_button.setText("Stop Live Feed")


    def on_timeframe_change(self, new_tf: str):
        """Re-plot with whatever timeframe is selected."""
        if self.current_file_path:
            self.load_and_plot_csv(self.current_file_path)

    def load_and_plot_csv(self, file_path):
        try:
            df = pd.read_csv(file_path)
            
            # Determine bucket frequency & bin size from dropdown
            tf = self.timeframe_dropdown.currentText()
            freq = f"{int(tf[:-1])}min" if tf.endswith("m") else f"{int(tf[:-1])}H"
            bin_size     = self.bin_size_map.get(tf, 0.03)
            candle_width = 0.3
            x_spacing    = 1.5

            # Stop any previous worker
            if getattr(self, "worker", None) and self.worker.isRunning():
                self.worker.terminate()
                self.worker.wait()

            # Launch a new DataWorker thread
            self.worker = DataWorker(
                file_path, freq, bin_size, candle_width, x_spacing
            )
            self.worker.data_ready.connect(self.on_data_ready)
            self.worker.start()


                        

        except Exception as e:
            print(f"Error loading CSV: {e}")

    def on_data_ready(self, payload):
        """Receives precomputed drawing instructions from the worker."""
        instr   = payload["instructions"]
        pmin    = payload["price_min"] * 0.99
        pmax    = payload["price_max"] * 1.01
        count   = payload["count"]

        # Compute horizontal scale so text width shrinks/expands with zoom
        vb = self.plot_widget.getViewBox()
        dx, dy = vb.viewPixelSize()           # returns (dx, dy) in data‐units per pixel
        scale_x = 1.0 / dx                     # invert dx to get pixels per data‐unit


        # ── Highlight params ──
        tf = self.timeframe_dropdown.currentText()
        bin_size     = self.bin_size_map.get(tf, 0.03)
        candle_width = 0.3
        offset       = candle_width/2 + 0.01

        # Preserve or auto-scale view
        vb = self.plot_widget.getViewBox()
        prev_x, prev_y = vb.viewRange()

        # Clear & restyle
        self.plot_widget.clear()
        self.plot_widget.setBackground('w')
        self.plot_widget.showGrid(x=False, y=False, alpha=0.3)
        self.plot_widget.getAxis('left').setPen(pg.mkPen('black'))
        self.plot_widget.getAxis('bottom').setPen(pg.mkPen('black'))

        # Draw each candle + wick + POC + footprint text
        for data in instr:
            x = data["x"]
            o, c, h, l = data["open"], data["close"], data["high"], data["low"]
            color = 'g' if c>o else 'r'
            brush = pg.mkBrush(color)
            pen   = pg.mkPen(color, width=2)

            # Candle body
            rect = QtWidgets.QGraphicsRectItem(
                QtCore.QRectF(x-0.15, min(o,c), 0.3, abs(c-o))
            )
            rect.setPen(pen); rect.setBrush(brush)
            rect.setAcceptHoverEvents(True)
            rect.setToolTip((
                f"Time: {data['timestamp'].strftime('%Y-%m-%d %H:%M')}\n"
                f"Open: {o:.2f}  High: {h:.2f}\n"
                f"Low: {l:.2f}   Close: {c:.2f}\n"
                f"Vol:  {data['total_vol']:.2f}"
            ))
            self.plot_widget.addItem(rect)

            # Wick
            wick = pg.PlotDataItem(
                x=[x, x], y=[l, h], pen=pg.mkPen(color, width=2)
            )
            self.plot_widget.addItem(wick)

            # POC
            if data["poc"] is not None:
                poc_line = pg.PlotDataItem(
                    x=[x-0.15, x+0.15], y=[data["poc"], data["poc"]],
                    pen=pg.mkPen("purple", width=2)
                )
                self.plot_widget.addItem(poc_line)

                # ── Highlight the full text+ candle width at POC ──
                highlight = QtWidgets.QGraphicsRectItem(
                    QtCore.QRectF(
                x - candle_width/2 - offset,  # left of sell-text
                data["poc"] - bin_size/2,      # mid-bin vertically
                candle_width + offset*2,       # full candle + text width
                bin_size                        # one bin tall
             )
         )
                # semi‐transparent purple fill, no border
                highlight.setBrush(QtGui.QBrush(QtGui.QColor(128, 0, 128, 50)))
                highlight.setPen(QtGui.QPen(QtCore.Qt.NoPen))
                # draw behind text but above candle: give it a mid‐level z‐value
                highlight.setZValue(1)
                self.plot_widget.addItem(highlight)


            # Footprint text
            for pb, v in data["vol_bins"].items():
                if v["buy"] > 0:
                    buy_text = pg.TextItem()
                    buy_text.setHtml(
                        f"<span style='color:navy; font-weight:bold'>{v['buy']:.2f} ({v['buy_count']})</span>"
                    )
                    buy_text.setAnchor((0, 0.5))
                    # shrink/grow horizontally with zoom, keep vertical height
                    buy_text.setTransform(
                        QtGui.QTransform().scale(scale_x, 1.0),
                        False
                    )
                    buy_text.setPos(x + offset, pb)
                    self.plot_widget.addItem(buy_text)

                if v["sell"] > 0:
                    sell_text = pg.TextItem()
                    sell_text.setHtml(
                        f"<span style='color:black; font-weight:bold'>{v['sell']:.2f} ({v['sell_count']})</span>"
                    )
                    sell_text.setAnchor((1, 0.5))
                    # same horizontal scaling
                    sell_text.setTransform(
                        QtGui.QTransform().scale(scale_x, 1.0),
                        False
                    )
                    sell_text.setPos(x - offset, pb)
                    self.plot_widget.addItem(sell_text)

        # Rebuild custom ticks
        ticks = [(i*1.5, instr[i]["timestamp"].strftime("%H:%M")) for i in range(count)]
        ax = self.plot_widget.getAxis('bottom')
        ax.setTicks([ticks])

        # Restore or auto‐scale
        if self.timer.isActive():
            vb.setRange(xRange=prev_x, yRange=prev_y, padding=0)
        else:
            self.plot_widget.setXRange(-1, count*1.5)
            self.plot_widget.setYRange(pmin, pmax)

        print(f"Plotted {count} footprint candles from CSV.")






if __name__ == "__main__":
    app = QApplication(sys.argv)
    window = FootprintGUI()
    window.show()
    sys.exit(app.exec_())
