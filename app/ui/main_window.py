from PySide6.QtCore import QSize, Qt, Signal
from PySide6.QtWidgets import (
    QButtonGroup,
    QDialog,
    QFrame,
    QHBoxLayout,
    QMainWindow,
    QPushButton,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

from app.config import APP_NAME, ROLE_TITLES, WINDOW_SIZE
from app.services.rules import can_write, is_admin
from app.ui import theme
from app.ui.admin_view import AdminView
from app.ui.book_view import BookView
from app.ui.catalog_view import CatalogView
from app.ui.common import button, fit_to_screen, label, show_info
from app.ui.editors import BookEditor
from app.ui.library_view import LibraryView
from app.ui.login_dialog import ProfileDialog
from app.ui.reader_view import ReaderView


SIDEBAR_WIDTH = 230
SIDEBAR_COLLAPSED = 68
AUTO_COLLAPSE_WIDTH = 1000
NAV_ITEMS = (
    ("catalog", "catalog", "Каталог"),
    ("library", "library", "Библиотека"),
    ("mine", "mine", "Мои книги"),
    ("admin", "admin", "Админ"),
)


class MainWindow(QMainWindow):
    logout_requested = Signal()

    def __init__(self, app):
        super().__init__()
        self.app = app
        self.user = None
        self.setWindowTitle(APP_NAME)
        self.setMinimumSize(720, 520)
        saved = theme.settings().value("sidebar_collapsed", False)
        self.collapsed_by_user = saved in (True, "true")
        self.narrow = False
        self.collapsed = self.collapsed_by_user
        fit_to_screen(self, *WINDOW_SIZE)
        self.narrow = self.width() < AUTO_COLLAPSE_WIDTH
        self.collapsed = self.collapsed_by_user or self.narrow
        root = QWidget()
        layout = QHBoxLayout(root)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        layout.addWidget(self._build_sidebar())
        self.stack = QStackedWidget()
        layout.addWidget(self.stack, 1)
        self.setCentralWidget(root)
        self.pages = {}
        self.return_key = "catalog"
        self._build_pages()
        self._apply_sidebar()

    def _build_sidebar(self):
        sidebar = QFrame()
        sidebar.setObjectName("Sidebar")
        self.sidebar = sidebar
        layout = QVBoxLayout(sidebar)
        layout.setContentsMargins(12, 16, 12, 18)
        layout.setSpacing(6)
        top = QHBoxLayout()
        self.toggle_button = QPushButton()
        self.toggle_button.setObjectName("SidebarToggle")
        self.toggle_button.setToolTip("Свернуть или развернуть меню")
        self.toggle_button.setCursor(Qt.CursorShape.PointingHandCursor)
        self.toggle_button.clicked.connect(self.toggle_sidebar)
        top.addWidget(self.toggle_button)
        top.addStretch()
        layout.addLayout(top)
        self.logo_box = QWidget()
        logo_layout = QVBoxLayout(self.logo_box)
        logo_layout.setContentsMargins(4, 0, 0, 0)
        logo_layout.setSpacing(0)
        logo_layout.addWidget(label("Author", "Logo"))
        logo_layout.addWidget(label("Yesterday", "Logo"))
        logo_layout.addWidget(label("книжная платформа", "LogoSub"))
        layout.addWidget(self.logo_box)
        layout.addSpacing(16)
        self.nav_group = QButtonGroup(self)
        self.nav_group.setExclusive(True)
        self.nav_buttons = {}
        self.nav_texts = {}
        for key, icon, text in NAV_ITEMS:
            nav = QPushButton()
            nav.setObjectName("NavButton")
            nav.setCheckable(True)
            nav.setIconSize(QSize(19, 19))
            nav.setCursor(Qt.CursorShape.PointingHandCursor)
            nav.clicked.connect(lambda _checked=False, page=key: self.show_page(page))
            self.nav_group.addButton(nav)
            self.nav_buttons[key] = nav
            self.nav_texts[key] = [icon, text]
            layout.addWidget(nav)
        layout.addStretch()
        self.profile_button = QPushButton()
        self.profile_button.setObjectName("ProfileButton")
        self.profile_button.setCursor(Qt.CursorShape.PointingHandCursor)
        self.profile_button.setToolTip("Открыть профиль")
        self.profile_button.clicked.connect(self.open_profile)
        layout.addWidget(self.profile_button)
        self.theme_button = button("", None, self.toggle_theme)
        layout.addWidget(self.theme_button)
        self.logout_button = button("", None, self.logout_requested.emit, "Выйти из учётной записи")
        layout.addWidget(self.logout_button)
        return sidebar

    def sidebar_collapsed(self):
        return self.collapsed

    def toggle_sidebar(self):
        self.collapsed = not self.collapsed
        if not self.narrow:
            self.collapsed_by_user = self.collapsed
            theme.settings().setValue("sidebar_collapsed", self.collapsed)
        self._apply_sidebar()

    def _apply_sidebar(self):
        collapsed = self.sidebar_collapsed()
        palette = theme.palette()
        self.sidebar.setFixedWidth(SIDEBAR_COLLAPSED if collapsed else SIDEBAR_WIDTH)
        self.logo_box.setVisible(not collapsed)
        self.toggle_button.setIcon(theme.icon("menu", palette["muted"]))
        for key, nav in self.nav_buttons.items():
            icon_name, text = self.nav_texts[key]
            nav.setIcon(theme.icon(icon_name, palette["text"], palette["accent_text"]))
            nav.setText("" if collapsed else f"  {text}")
            nav.setToolTip(text if collapsed else "")
            nav.setStyleSheet("text-align: center; padding: 10px 0;" if collapsed else "")
        dark = theme.current_name() == "dark"
        theme_icon, theme_text = ("sun", "Светлая тема") if dark else ("moon", "Тёмная тема")
        self.theme_button.setIcon(theme.icon(theme_icon, palette["text"]))
        self.theme_button.setText("" if collapsed else f"  {theme_text}")
        self.theme_button.setToolTip(theme_text)
        self.logout_button.setIcon(theme.icon("logout", palette["text"]))
        self.logout_button.setText("" if collapsed else "  Выйти")
        self.profile_button.setIcon(theme.icon("profile", palette["text"]))
        if self.user is not None:
            role = ROLE_TITLES.get(self.user.role, self.user.role)
            name = self.profile_button.fontMetrics().elidedText(self.user.name, Qt.TextElideMode.ElideRight, SIDEBAR_WIDTH - 80)
            self.profile_button.setText("" if collapsed else f"  {name}\n  {role}")
            self.profile_button.setToolTip(f"Профиль: {self.user.name}")
        for widget in (self.toggle_button, self.profile_button):
            widget.setStyleSheet("text-align: center;" if collapsed else "")

    def resizeEvent(self, event):
        super().resizeEvent(event)
        narrow = self.width() < AUTO_COLLAPSE_WIDTH
        if narrow != self.narrow:
            self.narrow = narrow
            self.collapsed = True if narrow else self.collapsed_by_user
            self._apply_sidebar()

    def open_profile(self):
        dialog = ProfileDialog(self.user, self)
        if dialog.exec() == QDialog.DialogCode.Accepted and dialog.updated_user is not None:
            self.user = dialog.updated_user
            self._apply_sidebar()
            current = self.stack.currentWidget()
            if current is not None:
                current.refresh()

    def _build_pages(self):
        self._add_page("catalog", CatalogView(self))
        self._add_page("mine", CatalogView(self, mine=True))
        self._add_page("book", BookView(self))
        self._add_page("reader", ReaderView(self))
        self._add_page("library", LibraryView(self))
        self._add_page("admin", AdminView(self))

    def _add_page(self, key, widget):
        self.pages[key] = widget
        self.stack.addWidget(widget)

    def set_user(self, user):
        self.user = user
        self.pages["reader"].book_id = None
        self.pages["book"].book_id = None
        self.nav_buttons["mine"].setVisible(can_write(user))
        self.nav_buttons["admin"].setVisible(is_admin(user))
        self.pages["mine"].title.setText("Все книги" if is_admin(user) else "Мои книги")
        self.nav_texts["mine"][1] = "Все книги" if is_admin(user) else "Мои книги"
        self._apply_sidebar()
        self.show_page("catalog")

    def toggle_theme(self):
        theme.apply_theme(self.app, "dark" if theme.current_name() == "light" else "light")
        self._apply_sidebar()
        self.on_theme_changed()

    def on_theme_changed(self):
        for page in self.pages.values():
            if hasattr(page, "on_theme_changed"):
                page.on_theme_changed()
        current = self.stack.currentWidget()
        if current is not None and current is not self.pages["reader"]:
            current.refresh()

    def show_page(self, key):
        page = self.pages[key]
        if key in self.nav_buttons:
            self.nav_buttons[key].setChecked(True)
            self.return_key = key
        self.stack.setCurrentWidget(page)
        page.refresh()

    def go_back(self):
        self.show_page(self.return_key)

    def open_book(self, book_id, register_view=True):
        self.pages["book"].load(book_id, register_view=register_view)
        self.stack.setCurrentWidget(self.pages["book"])

    def open_reader(self, book_id, chapter_id=None):
        if self.pages["reader"].open_book(book_id, chapter_id):
            self.stack.setCurrentWidget(self.pages["reader"])

    def closeEvent(self, event):
        self.pages["reader"].save_position()
        super().closeEvent(event)

    def edit_book(self, book_id):
        dialog = BookEditor(self.user, book_id, self)
        if dialog.exec() == QDialog.DialogCode.Accepted and dialog.saved_book_id:
            self.pages["book"].load(dialog.saved_book_id)
            self.stack.setCurrentWidget(self.pages["book"])

    def notify(self, message):
        show_info(message, self)
