from string import Template

from PySide6.QtCore import QByteArray, QRectF, QSettings, Qt
from PySide6.QtGui import QFont, QFontDatabase, QIcon, QPainter, QPixmap
from PySide6.QtSvg import QSvgRenderer

from app.config import APP_SLUG, assets_dir, data_dir, fonts_dir

SERIF = "PT Serif"
SANS = "PT Sans"

PALETTES = {
    "light": {
        "bg": "#F5EFE6",
        "card": "#FFFBF5",
        "text": "#2B2118",
        "accent": "#8B2E2E",
        "accent_hover": "#A23B3B",
        "accent_text": "#FFFBF5",
        "muted": "#7A6A58",
        "border": "#E3D6C4",
        "sidebar": "#EBE1D3",
        "hover": "#E6DACA",
        "input": "#FFFDF9",
        "shadow": "#40301E",
        "star": "#C9932E",
        "danger": "#A33A2F",
    },
    "dark": {
        "bg": "#1E1A17",
        "card": "#2A2420",
        "text": "#E8DFD3",
        "accent": "#C4625A",
        "accent_hover": "#D2756D",
        "accent_text": "#1E1A17",
        "muted": "#A6968A",
        "border": "#3B332D",
        "sidebar": "#171411",
        "hover": "#352D28",
        "input": "#25201C",
        "shadow": "#000000",
        "star": "#E0AE4C",
        "danger": "#D86A5E",
    },
}

_current = {"name": "light"}


def settings():
    return QSettings(APP_SLUG, APP_SLUG)


def load_fonts():
    for path in sorted(fonts_dir().glob("*.ttf")):
        QFontDatabase.addApplicationFont(str(path))


def ui_font(size=11, bold=False):
    font = QFont(SANS, size)
    font.setBold(bold)
    return font


def serif_font(size=12, bold=False):
    font = QFont(SERIF, size)
    font.setBold(bold)
    return font


def current_name():
    return _current["name"]


def palette():
    return PALETTES[_current["name"]]


def saved_theme():
    name = settings().value("theme", "light")
    return name if name in PALETTES else "light"


def apply_theme(app, name):
    _current["name"] = name if name in PALETTES else "light"
    settings().setValue("theme", _current["name"])
    app.setFont(ui_font(11))
    app.setStyleSheet(build_stylesheet(palette()))


def build_stylesheet(p):
    template = Template((assets_dir() / "theme.qss").read_text(encoding="utf-8"))
    files = stylesheet_files(_current["name"], p)
    return template.substitute(p, serif=SERIF, sans=SANS, arrow_icon=files["arrow"], check_icon=files["check"])


STROKE = 'fill="none" stroke="{color}" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"'

SHAPES = {
    "menu": '<path d="M4 6h16M4 12h16M4 18h16" {stroke}/>',
    "catalog": '<rect x="4" y="4" width="6.5" height="6.5" rx="1.5" {stroke}/>'
    '<rect x="13.5" y="4" width="6.5" height="6.5" rx="1.5" {stroke}/>'
    '<rect x="4" y="13.5" width="6.5" height="6.5" rx="1.5" {stroke}/>'
    '<rect x="13.5" y="13.5" width="6.5" height="6.5" rx="1.5" {stroke}/>',
    "library": '<path d="M5 4.5h4v15H5zM10.5 4.5h4v15h-4z" {stroke}/>'
    '<path d="M16 5.6l3.4-.9 3 14.3-3.4.8z" {stroke} transform="translate(-1.6 0)"/>',
    "mine": '<path d="M4 20h4L19 9a2.1 2.1 0 0 0-3-3L5 17z" {stroke}/><path d="M14 8l3 3" {stroke}/>',
    "admin": '<path d="M12 3l7 3v5c0 4.5-3 8-7 10-4-2-7-5.5-7-10V6z" {stroke}/><path d="M9 12l2 2 4-4" {stroke}/>',
    "profile": '<circle cx="12" cy="8.5" r="3.6" {stroke}/><path d="M4.8 20c.9-3.6 3.7-5.6 7.2-5.6s6.3 2 7.2 5.6" {stroke}/>',
    "moon": '<path d="M19.5 14.5A8 8 0 1 1 9.5 4.5a6.5 6.5 0 0 0 10 10z" {stroke}/>',
    "sun": '<circle cx="12" cy="12" r="4" {stroke}/><path d="M12 2.5v2M12 19.5v2M2.5 12h2M19.5 12h2'
    'M5.3 5.3l1.4 1.4M17.3 17.3l1.4 1.4M5.3 18.7l1.4-1.4M17.3 6.7l1.4-1.4" {stroke}/>',
    "logout": '<path d="M14 4h4a2 2 0 0 1 2 2v12a2 2 0 0 1-2 2h-4" {stroke}/><path d="M10 8l-4 4 4 4M6 12h10" {stroke}/>',
    "arrow-down": '<path d="M7 10l5 5 5-5" {stroke}/>',
    "check": '<path d="M6 12.5l4 4 8-9" fill="none" stroke="{color}" stroke-width="2.6" stroke-linecap="round" stroke-linejoin="round"/>',
}


def svg(name, color):
    body = SHAPES[name].replace("{stroke}", STROKE).replace("{color}", color)
    return f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24">{body}</svg>'


def pixmap(name, color, size=20, ratio=2.0):
    renderer = QSvgRenderer(QByteArray(svg(name, color).encode("utf-8")))
    image = QPixmap(int(size * ratio), int(size * ratio))
    image.fill(Qt.GlobalColor.transparent)
    painter = QPainter(image)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    renderer.render(painter, QRectF(0, 0, image.width(), image.height()))
    painter.end()
    image.setDevicePixelRatio(ratio)
    return image


def icon(name, color, checked_color=None, size=20):
    result = QIcon()
    result.addPixmap(pixmap(name, color, size), QIcon.Mode.Normal, QIcon.State.Off)
    result.addPixmap(pixmap(name, checked_color or color, size), QIcon.Mode.Normal, QIcon.State.On)
    return result


def stylesheet_files(theme_name, palette):
    folder = data_dir() / "ui"
    folder.mkdir(parents=True, exist_ok=True)
    files = {
        "arrow": ("arrow-down", palette["muted"]),
        "check": ("check", palette["accent_text"]),
    }
    paths = {}
    for key, (name, color) in files.items():
        path = folder / f"{name}-{theme_name}.svg"
        path.write_text(svg(name, color), encoding="utf-8")
        paths[key] = path.as_posix()
    return paths
