# splash.py

from PyQt6.QtWidgets import QWidget, QLabel, QVBoxLayout
from PyQt6.QtCore import Qt
from PyQt6.QtGui import QPixmap, QFont, QPainter

from utils import resource_path


class SplashScreen(QWidget):
    """Rahmenloses, transparentes Splash-Fenster mit Build-Info."""

    def __init__(self, build_info: str, parent=None) -> None:
        super().__init__(
            parent,
            Qt.WindowType.Window
            | Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.WindowStaysOnTopHint,
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose)
        self.build_info = build_info
        self._build_ui()

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        pix = QPixmap(str(resource_path("assets/splash.png")))
        self.splash_label = QLabel()
        self.splash_label.setPixmap(pix)
        self.splash_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(self.splash_label)

        self.info_label = RotatedLabel(self.build_info, angle=-1.5, parent=self)
        self.info_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.info_label.setFont(QFont("Segoe UI", 15, QFont.Weight.Bold))
        self.info_label.setStyleSheet("color: black; background: transparent;")
        self.info_label.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)

        self.resize(pix.width(), pix.height())

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        self.info_label.setGeometry(-100, self.height() - 300, self.width(), 90)

    def mousePressEvent(self, event) -> None:
        self.close()

    def show_centered(self, parent: QWidget) -> None:
        geo = parent.geometry()
        x = geo.x() + (geo.width() - self.width()) // 2
        y = geo.y() + (geo.height() - self.height()) // 2 - 100
        self.move(x, y)
        self.show()


class RotatedLabel(QLabel):
    def __init__(self, text: str, angle: float = 0, parent=None):
        super().__init__(text, parent)
        self.angle = angle

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        painter.translate(self.width() / 2, self.height() / 2)
        painter.rotate(self.angle)
        painter.translate(-self.width() / 2, -self.height() / 2)

        painter.setFont(self.font())
        painter.setPen(self.palette().color(self.foregroundRole()))
        painter.drawText(self.rect(), self.alignment(), self.text())
