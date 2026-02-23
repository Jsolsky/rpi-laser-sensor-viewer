import sys
import base64
import requests
from PyQt6.QtWidgets import (QApplication, QLabel, QMainWindow, QVBoxLayout, 
                             QWidget, QPushButton, QStackedWidget, QLineEdit)
from PyQt6.QtGui import QPixmap, QImage
from PyQt6.QtCore import Qt, QThread, pyqtSignal

class StreamWorker(QThread):
    """Handles the network requests in the background."""
    frame_received = pyqtSignal(QPixmap)
    error_occurred = pyqtSignal(str)

    def __init__(self, ip, port):
        super().__init__()
        self.url = f"http://{ip}:{port}/image"
        self.running = True

    def run(self):
        while self.running:
            try:
                # Short timeout to keep the loop snappy
                response = requests.get(self.url, timeout=1)
                response.raise_for_status()
                
                data = response.json()
                base64_string = data.get("base64")

                if base64_string:
                    image_bytes = base64.b64decode(base64_string)
                    qimage = QImage.fromData(image_bytes)
                    
                    if not qimage.isNull():
                        pixmap = QPixmap.fromImage(qimage)
                        self.frame_received.emit(pixmap)
                
                self.msleep(100)  # Wait 0.1 seconds before next request
            except Exception as e:
                self.error_occurred.emit(f"Connection Error: {str(e)}")
                self.msleep(1000) # Wait longer on error to avoid spamming

    def stop(self):
        self.running = False

class ImageApp(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Live Device Stream (/image)")
        self.resize(700, 600)

        self.stacked_widget = QStackedWidget()
        self.setCentralWidget(self.stacked_widget)
        
        self.worker = None
        self.setup_home_page()
        self.setup_image_page()

    def setup_home_page(self):
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setAlignment(Qt.AlignmentFlag.AlignCenter)

        self.ip_input = QLineEdit("127.0.0.1")
        self.port_input = QLineEdit("8000")
        self.run_button = QPushButton("START STREAM")
        self.run_button.setStyleSheet("padding: 10px; font-weight: bold; background-color: #4CAF50; color: white;")
        self.run_button.clicked.connect(self.start_stream)

        layout.addWidget(QLabel("Device IP:"))
        layout.addWidget(self.ip_input)
        layout.addWidget(QLabel("Port:"))
        layout.addWidget(self.port_input)
        layout.addWidget(self.run_button)
        self.stacked_widget.addWidget(page)

    def setup_image_page(self):
        page = QWidget()
        layout = QVBoxLayout(page)
        self.stop_button = QPushButton("STOP STREAM")
        self.stop_button.setStyleSheet("background-color: red; color: white; font-weight: bold; padding: 10px;")
        self.stop_button.clicked.connect(self.stop_stream)
        self.image_display = QLabel("Initializing stream...")
        self.image_display.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(self.stop_button)
        layout.addWidget(self.image_display)
        self.stacked_widget.addWidget(page)

    def start_stream(self):
        ip = self.ip_input.text().strip()
        port = self.port_input.text().strip()
        
        self.stacked_widget.setCurrentIndex(1)
        
        # Start background thread
        self.worker = StreamWorker(ip, port)
        self.worker.frame_received.connect(self.update_image)
        self.worker.error_occurred.connect(lambda msg: self.image_display.setText(msg))
        self.worker.start()

    def update_image(self, pixmap):
        """Update the label with the new frame scaled to window size."""
        self.image_display.setPixmap(pixmap.scaled(
            self.image_display.size(),
            Qt.AspectRatioMode.KeepAspectRatio,
            Qt.TransformationMode.SmoothTransformation
        ))

    def stop_stream(self):
        if self.worker:
            self.worker.stop()
            self.worker.wait() # Ensure thread finishes
        self.stacked_widget.setCurrentIndex(0)

if __name__ == "__main__":
    app = QApplication(sys.argv)
    window = ImageApp()
    window.show()
    sys.exit(app.exec())