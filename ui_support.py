"""Small reusable desktop components; no transcription dependencies."""
from pathlib import Path
from PySide6.QtCore import Signal, Qt
from PySide6.QtWidgets import QFrame, QVBoxLayout, QLabel, QPushButton, QWidget

from core import AUDIO_EXTENSIONS

STYLE = """
QWidget { color: #22342e; font-family: 'Segoe UI', 'Malgun Gothic', 'Noto Sans CJK KR', sans-serif; font-size: 14px; font-weight: 400; }
QWidget#window { background: #f4f6f3; }
QLabel#brand { font-size: 25px; font-weight: 700; }
QLabel#muted { color: #64776d; }
QLabel#sectionTitle { font-size: 19px; font-weight: 600; }
QLabel#status { font-weight: 600; color: #25654b; }
QGroupBox { background: white; border: 1px solid #dce4de; border-radius: 12px; margin-top: 14px; padding: 18px 14px 12px; font-weight: 600; }
QGroupBox::title { subcontrol-origin: margin; left: 14px; padding: 0 5px; }
QLineEdit, QComboBox, QSpinBox { background: #ffffff; border: 1px solid #cad6ce; border-radius: 7px; padding: 8px; min-height: 18px; selection-background-color: #d8ebdf; }
QLineEdit:focus, QComboBox:focus, QSpinBox:focus { border: 1px solid #318360; }
QComboBox QAbstractItemView { background: white; selection-background-color: #d8ebdf; color: #22342e; }
QPushButton { background: #ffffff; border: 1px solid #cad6ce; border-radius: 7px; padding: 9px 14px; font-weight: 600; }
QPushButton:hover { background: #edf4ee; border-color: #75a78b; }
QPushButton#primary { background: #286b4e; color: white; border: 1px solid #286b4e; padding: 11px 20px; }
QPushButton#primary:hover { background: #1d593e; }
QPushButton:disabled { background: #edf0ed; color: #919c94; border-color: #e0e5e0; }
QPushButton#disclosure { text-align: left; background: transparent; border: 0; padding: 8px 0; color: #466853; }
QTabWidget::pane { border: 0; }
QTabBar::tab { padding: 10px 18px; margin: 0 4px 10px 0; border-radius: 7px; color: #62766a; }
QTabBar::tab:selected { background: #dfece2; color: #23523b; font-weight: 600; }
QTabBar::tab:hover { background: #e9f0e9; }
QTextEdit, QPlainTextEdit, QListWidget { background: white; border: 1px solid #dce4de; border-radius: 9px; padding: 10px; selection-background-color: #d8ebdf; }
QListWidget::item { padding: 8px; border-radius: 5px; }
QListWidget::item:selected { background: #dfece2; color: #22342e; }
QProgressBar { border: 0; border-radius: 4px; background: #e0e8e1; min-height: 7px; max-height: 7px; }
QProgressBar::chunk { border-radius: 4px; background: #38875f; }
QCheckBox { spacing: 7px; padding: 3px 0; }
QScrollArea { border: 0; background: transparent; }
QScrollArea > QWidget > QWidget { background: transparent; }
QSplitter::handle { background: transparent; width: 16px; }
QFrame#drop { background: #edf5ee; border: 1px dashed #83aa91; border-radius: 12px; }
"""

class DropZone(QFrame):
    file_selected = Signal(str)

    def __init__(self, extensions, title, detail, browse, parent=None):
        super().__init__(parent)
        self.extensions = extensions
        self.setObjectName('drop')
        self.setAcceptDrops(True)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 12, 16, 12)
        self.title = QLabel(title)
        self.title.setAlignment(Qt.AlignCenter)
        self.title.setWordWrap(True)
        self.title.setStyleSheet('font-size: 16px; font-weight: 600;')
        hint = QLabel(detail)
        hint.setObjectName('muted')
        hint.setAlignment(Qt.AlignCenter)
        hint.setWordWrap(True)
        button = QPushButton('파일 선택…')
        button.clicked.connect(browse)
        layout.addWidget(self.title)
        layout.addWidget(hint)
        layout.addSpacing(6)
        layout.addWidget(button, alignment=Qt.AlignCenter)

    def local_file(self, mime):
        urls = mime.urls()
        if len(urls) != 1 or not urls[0].isLocalFile():
            return None
        path = Path(urls[0].toLocalFile())
        return str(path) if path.is_file() and path.suffix.lower() in self.extensions else None

    def dragEnterEvent(self, event):
        if self.local_file(event.mimeData()):
            event.acceptProposedAction()

    def dropEvent(self, event):
        path = self.local_file(event.mimeData())
        if path:
            self.file_selected.emit(path)
            event.acceptProposedAction()

class Disclosure(QWidget):
    def __init__(self, title, content):
        super().__init__()
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        self.button = QPushButton('＋  ' + title)
        self.button.setObjectName('disclosure')
        self.button.setCheckable(True)
        content.setVisible(False)
        self.button.toggled.connect(content.setVisible)
        self.button.toggled.connect(lambda opened: self.button.setText(('−  ' if opened else '＋  ') + title))
        layout.addWidget(self.button)
        layout.addWidget(content)
