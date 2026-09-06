"""Local Qt components adapted from Caleb's Dashboard settings (989db03).

Reused with the owner's permission under PronounceIt's MIT license. Components
take their palette from the owning PronounceIt window, never another add-on.
"""
from __future__ import annotations

from aqt.qt import (
    QApplication, QBrush, QColor, QEvent, QFont, QGridLayout, QHBoxLayout,
    QLabel, QPainter, QPen, QPushButton, QSize, QSizePolicy, QSlider,
    QTimer, Qt, QVBoxLayout, QWidget,
)

from .theme import theme_tokens


def surface(role: str = "") -> QWidget:
    widget = QWidget()
    widget.setProperty("role", role)
    widget.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
    widget.setMinimumWidth(0)
    return widget


def apply_fonts(root: QWidget) -> None:
    base = QApplication.font()
    sizes = {"page_title": (20, True), "brand": (16, True), "title": (18, True),
             "section": (13, True), "secondary": (12, False), "pronunciation": (20, True)}
    root.setFont(base)
    for widget in root.findChildren(QWidget):
        size, bold = sizes.get(widget.property("role"), (13, False))
        font = QFont(base)
        if font.pixelSize() > 0:
            font.setPixelSize(max(1, round(font.pixelSize() * size / 13)))
        elif font.pointSizeF() > 0:
            font.setPointSizeF(font.pointSizeF() * size / 13)
        if bold:
            font.setWeight(QFont.Weight.DemiBold)
        widget.setFont(font)


def label(text: str = "", role: str = "") -> QLabel:
    result = QLabel(text)
    result.setTextFormat(Qt.TextFormat.PlainText)
    result.setWordWrap(True)
    result.setMinimumWidth(0)
    result.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
    result.setProperty("role", role)
    result.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
    return result


def button(text: str, callback=None, role: str = "") -> QPushButton:
    result = QPushButton(text)
    result.setProperty("role", role)
    result.setAutoDefault(False)
    result.setCursor(Qt.CursorShape.PointingHandCursor)
    if callback:
        result.clicked.connect(lambda _checked=False: callback())
    return result


def status(target: QLabel, text: str, error: bool = False, tone: str = "") -> None:
    role = tone or ("error" if error else "success")
    target.setText(text)
    if target.property("role") != role:
        target.setProperty("role", role)
        target.style().unpolish(target)
        target.style().polish(target)
    target.setVisible(bool(text))


def column(role: str = "") -> tuple[QWidget, QVBoxLayout]:
    widget = surface(role)
    layout = QVBoxLayout(widget)
    layout.setContentsMargins(0, 0, 0, 0)
    layout.setSpacing(8)
    return widget, layout


def field(layout: QVBoxLayout, text: str, widget: QWidget, help_text: str = "") -> None:
    container, body = column()
    title = label(text)
    title.setBuddy(widget)
    body.addWidget(title)
    widget.setAccessibleName(text)
    widget.setAccessibleDescription(help_text)
    body.addWidget(widget)
    if help_text:
        body.addWidget(label(help_text, "secondary"))
    layout.addWidget(container)


class Disclosure(QPushButton):
    def __init__(self, title: str, content: QWidget):
        super().__init__("▸  " + title)
        self.setProperty("role", "disclosure")
        self.setAccessibleName(title)
        self.setAutoDefault(False)
        self.setCheckable(True)
        self.content = content
        content.hide()
        self.toggled.connect(lambda opened: self.expand(title, opened))

    def expand(self, title: str, opened: bool) -> None:
        self.content.setVisible(opened)
        self.setText(("▾  " if opened else "▸  ") + title)


def disclosure(layout: QVBoxLayout, title: str, widget: QWidget) -> Disclosure:
    toggle = Disclosure(title, widget)
    layout.addWidget(toggle)
    layout.addWidget(widget)
    return toggle


class SettingsSwitch(QPushButton):
    """Dashboard's positional switch with a native checkable-button contract."""
    def __init__(self, title: str, description: str = ""):
        super().__init__()
        self.setProperty("role", "switch")
        self.setAutoDefault(False)
        self.setCheckable(True)
        self.setFixedSize(44, 34)
        self.setAccessibleName(title)
        self.setAccessibleDescription(description)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.toggled.connect(self._changed)
        self._changed(False)

    def _changed(self, checked: bool) -> None:
        self.setToolTip("On" if checked else "Off")
        self.update()

    def paintEvent(self, event) -> None:
        t = theme_tokens(getattr(self.window(), "theme", "light"))
        checked, enabled = self.isChecked(), self.isEnabled()
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        track = t.accent if checked and enabled else t.field_bg
        painter.setPen(QPen(QColor(t.accent if checked and enabled else t.field_border), 1.2))
        painter.setBrush(QBrush(QColor(track)))
        painter.drawRoundedRect(5, 9, 34, 18, 9, 9)
        painter.setPen(QPen(Qt.PenStyle.NoPen))
        painter.setBrush(QBrush(QColor(t.disabled_text if not enabled else t.accent_text if checked else t.primary_text)))
        painter.drawEllipse(22 if checked else 7, 11, 14, 14)
        if self.hasFocus():
            painter.setPen(QPen(QColor(t.focus_border), 3))
            painter.setBrush(QBrush(Qt.BrushStyle.NoBrush))
            painter.drawRoundedRect(2, 2, 40, 30, 7, 7)


class FieldRow(QWidget):
    """Keep labels and help together; move long fields below on narrow rows."""
    def __init__(self, title: str, control: QWidget, description: str = "", stack_below: int = 0):
        super().__init__()
        self.setMinimumWidth(0)
        self.copy, body = column()
        body.setSpacing(2)
        self.title = label(title)
        self.title.setBuddy(control)
        self.help = label(description, "secondary")
        body.addWidget(self.title)
        body.addWidget(self.help)
        # Adopt the label before showing it. A parentless visible label becomes
        # a native window and can pull macOS out of Anki's full-screen Space.
        self.help.setVisible(bool(description))
        self.control = control
        control.setAccessibleName(title)
        control.setAccessibleDescription(description)
        self.stack_below = stack_below
        self.grid = QGridLayout(self)
        self.grid.setContentsMargins(0, 2, 0, 2)
        self.grid.setHorizontalSpacing(16)
        self.grid.setVerticalSpacing(8)
        self.grid.setColumnStretch(0, 1)
        self._stacked = None
        self.arrange(False)

    def arrange(self, stacked: bool) -> None:
        if stacked == self._stacked:
            return
        self._stacked = stacked
        self.grid.removeWidget(self.copy)
        self.grid.removeWidget(self.control)
        self.grid.addWidget(self.copy, 0, 0, 1, 2 if stacked else 1)
        self.grid.addWidget(self.control, 1 if stacked else 0, 0 if stacked else 1,
                            1, 2 if stacked else 1,
                            Qt.AlignmentFlag.AlignLeft if stacked else Qt.AlignmentFlag.AlignVCenter)

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        self.arrange(bool(self.stack_below and self.width() < self.stack_below))


class SettingsCard(QWidget):
    def __init__(self, title: str, description: str = ""):
        super().__init__()
        self.setProperty("role", "card")
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self.setMinimumWidth(0)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Maximum)
        self.body = QVBoxLayout(self)
        self.body.setContentsMargins(16, 16, 16, 16)
        self.body.setSpacing(12)
        if title:
            self.body.addWidget(label(title, "section"))
        if description:
            self.body.addWidget(label(description, "secondary"))


class CardGrid(QWidget):
    def __init__(self, *cards: QWidget):
        super().__init__()
        self.setMinimumWidth(0)
        self.cards = cards
        self.grid = QGridLayout(self)
        self.grid.setContentsMargins(0, 0, 0, 0)
        self.grid.setSpacing(16)
        self._wide = None
        self.arrange(False)

    def arrange(self, wide: bool) -> None:
        if self._wide == wide:
            return
        self._wide = wide
        for card in self.cards:
            self.grid.removeWidget(card)
        self.grid.setColumnStretch(0, 1)
        self.grid.setColumnStretch(1, 1 if wide else 0)
        for i, card in enumerate(self.cards):
            self.grid.addWidget(card, i // 2 if wide else i, i % 2 if wide else 0,
                                Qt.AlignmentFlag.AlignTop)

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        self.arrange(self.width() >= max(760, self.fontMetrics().horizontalAdvance("M") * 76))


class ValueSlider(QWidget):
    def __init__(self, name: str, low: int, high: int, formatter, markers=()):
        super().__init__()
        self.setMinimumWidth(0)
        self.slider = QSlider(Qt.Orientation.Horizontal)
        self.slider.setRange(low, high)
        self.slider.setMinimumHeight(34)
        self.slider.setAccessibleName(name)
        self.readout = label()
        self.readout.setWordWrap(False)
        self.readout.setAlignment(Qt.AlignmentFlag.AlignRight)
        body = QVBoxLayout(self)
        body.setContentsMargins(0, 0, 0, 0)
        body.setSpacing(4)
        row = QHBoxLayout()
        row.addWidget(label(name), 1)
        row.addWidget(self.readout)
        body.addLayout(row)
        body.addWidget(self.slider)
        if markers:
            scale = QHBoxLayout()
            for i, text in enumerate(markers):
                if i:
                    scale.addStretch()
                scale.addWidget(label(text, "secondary"))
            body.addLayout(scale)
        self.slider.valueChanged.connect(lambda value: self.readout.setText(formatter(value)))
        self.readout.setText(formatter(low))


class ActivityIndicator(QWidget):
    def __init__(self):
        super().__init__()
        self.setFixedSize(18, 18)
        self.angle = 0
        self.timer = QTimer(self)
        self.timer.setInterval(90)
        self.timer.timeout.connect(self.advance)

    def advance(self):
        self.angle = (self.angle + 30) % 360
        self.update()

    def showEvent(self, event):
        super().showEvent(event)
        self.timer.start()

    def hideEvent(self, event):
        self.timer.stop()
        super().hideEvent(event)

    def paintEvent(self, event):
        t = theme_tokens(getattr(self.window(), "theme", "light"))
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        painter.setPen(QPen(QColor(t.card_border), 2))
        painter.drawEllipse(3, 3, 12, 12)
        painter.setPen(QPen(QColor(t.accent), 2))
        painter.drawArc(3, 3, 12, 12, -self.angle * 16, 110 * 16)
