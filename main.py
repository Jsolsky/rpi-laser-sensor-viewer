import sys
import os
import base64
import requests
import ctypes
from PyQt6.QtWidgets import (QApplication, QLabel, QMainWindow, QVBoxLayout, 
                             QWidget, QPushButton, QStackedWidget, QLineEdit, QHBoxLayout, QSizePolicy)
from PyQt6.QtGui import QPixmap, QImage, QPainter, QColor, QPen, QBrush, QIcon
from PyQt6.QtCore import Qt, QThread, pyqtSignal, QPointF

# Fix for Windows Taskbar Icon (Grouping)
try:
    myappid = 'vision.system.tracker.v2'
    ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(myappid)
except Exception:
    pass

class StreamWorker(QThread):
    frame_received = pyqtSignal(QPixmap, dict)
    error_occurred = pyqtSignal(str)

    def __init__(self, ip, port):
        super().__init__()
        self.base_url = f"http://{ip}:{port}"
        self.running = True
        self.mode = "single" 

    def run(self):
        while self.running:
            pos_data = {}
            
            # --- 1. ATTEMPT POSITION FETCH (Isolated) ---
            try:
                endpoint = "/position_grid_full" if self.mode == "grid" else "/position"
                current_timeout = 2.0 if self.mode == "grid" else 0.8

                pos_resp = requests.get(f"{self.base_url}{endpoint}", timeout=current_timeout)
                pos_resp.raise_for_status()
                pos_data = pos_resp.json()
            except Exception as e:
                pos_data = {"_network_error": True}

            # --- 2. ATTEMPT IMAGE FETCH ---
            try:
                img_resp = requests.get(f"{self.base_url}/image", timeout=1.0)
                img_resp.raise_for_status()
                img_json = img_resp.json()
                
                base64_string = img_json.get("base64")
                if base64_string:
                    image_bytes = base64.b64decode(base64_string)
                    qimage = QImage.fromData(image_bytes)
                    
                    if not qimage.isNull():
                        pixmap = QPixmap.fromImage(qimage)
                        self.frame_received.emit(pixmap, pos_data)
                
                self.msleep(30) 
                
            except Exception as e:
                self.error_occurred.emit(f"Stream Connection Lost: {str(e)}")
                self.msleep(1000)

    def stop(self):
        self.running = False

class ImageApp(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Vision Tracker Pro")
        self.resize(900, 800)
        self.setMinimumSize(600, 500)
        self.setStyleSheet("QMainWindow { background-color: #121212; }")
        
        # --- SET APP ICON ---
        icon_path = os.path.join(os.path.dirname(__file__), "icon.png")
        if os.path.exists(icon_path):
            self.setWindowIcon(QIcon(icon_path))
        
        self.last_pixmap = None  
        self.last_data = {}

        self.stacked_widget = QStackedWidget()
        self.setCentralWidget(self.stacked_widget)
        
        self.setup_home_page()
        self.setup_image_page()

    def setup_home_page(self):
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setAlignment(Qt.AlignmentFlag.AlignCenter)
        page.setStyleSheet("color: white; font-size: 14px;")

        self.ip_input = QLineEdit("127.0.0.1")
        self.port_input = QLineEdit("8000")
        for inp in [self.ip_input, self.port_input]:
            inp.setStyleSheet("color: black; background: white; padding: 5px; margin-bottom: 10px;")
        
        self.run_button = QPushButton("START SYSTEM")
        self.run_button.setStyleSheet("background-color: #2E7D32; color: white; font-weight: bold; padding: 15px;")
        self.run_button.clicked.connect(self.start_stream)

        layout.addWidget(QLabel("<b>Device IP:</b>"))
        layout.addWidget(self.ip_input)
        layout.addWidget(QLabel("<b>Port:</b>"))
        layout.addWidget(self.port_input)
        layout.addWidget(self.run_button)
        self.stacked_widget.addWidget(page)

    def setup_image_page(self):
        page = QWidget()
        layout = QVBoxLayout(page)
        
        ctrl_layout = QHBoxLayout()
        self.mode_button = QPushButton("MODE: SINGLE BEAM")
        self.mode_button.setStyleSheet("background-color: #1976D2; color: white; font-weight: bold; padding: 8px;")
        self.mode_button.clicked.connect(self.toggle_mode)

        self.stop_button = QPushButton("STOP")
        self.stop_button.setStyleSheet("background-color: #C62828; color: white; font-weight: bold; padding: 8px;")
        self.stop_button.clicked.connect(self.stop_stream)

        ctrl_layout.addWidget(self.mode_button)
        ctrl_layout.addWidget(self.stop_button)

        self.image_display = QLabel("Waiting for data...")
        self.image_display.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.image_display.setStyleSheet("background-color: #000; border: 1px solid #333;")
        self.image_display.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Ignored)
        self.image_display.setMinimumSize(100, 100) 

        self.coord_label = QLabel("X: 0.00 | Y: 0.00")
        self.coord_label.setStyleSheet("color: #00FF00; font-family: monospace; font-size: 14px; padding: 5px;")

        layout.addLayout(ctrl_layout)
        layout.addWidget(self.image_display, stretch=1)
        layout.addWidget(self.coord_label)
        self.stacked_widget.addWidget(page)

    def toggle_mode(self):
        if hasattr(self, 'worker'):
            if self.worker.mode == "single":
                self.worker.mode = "grid"
                self.mode_button.setText("MODE: FULL GRID")
            else:
                self.worker.mode = "single"
                self.mode_button.setText("MODE: SINGLE BEAM")

    def start_stream(self):
        self.stacked_widget.setCurrentIndex(1)
        self.worker = StreamWorker(self.ip_input.text().strip(), self.port_input.text().strip())
        self.worker.frame_received.connect(self.update_ui)
        self.worker.error_occurred.connect(lambda msg: self.image_display.setText(msg))
        self.worker.start()

    def update_ui(self, pixmap, data):
        self.last_pixmap = pixmap
        self.last_data = data
        
        painter = QPainter(pixmap)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        
        if data.get("_network_error"):
            self.coord_label.setText("STATUS: TELEMETRY OFFLINE")
        else:
            x = data.get("position_x")
            y = data.get("position_y")

            if x is None or y is None:
                self.coord_label.setText("STATUS: SEARCHING... (No Beam)")
            else:
                if self.worker.mode == "grid":
                    grid_pen = QPen(QColor(0, 255, 255, 180), 2, Qt.PenStyle.DashLine)
                    painter.setPen(grid_pen)
                    mv, cv = data.get("vertical_line_gradient"), data.get("vertical_line_intercept")
                    mh, ch = data.get("horizontal_line_gradient"), data.get("horizontal_line_intercept")
                    
                    if all(v is not None for v in [mv, cv]):
                        painter.drawLine(QPointF(0, cv), QPointF(pixmap.width(), mv * pixmap.width() + cv))
                    if all(v is not None for v in [mh, ch]):
                        painter.drawLine(QPointF(0, ch), QPointF(pixmap.width(), mh * pixmap.width() + ch))

                painter.setBrush(QBrush(QColor(255, 0, 0)))
                painter.setPen(QPen(QColor(255, 255, 255), 2))
                painter.drawEllipse(QPointF(x, y), 8, 8)
                self.coord_label.setText(f"X: {x:.2f} | Y: {y:.2f} (Lock On)")
            
        painter.end()
        self.display_pixmap(pixmap)

    def display_pixmap(self, pixmap):
        if not pixmap.isNull():
            scaled = pixmap.scaled(
                self.image_display.size(),
                Qt.AspectRatioMode.KeepAspectRatio,
                Qt.TransformationMode.SmoothTransformation
            )
            self.image_display.setPixmap(scaled)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        if self.last_pixmap:
            self.display_pixmap(self.last_pixmap)

    def stop_stream(self):
        if hasattr(self, 'worker') and self.worker:
            self.worker.stop()
            self.worker.wait()
        self.stacked_widget.setCurrentIndex(0)

if __name__ == "__main__":
    app = QApplication(sys.argv)
    window = ImageApp()
    window.show()
    sys.exit(app.exec())