from PySide6.QtCore import QPropertyAnimation, QRectF, QSize, Qt, Signal
from PySide6.QtGui import QColor, QFont, QPainter, QPainterPath, QPen, QPixmap
from PySide6.QtWidgets import QFrame, QGraphicsDropShadowEffect, QGridLayout, QLabel, QVBoxLayout, QWidget

from app.services.books import cover_file
from app.ui import theme
from app.ui.common import breakable, label, rating_text, shorten


def placeholder_cover(width, height, title, author):
    palette = theme.palette()
    pixmap = QPixmap(width, height)
    pixmap.fill(QColor(palette["hover"]))
    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    margin = width * 0.09
    painter.setPen(QPen(QColor(palette["border"]), max(2, width // 120)))
    painter.drawRect(QRectF(margin / 2, margin / 2, width - margin, height - margin))
    painter.fillRect(QRectF(margin, height * 0.16, width * 0.22, max(3, width // 70)), QColor(palette["accent"]))
    flags = Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignTop | Qt.TextFlag.TextWordWrap
    painter.setPen(QColor(palette["text"]))
    painter.setFont(QFont(theme.SERIF, max(9, width // 13), QFont.Weight.Bold))
    painter.drawText(QRectF(margin, height * 0.22, width - 2 * margin, height * 0.55), flags, breakable(shorten(title, 60), 10))
    painter.setPen(QColor(palette["muted"]))
    painter.setFont(QFont(theme.SANS, max(7, width // 22)))
    painter.drawText(QRectF(margin, height * 0.8, width - 2 * margin, height * 0.12), flags, shorten(author, 40))
    painter.end()
    return pixmap


def rounded(pixmap, radius):
    result = QPixmap(pixmap.size())
    result.fill(Qt.GlobalColor.transparent)
    painter = QPainter(result)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    path = QPainterPath()
    path.addRoundedRect(QRectF(pixmap.rect()), radius, radius)
    painter.setClipPath(path)
    painter.drawPixmap(0, 0, pixmap)
    painter.end()
    return result


class CoverLabel(QLabel):
    def __init__(self, width, height, radius=10, parent=None):
        super().__init__(parent)
        self.cover_width = width
        self.cover_height = height
        self.radius = radius
        self.setFixedSize(width, height)
        self.setAlignment(Qt.AlignmentFlag.AlignCenter)

    def set_cover(self, cover_path, title="", author=""):
        path = cover_file(cover_path)
        pixmap = QPixmap(str(path)) if path else QPixmap()
        if pixmap.isNull():
            self.set_pixmap_source(placeholder_cover(self.cover_width * 2, self.cover_height * 2, title, author))
        else:
            self.set_pixmap_source(pixmap)

    def set_image_file(self, file_path):
        pixmap = QPixmap(str(file_path))
        if not pixmap.isNull():
            self.set_pixmap_source(pixmap)

    def set_pixmap_source(self, pixmap):
        ratio = self.devicePixelRatioF()
        target_size = self.size() * ratio
        scaled = pixmap.scaled(
            target_size,
            Qt.AspectRatioMode.KeepAspectRatioByExpanding,
            Qt.TransformationMode.SmoothTransformation,
        )
        x = (scaled.width() - target_size.width()) // 2
        y = (scaled.height() - target_size.height()) // 2
        cropped = scaled.copy(x, y, target_size.width(), target_size.height())
        result = rounded(cropped, self.radius * ratio)
        result.setDevicePixelRatio(ratio)
        self.setPixmap(result)


class StarRating(QWidget):
    rated = Signal(int)

    def __init__(self, value=0, star_size=26, parent=None):
        super().__init__(parent)
        self.value = value
        self.hover_value = 0
        self.star_size = star_size
        self.setMouseTracking(True)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setToolTip("Поставить оценку")

    def sizeHint(self):
        return QSize(self.star_size * 5 + 8, self.star_size + 6)

    def minimumSizeHint(self):
        return self.sizeHint()

    def set_value(self, value):
        self.value = value or 0
        self.update()

    def _star_at(self, x):
        return min(5, max(1, int(x // self.star_size) + 1))

    def mouseMoveEvent(self, event):
        self.hover_value = self._star_at(event.position().x())
        self.update()

    def leaveEvent(self, event):
        self.hover_value = 0
        self.update()
        super().leaveEvent(event)

    def mouseReleaseEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self.value = self._star_at(event.position().x())
            self.update()
            self.rated.emit(self.value)

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        palette = theme.palette()
        active = self.hover_value or self.value
        font = QFont(theme.SANS)
        font.setPixelSize(int(self.star_size * 0.9))
        painter.setFont(font)
        for index in range(5):
            filled = index < active
            painter.setPen(QColor(palette["star"] if filled else palette["border"]))
            rect = QRectF(index * self.star_size, 0, self.star_size, self.star_size + 4)
            painter.drawText(rect, Qt.AlignmentFlag.AlignCenter, "★")
        painter.end()


CARD_WIDTH = 200
CARD_HEIGHT = 384


class BookCard(QFrame):
    clicked = Signal(int)

    def __init__(self, item, parent=None):
        super().__init__(parent)
        self.book_id = item.book.id
        self.setObjectName("Card")
        self.setFixedSize(CARD_WIDTH, CARD_HEIGHT)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setProperty("hovered", False)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(14, 14, 14, 14)
        layout.setSpacing(4)
        cover = CoverLabel(CARD_WIDTH - 28, 258, 8)
        cover.set_cover(item.book.cover_path, item.book.title, item.book.author.name)
        layout.addWidget(cover)
        layout.addSpacing(6)
        title = label(breakable(item.book.title, 14), "CardTitle", wrap=True)
        title.setMaximumHeight(44)
        layout.addWidget(title)
        author = label("", "CardAuthor")
        author.setText(author.fontMetrics().elidedText(item.book.author.name, Qt.TextElideMode.ElideRight, CARD_WIDTH - 30))
        layout.addWidget(author)
        layout.addWidget(label(rating_text(item.rating, item.votes), "CardRating"))
        genre_text = ", ".join(genre.name for genre in item.book.genres)
        genres = label("", "CardGenres")
        genres.setText(genres.fontMetrics().elidedText(genre_text, Qt.TextElideMode.ElideRight, CARD_WIDTH - 30))
        genres.setToolTip(genre_text)
        layout.addWidget(genres)
        layout.addStretch()
        self.shadow = QGraphicsDropShadowEffect(self)
        self.shadow.setOffset(0, 3)
        self.shadow.setBlurRadius(14)
        self.update_shadow_color()
        self.setGraphicsEffect(self.shadow)
        self.animation = QPropertyAnimation(self.shadow, b"blurRadius", self)
        self.animation.setDuration(160)
        self.setToolTip(item.book.title)

    def update_shadow_color(self):
        color = QColor(theme.palette()["shadow"])
        color.setAlpha(45 if theme.current_name() == "light" else 140)
        self.shadow.setColor(color)

    def _set_hovered(self, hovered):
        self.setProperty("hovered", hovered)
        self.style().unpolish(self)
        self.style().polish(self)
        self.animation.stop()
        self.animation.setStartValue(self.shadow.blurRadius())
        self.animation.setEndValue(30 if hovered else 14)
        self.animation.start()
        self.shadow.setOffset(0, 8 if hovered else 3)

    def enterEvent(self, event):
        self._set_hovered(True)
        super().enterEvent(event)

    def leaveEvent(self, event):
        self._set_hovered(False)
        super().leaveEvent(event)

    def mouseReleaseEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton and self.rect().contains(event.position().toPoint()):
            self.clicked.emit(self.book_id)
        super().mouseReleaseEvent(event)


SPACING = 22


class CardGrid(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.cards = []
        self.columns = 0
        self.grid = QGridLayout(self)
        self.grid.setContentsMargins(6, 6, 6, 16)
        self.grid.setHorizontalSpacing(SPACING)
        self.grid.setVerticalSpacing(SPACING)
        self.grid.setAlignment(Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignLeft)

    def set_cards(self, cards):
        for card in self.cards:
            self.grid.removeWidget(card)
            card.setParent(None)
            card.deleteLater()
        self.cards = list(cards)
        self.columns = 0
        self._relayout()

    def add_cards(self, cards):
        self.cards.extend(cards)
        self.columns = 0
        self._relayout()

    def _column_count(self):
        available = max(1, self.width() - 12)
        return max(1, (available + SPACING) // (CARD_WIDTH + SPACING))

    def _relayout(self):
        columns = self._column_count()
        if columns == self.columns and all(card.parent() is self for card in self.cards):
            return
        self.columns = columns
        for card in self.cards:
            self.grid.removeWidget(card)
        for index, card in enumerate(self.cards):
            self.grid.addWidget(card, index // columns, index % columns)
            card.show()

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._relayout()
