import sys
import os
import base64
import requests
import ctypes
from PyQt6.QtWidgets import (QApplication, QLabel, QMainWindow, QVBoxLayout, 
                             QWidget, QPushButton, QStackedWidget, QLineEdit)
from PyQt6.QtGui import QPixmap, QImage, QIcon, QPainter, QColor, QPen, QBrush
from PyQt6.QtCore import Qt, QThread, pyqtSignal, QPointF

# Fix for Windows Taskbar Icon
try:
    myappid = 'vision.system.tracker.v1'
    ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(myappid)
except Exception:
    pass

class StreamWorker(QThread):
    frame_received = pyqtSignal(QPixmap, float, float)
    error_occurred = pyqtSignal(str)

    def __init__(self, ip, port):
        super().__init__()
        self.base_url = f"http://{ip}:{port}"
        self.running = True

    def run(self):
        while self.running:
            try:
                # 1. Fetch Position
                pos_resp = requests.get(f"{self.base_url}/position", timeout=0.8)
                pos_resp.raise_for_status()
                pos_data = pos_resp.json()
                curr_x = float(pos_data.get("position_x", 0.0))
                curr_y = float(pos_data.get("position_y", 0.0))

                # 2. Fetch Image
                img_resp = requests.get(f"{self.base_url}/image", timeout=0.8)
                img_resp.raise_for_status()
                img_json = img_resp.json()
                
                base64_string = img_json.get("base64")
                if base64_string:
                    image_bytes = base64.b64decode(base64_string)
                    qimage = QImage.fromData(image_bytes)
                    if not qimage.isNull():
                        pixmap = QPixmap.fromImage(qimage)
                        self.frame_received.emit(pixmap, curr_x, curr_y)
                self.msleep(100) 
            except Exception as e:
                self.error_occurred.emit(f"Stream Error: {str(e)}")
                self.msleep(500)

    def stop(self):
        self.running = False

class ImageApp(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Vision Tracker")
        self.resize(800, 700)
        self.setStyleSheet("QMainWindow { background-color: #121212; }")
        
        self.last_pixmap = None  
        self.set_app_icon() # Load icon.png

        self.stacked_widget = QStackedWidget()
        self.setCentralWidget(self.stacked_widget)
        
        self.setup_home_page()
        self.setup_image_page()

    def set_app_icon(self):
        """Finds and sets the application icon."""
        app_dir = os.path.dirname(os.path.abspath(__file__))
        icon_path = os.path.join(app_dir, "icon.png")
        
        if os.path.exists(icon_path):
            app_icon = QIcon(icon_path)
            self.setWindowIcon(app_icon)
            # Set for the whole app (helps with certain OS menus)
            QApplication.setWindowIcon(app_icon)
        else:
            print(f"Warning: icon.png not found in {app_dir}")

    def setup_home_page(self):
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setAlignment(Qt.AlignmentFlag.AlignCenter)
        page.setStyleSheet("color: white; font-size: 14px;")

        self.ip_input = QLineEdit("127.0.0.1")
        self.port_input = QLineEdit("8000")
        self.ip_input.setStyleSheet("color: black; background: white;")
        self.port_input.setStyleSheet("color: black; background: white;")
        
        self.run_button = QPushButton("START STREAM")
        self.run_button.setStyleSheet("""
            QPushButton {
                background-color: #2E7D32; 
                color: white; 
                font-weight: bold; 
                padding: 12px;
                border-radius: 4px;
            }
            QPushButton:hover {
                background-color: #388E3C;
            }
        """)
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
        
        self.stop_button = QPushButton("STOP STREAM")
        self.stop_button.setStyleSheet("background-color: #C62828; color: white; font-weight: bold; padding: 10px;")
        self.stop_button.clicked.connect(self.stop_stream)

        self.image_display = QLabel("Connecting...")
        self.image_display.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.image_display.setMinimumSize(1, 1) # Allows shrinking
        self.image_display.setSizePolicy(self.image_display.sizePolicy().Policy.Expanding, 
                                         self.image_display.sizePolicy().Policy.Expanding)

        self.coord_label = QLabel("Position X: 0.00\nPosition Y: 0.00")
        self.coord_label.setAlignment(Qt.AlignmentFlag.AlignLeft)
        self.coord_label.setStyleSheet("""
            color: white; 
            font-family: monospace; 
            font-size: 16px; 
            font-weight: bold; 
            margin-left: 10px; 
            margin-bottom: 10px;
        """)

        layout.addWidget(self.stop_button)
        layout.addWidget(self.image_display, 1) 
        layout.addWidget(self.coord_label)
        self.stacked_widget.addWidget(page)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        if self.last_pixmap:
            self.display_pixmap(self.last_pixmap)

    def start_stream(self):
        self.stacked_widget.setCurrentIndex(1)
        self.worker = StreamWorker(self.ip_input.text().strip(), self.port_input.text().strip())
        self.worker.frame_received.connect(self.update_ui)
        self.worker.error_occurred.connect(lambda msg: self.image_display.setText(msg))
        self.worker.start()

    def update_ui(self, pixmap, x, y):
        self.coord_label.setText(f"Position X: {x:.2f}\nPosition Y: {y:.2f}")

        # Paint the red dot with white outline
        painter = QPainter(pixmap)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setBrush(QBrush(QColor(255, 0, 0)))
        painter.setPen(QPen(QColor(255, 255, 255), 2))
        painter.drawEllipse(QPointF(x, y), 8, 8)
        painter.end()

        self.last_pixmap = pixmap 
        self.display_pixmap(pixmap)

    def display_pixmap(self, pixmap):
        if not pixmap.isNull():
            self.image_display.setPixmap(pixmap.scaled(
                self.image_display.size(),
                Qt.AspectRatioMode.KeepAspectRatio,
                Qt.TransformationMode.SmoothTransformation
            ))

    def stop_stream(self):
        if hasattr(self, 'worker') and self.worker:
            self.worker.stop()
            self.worker.wait()
        self.last_pixmap = None
        self.stacked_widget.setCurrentIndex(0)

if __name__ == "__main__":
    app = QApplication(sys.argv)
    window = ImageApp()
    window.show()
    sys.exit(app.exec())