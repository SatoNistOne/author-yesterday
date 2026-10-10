from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QButtonGroup,
    QDialog,
    QFormLayout,
    QHBoxLayout,
    QLineEdit,
    QRadioButton,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from app import db
from app.config import ROLE_AUTHOR, ROLE_READER, ROLE_TITLES
from app.services import auth
from app.services.rules import DISPLAY_NAME_MAX, PASSWORD_MAX, ServiceError, USERNAME_MAX, ValidationError
from app.ui.common import breakable, button, guarded, label, show_info


class LoginDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.user = None
        self.setWindowTitle("Author Yesterday — вход")
        self.setFixedWidth(460)
        layout = QVBoxLayout(self)
        layout.setSizeConstraint(QVBoxLayout.SizeConstraint.SetFixedSize)
        layout.setContentsMargins(36, 30, 36, 30)
        layout.setSpacing(10)
        title = label("Author Yesterday", "AuthTitle")
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        subtitle = label("Книжная платформа: читайте и публикуйте по главам", "Muted")
        subtitle.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(title)
        layout.addWidget(subtitle)
        layout.addSpacing(10)
        self.tabs = QTabWidget()
        self.tabs.addTab(self._build_login(), "Вход")
        self.tabs.addTab(self._build_register(), "Регистрация")
        self.tabs.currentChanged.connect(lambda _index: self.error.setText(""))
        layout.addWidget(self.tabs)
        self.error = label("", "ErrorText", wrap=True)
        layout.addWidget(self.error)

    def _build_login(self):
        page = QWidget()
        form = QFormLayout(page)
        form.setContentsMargins(0, 16, 0, 0)
        form.setVerticalSpacing(12)
        self.login_name = QLineEdit()
        self.login_name.setPlaceholderText("Логин")
        self.login_password = QLineEdit()
        self.login_password.setPlaceholderText("Пароль")
        self.login_password.setEchoMode(QLineEdit.EchoMode.Password)
        self.login_password.returnPressed.connect(self._login)
        self.login_name.setMaxLength(USERNAME_MAX)
        self.login_password.setMaxLength(PASSWORD_MAX)
        form.addRow("Логин", self.login_name)
        form.addRow("Пароль", self.login_password)
        submit = button("Войти", "primary", self._login)
        submit.setDefault(True)
        form.addRow(submit)
        return page

    def _build_register(self):
        page = QWidget()
        form = QFormLayout(page)
        form.setContentsMargins(0, 16, 0, 0)
        form.setVerticalSpacing(12)
        self.reg_name = QLineEdit()
        self.reg_name.setPlaceholderText("Не менее 3 символов")
        self.reg_display = QLineEdit()
        self.reg_display.setPlaceholderText("Как подписывать книги и отзывы")
        self.reg_password = QLineEdit()
        self.reg_password.setEchoMode(QLineEdit.EchoMode.Password)
        self.reg_password.setPlaceholderText("Не менее 6 символов")
        self.reg_repeat = QLineEdit()
        self.reg_repeat.setEchoMode(QLineEdit.EchoMode.Password)
        self.reg_repeat.returnPressed.connect(self._register)
        self.reg_name.setMaxLength(USERNAME_MAX)
        self.reg_display.setMaxLength(DISPLAY_NAME_MAX)
        self.reg_password.setMaxLength(PASSWORD_MAX)
        self.reg_repeat.setMaxLength(PASSWORD_MAX)
        roles = QHBoxLayout()
        self.role_reader = QRadioButton("Читатель")
        self.role_author = QRadioButton("Автор")
        self.role_reader.setChecked(True)
        group = QButtonGroup(page)
        group.addButton(self.role_reader)
        group.addButton(self.role_author)
        roles.addWidget(self.role_reader)
        roles.addWidget(self.role_author)
        roles.addStretch()
        form.addRow("Логин", self.reg_name)
        form.addRow("Имя", self.reg_display)
        form.addRow("Пароль", self.reg_password)
        form.addRow("Повтор", self.reg_repeat)
        form.addRow("Роль", roles)
        form.addRow(button("Зарегистрироваться", "primary", self._register))
        return page

    def _login(self):
        try:
            with db.session_scope() as session:
                self.user = auth.login(session, self.login_name.text(), self.login_password.text())
        except ServiceError as error:
            self.error.setText(str(error))
            return
        self.accept()

    def _register(self):
        if self.reg_password.text() != self.reg_repeat.text():
            self.error.setText("Пароли не совпадают")
            return
        role = ROLE_AUTHOR if self.role_author.isChecked() else ROLE_READER
        try:
            with db.session_scope() as session:
                self.user = auth.register(
                    session, self.reg_name.text(), self.reg_password.text(), role, self.reg_display.text()
                )
        except ServiceError as error:
            self.error.setText(str(error))
            return
        self.accept()


def password_field(placeholder=""):
    field = QLineEdit()
    field.setEchoMode(QLineEdit.EchoMode.Password)
    field.setPlaceholderText(placeholder)
    field.setMaxLength(PASSWORD_MAX)
    return field


class ProfileDialog(QDialog):
    def __init__(self, user, parent=None):
        super().__init__(parent)
        self.user = user
        self.updated_user = None
        self.setWindowTitle("Профиль")
        self.setMinimumWidth(460)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(28, 24, 28, 22)
        layout.setSpacing(12)
        layout.addWidget(label("Профиль", "SectionTitle"))
        layout.addWidget(label(breakable(f"Логин: {user.username} · {ROLE_TITLES.get(user.role, user.role)}"), "Muted", wrap=True))
        form = QFormLayout()
        form.setVerticalSpacing(12)
        self.name_edit = QLineEdit(user.name)
        self.name_edit.setMaxLength(DISPLAY_NAME_MAX)
        form.addRow("Имя", self.name_edit)
        layout.addLayout(form)
        layout.addSpacing(6)
        layout.addWidget(label("Смена пароля", "CardTitle"))
        layout.addWidget(label("Оставьте поля пустыми, если менять пароль не нужно", "Muted", wrap=True))
        password_form = QFormLayout()
        password_form.setVerticalSpacing(12)
        self.current_password = password_field("Текущий пароль")
        self.new_password = password_field("Не менее 6 символов")
        self.repeat_password = password_field()
        password_form.addRow("Текущий", self.current_password)
        password_form.addRow("Новый", self.new_password)
        password_form.addRow("Повтор", self.repeat_password)
        layout.addLayout(password_form)
        actions = QHBoxLayout()
        actions.addStretch()
        actions.addWidget(button("Отмена", None, self.reject))
        save = button("Сохранить", "primary", self.save)
        save.setDefault(True)
        actions.addWidget(save)
        layout.addSpacing(6)
        layout.addLayout(actions)

    @guarded
    def save(self):
        new_password = self.new_password.text()
        if new_password != self.repeat_password.text():
            raise ValidationError("Новые пароли не совпадают")
        with db.session_scope() as session:
            self.updated_user = auth.update_profile(
                session, self.user.id, self.name_edit.text(), self.current_password.text(), new_password
            )
        if new_password:
            show_info("Пароль изменён", self)
        self.accept()
