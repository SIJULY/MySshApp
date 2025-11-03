import sys
import threading
import base64
import stat
import datetime
import json
import functools  # (新增) 导入 functools
import requests  # (新增) 导入 requests
from PySide6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QFormLayout,
    QLineEdit, QPushButton, QTextEdit, QListWidget, QSplitter,
    QHBoxLayout, QLabel, QMessageBox, QListWidgetItem, QFileDialog,
    QDialog, QDialogButtonBox,
    QTabWidget,
    QTableWidget, QTableWidgetItem, QHeaderView,
    QTreeWidget, QTreeWidgetItem, QTreeWidgetItemIterator,
    QStackedWidget, QTabBar,
    QScrollArea, QCheckBox, QMenu,
    QFrame,
    QAbstractItemView,
    QGridLayout  # (新增)
)
# --- (新增) 导入 WebEngine 和 WebChannel ---
from PySide6.QtWebEngineWidgets import QWebEngineView
from PySide6.QtWebEngineCore import QWebEngineSettings
from PySide6.QtWebChannel import QWebChannel

from PySide6.QtCore import (
    Qt, Signal, QObject, QThread,
    QSettings, QTimer, QMetaObject, Q_ARG, Slot, QUrl,
    QPoint  # (新增)
)
from PySide6.QtGui import QFont, QCloseEvent
import paramiko
import os

# --- (新增) 终端的 HTML 和 JavaScript ---
# 我们将使用 xterm.js (VS Code 终端正在使用的库)
# 它通过 CDN 加载
TERMINAL_HTML = """
<!DOCTYPE html>
<html>
<head>
    <meta charset="utf-8" />
    <title>xterm.js Terminal</title>
    <link rel="stylesheet" href="https://cdn.jsdelivr.net/npm/xterm@5.3.0/css/xterm.min.css" />
    <script src="https://cdn.jsdelivr.net/npm/xterm@5.3.0/lib/xterm.min.js"></script>

    <script src="https://cdn.jsdelivr.net/npm/xterm-addon-fit@0.8.0/lib/xterm-addon-fit.min.js"></script>

    <script src="qrc:///qtwebchannel/qwebchannel.js"></script>

    <style>
        body, html {
            margin: 0;
            padding: 0;
            width: 100%;
            height: 100%;
            background-color: #1e1e1e; /* 终端背景色 */
            overflow: hidden; /* 隐藏滚动条 */
        }
        #terminal {
            width: 100%;
            height: 100%;
        }
    </style>
</head>
<body>
    <div id="terminal"></div>

    <script>
        // --- 1. 初始化 xterm.js 终端 ---
        const term = new Terminal({
            cursorBlink: true,
            theme: {
                background: '#1e1e1e',
                foreground: '#d4d4d4'
            },
            fontFamily: 'monospace',
            fontSize: 14
        });

        // --- 2. 初始化 'fit' 插件 ---
        const fitAddon = new FitAddon.FitAddon();
        term.loadAddon(fitAddon);

        // --- 3. 将终端附加到 DOM ---
        term.open(document.getElementById('terminal'));

        // --- 4. (修改) 设置与 Python 的 WebChannel 通信 (健壮模式) ---
        new QWebChannel(qt.webChannelTransport, function (channel) {

            function initialize_backend() {
                if (channel.objects.py_backend) {
                    // --- 后端对象已找到 ---
                    console.log("py_backend object found. Setting up.");
                    window.py_backend = channel.objects.py_backend;

                    // --- 5. JS -> Python (用户输入) ---
                    // 这可以安全地立即连接。
                    term.onData(function (data) {
                        py_backend.term_write(data);
                    });

                    // --- 6. Python -> JS (等待 Shell 准备就绪) ---

                    // (*** 新增 ***) 
                    // 添加一个标志位来防止双重连接
                    let isPyBackendConnected = false;

                    py_backend.shell_ready.connect(function () {
                        console.log("Python shell_ready signal received.");

                        // (*** 新增 ***) 
                        // 检查标志位
                        if (isPyBackendConnected) {
                            console.log("Backend already connected. Ignoring duplicate signal.");
                            // 即使重复，也可能需要调整大小（例如浏览器刷新）
                            resize_term();
                            term.focus();
                            return; // 退出，不重复连接
                        }
                        isPyBackendConnected = true;
                        // (*** 新增结束 ***)


                        // --- 6a. 连接 Shell 输出 ---
                        py_backend.term_read.connect(function (data) {
                            term.write(data);
                        });

                        // --- 7. 连接调整大小逻辑 ---
                        function resize_term() {
                            fitAddon.fit();
                            py_backend.resize_shell(term.cols, term.rows);
                        }

                        window.addEventListener('resize', resize_term);
                        resize_term(); // 调用一次
                        term.focus();
                    });

                    // 告诉 Python JS 已经加载
                    py_backend.js_loaded();

                } else {
                    // 如果 py_backend 还没准备好，等待并重试
                    console.log("Waiting for py_backend...");
                    setTimeout(initialize_backend, 100);
                }
            }

            // 开始初始化检查
            initialize_backend();
        });
    </script>
</body>
</html>
"""
# --- (修改) 账户添加/编辑对话框 ---
class AccountDialog(QDialog):
    """
    一个模式对话框，用于添加或编辑账户信息。
    """

    def __init__(self, account_data=None, parent=None):
        super().__init__(parent)
        self.setWindowTitle("账户信息")

        layout = QFormLayout(self)

        self.name_input = QLineEdit()
        self.host_input = QLineEdit()
        self.port_input = QLineEdit("22")
        self.user_input = QLineEdit("root")

        # --- 密码认证 ---
        self.pass_input = QLineEdit()
        self.pass_input.setEchoMode(QLineEdit.EchoMode.Password)
        layout.addRow("名称 (例如 '我的VPS'):", self.name_input)
        layout.addRow("主机:", self.host_input)
        layout.addRow("端口:", self.port_input)
        layout.addRow("用户名:", self.user_input)
        layout.addRow("密码 (优先):", self.pass_input)

        # --- (新增) 密钥文件认证 ---
        key_layout = QHBoxLayout()
        self.key_path_input = QLineEdit()
        self.key_path_input.setReadOnly(True)
        self.key_path_input.setPlaceholderText("或选择密钥文件")
        browse_btn = QPushButton("浏览...")
        browse_btn.clicked.connect(self.on_browse_key_file)
        key_layout.addWidget(self.key_path_input)
        key_layout.addWidget(browse_btn)
        layout.addRow("密钥文件:", key_layout)

        # --- 互斥逻辑 ---
        self.pass_input.textChanged.connect(self.on_pass_changed)
        self.key_path_input.textChanged.connect(self.on_key_changed)

        # 保存和取消按钮
        self.button_box = QDialogButtonBox(QDialogButtonBox.Save | QDialogButtonBox.Cancel)
        self.button_box.accepted.connect(self.accept)
        self.button_box.rejected.connect(self.reject)
        layout.addWidget(self.button_box)

        if account_data:
            self.name_input.setText(account_data.get('name', ''))
            self.host_input.setText(account_data.get('host', ''))
            self.port_input.setText(account_data.get('port', '22'))
            self.user_input.setText(account_data.get('user', 'root'))
            self.key_path_input.setText(account_data.get('key_path', ''))
            try:
                # 仅在没有密钥路径时才加载密码
                if not account_data.get('key_path', ''):
                    decoded_pass = base64.b64decode(account_data.get('pass_b64', '')).decode('utf-8')
                    self.pass_input.setText(decoded_pass)
            except Exception:
                self.pass_input.setText("")

    def on_browse_key_file(self):
        """打开文件对话框选择密钥文件"""
        path, _ = QFileDialog.getOpenFileName(self, "选择私钥文件", os.path.expanduser("~"), "所有文件 (*)")
        if path:
            self.key_path_input.setText(path)

    def on_pass_changed(self, text):
        """当用户输入密码时，清空密钥路径"""
        if text:
            self.key_path_input.clear()

    def on_key_changed(self, text):
        """当用户选择密钥时，清空密码"""
        if text:
            self.pass_input.clear()

    def get_data(self):
        """获取对话框中的数据"""
        pass_b64 = ""
        key_path = self.key_path_input.text()

        # 仅在没有选择密钥时才保存密码
        if not key_path:
            try:
                pass_b64 = base64.b64encode(self.pass_input.text().encode('utf-8')).decode('utf-8')
            except Exception:
                pass_b64 = ""

        return {
            'name': self.name_input.text(),
            'host': self.host_input.text(),
            'port': self.port_input.text(),
            'user': self.user_input.text(),
            'pass_b64': pass_b64,
            'key_path': key_path  # (新增)
        }


# --- 简单的文本编辑器对话框 ---
class TextEditorDialog(QDialog):
    """
    一个简单的模式对话框，用于编辑文本文件内容。
    """

    def __init__(self, file_content, parent=None):
        super().__init__(parent)
        self.setWindowTitle("终端")
        self.setGeometry(150, 150, 600, 500)

        layout = QVBoxLayout(self)

        self.text_edit = QTextEdit()
        self.text_edit.setText(file_content)
        self.text_edit.setFontFamily("monospace")
        layout.addWidget(self.text_edit)

        # 保存和取消按钮
        self.button_box = QDialogButtonBox(QDialogButtonBox.Save | QDialogButtonBox.Cancel)
        self.button_box.accepted.connect(self.accept)
        self.button_box.rejected.connect(self.reject)
        layout.addWidget(self.button_box)

    def get_text(self):
        """获取编辑后的文本"""
        return self.text_edit.toPlainText()


# --- (新增) 添加命令对话框 ---
class CommandDialog(QDialog):
    """
    一个模式对话框，用于添加或编辑命令卡片。
    """

    def __init__(self, command_data=None, parent=None):
        super().__init__(parent)
        self.setWindowTitle("添加/编辑命令")

        layout = QFormLayout(self)

        self.name_input = QLineEdit()
        self.command_input = QTextEdit()
        self.command_input.setFontFamily("monospace")
        self.command_input.setAcceptRichText(False)
        self.add_cr_checkbox = QCheckBox("末尾添加回车符 (自动执行)")

        layout.addRow("名称:", self.name_input)
        layout.addRow("命令:", self.command_input)
        layout.addRow("", self.add_cr_checkbox)

        # 保存和取消按钮
        self.button_box = QDialogButtonBox(QDialogButtonBox.Save | QDialogButtonBox.Cancel)
        self.button_box.accepted.connect(self.accept)
        self.button_box.rejected.connect(self.reject)
        layout.addWidget(self.button_box)

        if command_data:
            self.name_input.setText(command_data.get('name', ''))
            self.command_input.setText(command_data.get('command', ''))
            self.add_cr_checkbox.setChecked(command_data.get('add_cr', True))
        else:
            self.add_cr_checkbox.setChecked(True)  # 默认为 true

    def get_data(self):
        """获取对话框中的数据"""
        return {
            'name': self.name_input.text(),
            'command': self.command_input.toPlainText(),
            'add_cr': self.add_cr_checkbox.isChecked()
        }


# --- (修改) 同步登录/管理对话框 ---
class SyncDialog(QDialog):  # (修改) 重命名
    """
    用于登录、注册和管理同步服务器的对话框。
    """
    # --- (修改) 信号现在包含用户名 ---
    login_success = Signal(str, str, str)  # server_url, token, username
    logout_requested = Signal()  # (新增)

    # (新增) 手动同步信号
    upload_requested = Signal()
    download_requested = Signal()

    def __init__(self, settings, sync_manager, parent=None):
        super().__init__(parent)
        self.settings = settings
        self.setWindowTitle("账户同步")

        self.sync_manager = sync_manager

        # 连接信号
        self.sync_manager.login_success.connect(self.on_login_success)
        self.sync_manager.register_success.connect(self.on_register_success)
        self.sync_manager.sync_failure.connect(self.on_sync_failure)

        # (新增) 连接手动同步信号
        self.sync_manager.upload_success.connect(lambda: self.status_label.setText("上传成功！"))
        # --- (修复) lambda 必须接受 str 参数 ---
        self.sync_manager.download_success.connect(lambda json_str, ask: self.status_label.setText("下载成功！"))

        main_layout = QVBoxLayout(self)
        form_layout = QFormLayout()

        self.server_input = QLineEdit()
        self.username_input = QLineEdit()
        self.password_input = QLineEdit()
        self.password_input.setEchoMode(QLineEdit.EchoMode.Password)

        self.server_input.setText(self.settings.value("sync/server_url", "http://[VPS_IP]:5000"))
        self.username_input.setText(self.settings.value("sync/username", ""))

        form_layout.addRow("服务器 URL:", self.server_input)
        form_layout.addRow("用户名:", self.username_input)
        form_layout.addRow("密码:", self.password_input)

        main_layout.addLayout(form_layout)

        self.status_label = QLabel("请输入你的同步服务器信息。")
        self.status_label.setWordWrap(True)
        main_layout.addWidget(self.status_label)

        self.login_btn = QPushButton("登录")
        self.register_btn = QPushButton("注册")
        self.logout_btn = QPushButton("登出")  # (新增)
        self.login_btn.clicked.connect(self.start_login)
        self.register_btn.clicked.connect(self.start_register)
        self.logout_btn.clicked.connect(self.start_logout)  # (新增)

        login_button_layout = QHBoxLayout()
        login_button_layout.addWidget(self.login_btn)
        login_button_layout.addWidget(self.register_btn)
        login_button_layout.addWidget(self.logout_btn)  # (新增)
        main_layout.addLayout(login_button_layout)

        # --- (新增) 手动同步按钮 ---
        sync_button_layout = QHBoxLayout()
        self.upload_btn = QPushButton("上传 (本地覆盖云端)")
        self.download_btn = QPushButton("下载 (云端覆盖本地)")
        self.upload_btn.clicked.connect(self.start_upload)
        self.download_btn.clicked.connect(self.start_download)

        sync_button_layout.addWidget(self.upload_btn)
        sync_button_layout.addWidget(self.download_btn)
        main_layout.addLayout(sync_button_layout)

        # 检查是否已有令牌
        if self.settings.value("sync/token"):
            self.status_label.setText(f"已登录到 {self.settings.value('sync/username')}")
            self.set_sync_buttons_enabled(True)
            self.login_btn.setEnabled(False)
            self.register_btn.setEnabled(False)
        else:
            self.set_sync_buttons_enabled(False)
            self.logout_btn.setEnabled(False)

    def start_login(self):
        self.set_login_buttons_enabled(False)
        self.status_label.setText("正在登录...")
        QMetaObject.invokeMethod(
            self.sync_manager, "login",
            Qt.QueuedConnection,
            Q_ARG(str, self.server_input.text()),
            Q_ARG(str, self.username_input.text()),
            Q_ARG(str, self.password_input.text())
        )

    def start_register(self):
        self.set_login_buttons_enabled(False)
        self.status_label.setText("正在注册...")
        QMetaObject.invokeMethod(
            self.sync_manager, "register",
            Qt.QueuedConnection,
            Q_ARG(str, self.server_input.text()),
            Q_ARG(str, self.username_input.text()),
            Q_ARG(str, self.password_input.text())
        )

    # (新增)
    def start_logout(self):
        self.settings.remove("sync/token")
        self.settings.remove("sync/username")
        self.status_label.setText("已登出。同步已禁用。")
        self.set_login_buttons_enabled(True)
        self.set_sync_buttons_enabled(False)
        self.logout_btn.setEnabled(False)
        self.logout_requested.emit()  # 告诉 MainWindow 切换回本地

    def start_upload(self):
        self.status_label.setText("正在上传...")
        self.upload_requested.emit()

    def start_download(self):
        self.status_label.setText("正在下载...")
        self.download_requested.emit()

    def set_login_buttons_enabled(self, enabled):
        self.login_btn.setEnabled(enabled)
        self.register_btn.setEnabled(enabled)

    def set_sync_buttons_enabled(self, enabled):
        self.upload_btn.setEnabled(enabled)
        self.download_btn.setEnabled(enabled)
        self.logout_btn.setEnabled(enabled)  # (修改)

    @Slot(str, str, str)  # (修改) 增加 username
    def on_login_success(self, server_url, token, username):
        self.set_login_buttons_enabled(False)  # (修改) 登录后禁用
        self.set_sync_buttons_enabled(True)
        self.status_label.setText("登录成功！请选择操作。")

        # (移除) username 现在从信号中获取

        # 保存凭据
        self.settings.setValue("sync/server_url", server_url)
        self.settings.setValue("sync/username", username)  # (修改)
        self.settings.setValue("sync/token", token)

        self.login_success.emit(server_url, token, username)  # (修改)
        # (移除) 不再自动关闭

    @Slot()
    def on_register_success(self):
        self.set_login_buttons_enabled(True)
        self.status_label.setText("注册成功！请立即登录。")

    @Slot(str)
    def on_sync_failure(self, error):
        self.set_login_buttons_enabled(True)
        self.status_label.setText(f"错误: {error}")
        if "token" in error.lower() or "过期" in error:
            self.set_sync_buttons_enabled(False)
            self.settings.remove("sync/token")
            self.logout_btn.setEnabled(False)

    def closeEvent(self, event):
        # (修复) 断开信号，防止崩溃
        try:
            self.sync_manager.login_success.disconnect(self.on_login_success)
            self.sync_manager.register_success.disconnect(self.on_register_success)
            self.sync_manager.sync_failure.disconnect(self.on_sync_failure)
            self.sync_manager.upload_success.disconnect()
            self.sync_manager.download_success.disconnect()
        except Exception as e:
            print(f"关闭同步对话框时出错: {e}")

        event.accept()


# --- (新增) 终端桥接类 ---
class TerminalBridge(QObject):
    """
    此类存在于主 GUI 线程中，作为 QWebChannel 和
    后台 SshWorker 线程之间的安全桥梁。
    """
    # 信号：发往 JS
    term_read = Signal(str)
    shell_ready = Signal()

    # 信号：发往 SshWorker
    bridge_term_write = Signal(str)
    bridge_resize_shell = Signal(int, int)
    bridge_js_loaded = Signal()

    # 槽：从 SshWorker 接收
    @Slot(str)
    def on_term_read(self, data):
        self.term_read.emit(data)

    @Slot()
    def on_shell_ready(self):
        self.shell_ready.emit()

    # 槽：从 JS 接收
    @Slot(str)
    def term_write(self, data):
        self.bridge_term_write.emit(data)

    @Slot(int, int)
    def resize_shell(self, cols, rows):
        self.bridge_resize_shell.emit(cols, rows)

    @Slot()
    def js_loaded(self):
        self.bridge_js_loaded.emit()


# --- 用于在后台线程中处理 SSH ---
class SshWorker(QObject):
    """
    在一个单独的线程中处理 Paramiko SSH 操作
    以避免冻结 GUI
    """
    # (修改) 信号现在将由 SessionManager 路由
    connection_success = Signal(object)
    connection_failed = Signal(str)
    file_list_result = Signal(list, str)
    status_update = Signal(dict)
    download_success = Signal(str)
    download_failed = Signal(str)
    upload_success = Signal(str)
    upload_failed = Signal(str)
    file_content_fetched = Signal(str)
    file_content_failed = Signal(str)
    file_save_success = Signal(str)
    file_save_failed = Signal(str)
    tree_dir_list_result = Signal(str, list, str)

    term_read = Signal(str)
    shell_ready = Signal()

    def __init__(self):
        super().__init__()
        self.ssh_client = None
        self.monitor_timer = None
        self.ssh_channel = None
        self.shell_thread = None
        self.is_running = True  # (新增)

    @Slot(dict)
    def start_connection(self, account_data):
        """尝试连接到 SSH 服务器"""
        try:
            host = account_data.get('host')
            port = int(account_data.get('port', 22))
            username = account_data.get('user')
            pass_b64 = account_data.get('pass_b64')
            key_path = account_data.get('key_path')

            password = None
            key_filename = None

            if key_path:
                key_filename = key_path
                print(f"尝试使用密钥文件登录: {key_filename}")
            elif pass_b64:
                try:
                    password = base64.b64decode(pass_b64).decode('utf-8')
                    print("尝试使用密码登录")
                except Exception:
                    raise ValueError("密码解码失败")
            else:
                print("尝试无密码/无密钥登录 (可能使用 SSH Agent)")

            self.ssh_client = paramiko.SSHClient()
            self.ssh_client.set_missing_host_key_policy(paramiko.AutoAddPolicy())

            self.ssh_client.connect(
                hostname=host,
                port=port,
                username=username,
                password=password,
                key_filename=key_filename,
                timeout=5
            )
            self.connection_success.emit(self.ssh_client)
        except Exception as e:
            self.connection_failed.emit(str(e))

    def start_shell(self, ssh_client):
        """
        使用 invoke_shell 启动一个持久化的 PTY。
        """
        try:
            self.ssh_channel = ssh_client.invoke_shell(term='xterm-256color', width=80, height=24)
            self.shell_thread = threading.Thread(target=self.read_shell_output, daemon=True)
            self.shell_thread.start()
            self.shell_ready.emit()
        except Exception as e:
            self.term_read.emit(f"\n无法启动 shell: {e}\n")

    def read_shell_output(self):
        """
        在专用的 threading.Thread 中运行，
        """
        try:
            while self.is_running and self.ssh_channel and not self.ssh_channel.closed:
                data = self.ssh_channel.recv(4096)
                if not data:
                    break
                self.term_read.emit(data.decode('utf-8', errors='replace'))
        except Exception as e:
            if self.is_running and self.ssh_channel and not self.ssh_channel.closed:
                print(f"Shell 读取错误: {e}")
                self.term_read.emit(f"\nShell 读取错误: {e}\n")

    @Slot(str)
    def term_write(self, data):
        if self.ssh_channel:
            try:
                self.ssh_channel.send(data.encode('utf-8'))
            except Exception as e:
                print(f"Shell 写入错误: {e}")

    @Slot(int, int)
    def resize_shell(self, cols, rows):
        if self.ssh_channel:
            try:
                self.ssh_channel.resize_pty(width=cols, height=rows)
            except Exception as e:
                print(f"PTY 重设大小错误: {e}")

    @Slot()
    def js_loaded(self):
        print("JS has loaded and found py_backend.")
        if self.ssh_channel and not self.ssh_channel.closed:
            print("Re-emitting shell_ready for reloaded page.")
            self.shell_ready.emit()

    @Slot(str)
    def list_files(self, path="."):
        if not self.ssh_client:
            self.file_list_result.emit([], "错误：未连接")
            return
        try:
            sftp = self.ssh_client.open_sftp()
            file_attrs_list = sftp.listdir_attr(path)
            sftp.close()

            formatted_list = []
            for attr in file_attrs_list:
                is_dir = stat.S_ISDIR(attr.st_mode)
                file_type = "目录" if is_dir else "文件"
                mtime = datetime.datetime.fromtimestamp(attr.st_mtime).strftime('%Y-%m-%d %H:%M:%S')
                perms = stat.filemode(attr.st_mode)
                formatted_list.append({
                    "name": attr.filename,
                    "size": attr.st_size if not is_dir else 0,
                    "type": file_type, "mtime": mtime,
                    "perms": perms, "is_dir": is_dir
                })
            self.file_list_result.emit(formatted_list, None)
        except Exception as e:
            self.file_list_result.emit([], str(e))
            print(f"SFTP 错误: {e}")

    @Slot(str)
    def list_dirs_for_tree(self, path):
        if not self.ssh_client:
            self.tree_dir_list_result.emit(path, [], "错误：未连接")
            return
        try:
            sftp = self.ssh_client.open_sftp()
            attrs_list = sftp.listdir_attr(path)
            sftp.close()
            dir_list = []
            for attr in attrs_list:
                if stat.S_ISDIR(attr.st_mode) and attr.filename not in ('.', '..'):
                    dir_list.append(attr.filename)
            self.tree_dir_list_result.emit(path, sorted(dir_list), None)
        except Exception as e:
            self.tree_dir_list_result.emit(path, [], str(e))
            print(f"SFTP (Tree) 错误: {e}")

    @Slot(str, str)
    def download_file(self, remote_path, local_path):
        if not self.ssh_client:
            self.download_failed.emit("错误：未连接")
            return
        try:
            sftp = self.ssh_client.open_sftp()
            sftp.get(remote_path, local_path)
            sftp.close()
            self.download_success.emit(f"文件已成功下载到: {local_path}")
        except Exception as e:
            self.download_failed.emit(f"下载失败: {e}")

    @Slot(str, str)
    def upload_file(self, local_path, remote_path):
        if not self.ssh_client:
            self.upload_failed.emit("错误：未连接")
            return
        try:
            sftp = self.ssh_client.open_sftp()
            sftp.put(local_path, remote_path)
            sftp.close()
            self.upload_success.emit(f"文件已成功上传到: {remote_path}")
        except Exception as e:
            self.upload_failed.emit(f"上传失败: {e}")

    @Slot(str)
    def fetch_file_content(self, remote_path):
        if not self.ssh_client:
            self.file_content_failed.emit("错误：未连接")
            return
        try:
            sftp = self.ssh_client.open_sftp()
            with sftp.open(remote_path, 'r') as f:
                content = f.read(5 * 1024 * 1024).decode('utf-8')
            sftp.close()
            self.file_content_fetched.emit(content)
        except Exception as e:
            self.file_content_failed.emit(f"无法读取文件内容: {e}\n(可能是二进制文件、权限不足或文件过大)")

    @Slot(str, str)
    def save_file_content(self, remote_path, content):
        if not self.ssh_client:
            self.file_save_failed.emit("错误：未连接")
            return
        try:
            sftp = self.ssh_client.open_sftp()
            with sftp.open(remote_path, 'w') as f:
                f.write(content.encode('utf-8'))
            sftp.close()
            self.file_save_success.emit(f"文件已成功保存: {remote_path}")
        except Exception as e:
            self.file_save_failed.emit(f"保存失败: {e}")

    def start_monitoring(self):
        if self.monitor_timer is None:
            self.monitor_timer = QTimer()
            self.monitor_timer.timeout.connect(self.fetch_status)
        self.monitor_timer.start(2000)
        self.fetch_status()

    def stop_monitoring(self):
        if self.monitor_timer:
            self.monitor_timer.stop()

    def fetch_status(self):
        if not self.ssh_client or not self.is_running:
            return

        # --- (修复) 更改 grep 命令以仅获取平均 CPU ---
        command = "uptime; free -m; top -bn1 | grep -E '^(Tasks|%Cpu\(s\))'; df -h /"

        try:
            stdin, stdout, stderr = self.ssh_client.exec_command(command)
            output = stdout.read().decode('utf-8')
            errors = stderr.read().decode('utf-8')
            if errors:
                print(f"获取状态时出错 (stderr): {errors}")
            stats = self.parse_stats(output)
            self.status_update.emit(stats)
        except Exception as e:
            if self.is_running:
                print(f"获取状态时出错: {e}")
                self.status_update.emit({"error": str(e)})

    # (修改) 恢复到 V2 版本的解析
    def parse_stats(self, output):
        stats = {}
        try:
            lines = output.splitlines()
            for line in lines:
                if 'load average' in line:
                    parts = line.split('up')
                    if len(parts) > 1:
                        stats['uptime'] = parts[1].split(',')[0].strip()
                        stats['load'] = line.split('load average:')[-1].strip()
                elif line.startswith('Mem:'):
                    parts = line.split()
                    stats['mem_total'] = parts[1]
                    stats['mem_used'] = parts[2]
                elif line.startswith('%Cpu(s):'):  # (修改) 确保只匹配这一行
                    parts = line.split(',')
                    for part in parts:
                        if 'id' in part:
                            # 提取 idle 值
                            idle = float(part.strip().split()[0].replace(',', '.'))
                            cpu_usage = 100.0 - idle
                            stats['cpu_usage'] = f"{cpu_usage:.1f}%"
                            break
                elif line.startswith('Tasks:'):
                    stats['tasks'] = line.split('Tasks:')[-1].split(',')[0].strip()
                elif line.startswith('/dev/'):
                    parts = line.split()
                    stats['disk_size'] = parts[1]
                    stats['disk_used'] = parts[2]
                    stats['disk_percent'] = parts[4]  # 恢复
        except Exception as e:
            print(f"解析状态时出错: {e}")
            stats['error'] = "解析失败"
        return stats

    # (新增) 清理方法
    @Slot()
    def close(self):
        """关闭此 worker 的所有资源"""
        self.is_running = False
        self.stop_monitoring()
        if self.ssh_channel:
            self.ssh_channel.close()
        if self.ssh_client:
            self.ssh_client.close()


# --- (修改) 状态监视器小部件 ---
class StatusMonitorWidget(QWidget):

    # (移除) 样式

    def __init__(self, parent=None):
        super().__init__(parent)
        # (恢复) V2 版本的 QFormLayout
        status_layout = QFormLayout(self)
        # --- (修复) 强制标签左对齐 ---
        status_layout.setLabelAlignment(Qt.AlignmentFlag.AlignLeft)
        align_left = Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter

        self.uptime_label = QLabel("N/A")
        self.uptime_label.setAlignment(align_left)
        self.load_label = QLabel("N/A")
        self.load_label.setAlignment(align_left)
        self.tasks_label = QLabel("N/A")
        self.tasks_label.setAlignment(align_left)
        self.cpu_label = QLabel("N/A")
        self.cpu_label.setAlignment(align_left)
        self.mem_label = QLabel("N/A")
        self.mem_label.setAlignment(align_left)
        self.disk_label = QLabel("N/A")
        self.disk_label.setAlignment(align_left)

        status_layout.addRow("运行时间:", self.uptime_label)
        status_layout.addRow("系统负载:", self.load_label)
        status_layout.addRow("任务数:", self.tasks_label)
        status_layout.addRow("CPU:", self.cpu_label)
        status_layout.addRow("内存:", self.mem_label)
        status_layout.addRow("磁盘 (/):", self.disk_label)

    @Slot(dict)
    def on_status_update(self, stats):
        if "error" in stats:
            self.reset()
            self.uptime_label.setText("错误")
            self.load_label.setText("错误")
            return

        self.uptime_label.setText(stats.get('uptime', 'N/A'))
        self.load_label.setText(stats.get('load', 'N/A'))
        self.tasks_label.setText(stats.get('tasks', 'N/A'))
        self.cpu_label.setText(stats.get('cpu_usage', 'N/A'))

        # (恢复) V2 版本的文本
        mem_used = stats.get('mem_used', 'N/A')
        mem_total = stats.get('mem_total', 'N/A')
        self.mem_label.setText(f"{mem_used}M / {mem_total}M")

        disk_used = stats.get('disk_used', 'N/A')
        disk_size = stats.get('disk_size', 'N/A')
        disk_percent = stats.get('disk_percent', 'N/A')
        self.disk_label.setText(f"{disk_used} / {disk_size} ({disk_percent})")

    def reset(self):
        # (恢复) V2 版本的重置
        self.uptime_label.setText("N/A")
        self.load_label.setText("N/A")
        self.tasks_label.setText("N/A")
        self.cpu_label.setText("N/A")
        self.mem_label.setText("N/A")
        self.disk_label.setText("N/A")


# --- (修改) 文件浏览器小部件重命名为 BottomPaneWidget ---
class BottomPaneWidget(QWidget):
    # 向 worker 发出请求
    request_list_files = Signal(str)
    request_list_dirs = Signal(str)
    request_download = Signal(str, str)
    request_upload = Signal(str, str)
    request_fetch_content = Signal(str)
    request_save_content = Signal(str, str)

    # (新增) 向 bridge 发送命令
    send_to_terminal = Signal(str)

    # 显示消息
    show_message = Signal(str, str)  # (title, message)
    show_error = Signal(str, str)  # (title, error)
    show_warning = Signal(str, str)  # (新增)

    def __init__(self, settings, parent=None):
        super().__init__(parent)

        self.settings = settings  # (新增) 存储 QSettings 的引用
        self.current_path = "/"
        self.editing_remote_path = None
        self.editor_dialog = None

        file_tabs_layout = QVBoxLayout(self)
        file_tabs_layout.setContentsMargins(0, 0, 0, 0)

        self.file_tab_control = QTabWidget()

        # --- Tab 1: 文件浏览器 (树状 + 表格) ---
        file_browser_widget = QWidget()
        file_browser_layout = QVBoxLayout(file_browser_widget)
        file_browser_layout.setContentsMargins(0, 0, 0, 0)

        self.current_path_label = QLabel(f"路径: {self.current_path}")
        self.current_path_label.setWordWrap(True)

        file_splitter = QSplitter(Qt.Orientation.Horizontal)

        self.dir_tree_widget = QTreeWidget()
        self.dir_tree_widget.setHeaderHidden(True)

        right_file_widget = QWidget()
        right_file_layout = QVBoxLayout(right_file_widget)
        right_file_layout.setContentsMargins(0, 0, 0, 0)

        self.file_table_widget = QTableWidget()
        self.file_table_widget.setColumnCount(5)
        self.file_table_widget.setHorizontalHeaderLabels(["文件名", "大小", "类型", "修改时间", "权限"])
        self.file_table_widget.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.file_table_widget.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.file_table_widget.verticalHeader().setVisible(False)
        self.file_table_widget.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self.file_table_widget.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.Interactive)
        self.file_table_widget.setAlternatingRowColors(True)

        file_button_layout = QHBoxLayout()
        self.upload_btn = QPushButton("上传文件...")
        self.download_btn = QPushButton("下载选中")
        self.edit_btn = QPushButton("编辑选中")
        file_button_layout.addWidget(self.upload_btn)
        file_button_layout.addWidget(self.download_btn)
        file_button_layout.addWidget(self.edit_btn)

        right_file_layout.addWidget(self.file_table_widget, 1)
        right_file_layout.addLayout(file_button_layout)

        file_splitter.addWidget(self.dir_tree_widget)
        file_splitter.addWidget(right_file_widget)
        file_splitter.setSizes([100, 500])

        file_browser_layout.addWidget(self.current_path_label)
        file_browser_layout.addWidget(file_splitter, 1)

        # --- Tab 2: 命令 (修改) ---
        self.commands_widget = QWidget()
        commands_layout = QVBoxLayout(self.commands_widget)

        self.command_scroll_area = QScrollArea()
        self.command_scroll_area.setWidgetResizable(True)
        self.command_scroll_area_content = QWidget()
        # --- (修改) 切换到 QGridLayout ---
        self.command_cards_layout = QGridLayout(self.command_scroll_area_content)
        self.command_cards_layout.setAlignment(Qt.AlignmentFlag.AlignTop)
        self.command_scroll_area.setWidget(self.command_scroll_area_content)

        commands_layout.addWidget(self.command_scroll_area)

        # (新增) 右键菜单
        self.commands_widget.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.commands_widget.customContextMenuRequested.connect(self.on_command_context_menu)

        self.file_tab_control.addTab(file_browser_widget, "文件")
        self.file_tab_control.addTab(self.commands_widget, "命令")

        file_tabs_layout.addWidget(self.file_tab_control)

        # --- 连接信号 ---
        self.file_table_widget.itemDoubleClicked.connect(self.on_file_item_double_clicked)
        self.dir_tree_widget.itemExpanded.connect(self.on_tree_item_expanded)
        self.dir_tree_widget.currentItemChanged.connect(self.on_tree_item_selected)

        self.download_btn.clicked.connect(self.start_download_file)
        self.upload_btn.clicked.connect(self.start_upload_file)
        self.edit_btn.clicked.connect(self.start_edit_file)

        # (新增) 加载命令
        self.load_commands()

    # --- (新增) 命令选项卡方法 ---
    def on_command_context_menu(self, pos):
        menu = QMenu(self)
        add_action = menu.addAction("添加命令...")

        action = menu.exec(self.commands_widget.mapToGlobal(pos))

        if action == add_action:
            self.on_add_command(None)  # (修改) 传入 None 表示新建

    def on_add_command(self, old_name=None):
        """添加或编辑命令。 old_name=None 表示新建。"""
        command_data = None
        if old_name:
            all_commands = self.settings.value("commands", {})
            command_data = all_commands.get(old_name)
            if not command_data:
                self.show_error.emit("错误", "找不到要编辑的命令。")
                return

        dialog = CommandDialog(command_data, self)
        if dialog.exec() == QDialog.Accepted:
            data = dialog.get_data()
            name = data.get('name')
            if not name:
                self.show_warning.emit("名称无效", "命令名称不能为空。")
                return

            commands = self.settings.value("commands", {})

            # 检查重名，除非是自己
            if name != old_name and name in commands:
                self.show_warning.emit("名称冲突", "该名称的命令已存在。")
                return

            # 如果重命名了，删除旧的
            if old_name and old_name != name and old_name in commands:
                del commands[old_name]

            commands[name] = data
            self.settings.setValue("commands", commands)
            self.load_commands()  # 刷新 UI

    # (修改)
    def load_commands(self):
        # 清空现有卡片
        # (修复) 正确清空 QGridLayout
        while self.command_cards_layout.count():
            item = self.command_cards_layout.takeAt(0)
            widget = item.widget()
            if widget:
                widget.deleteLater()

        commands = self.settings.value("commands", {})

        # (修改) 动态网格布局，每行 4 个
        col_count = 4
        row = 0
        col = 0

        for name, data in sorted(commands.items()):
            card = QPushButton(name)
            card.setToolTip(data.get('command', ''))
            card.setObjectName(name)  # (修复)

            # (修改) 使用 functools.partial 来正确捕获 data
            card.clicked.connect(functools.partial(self.on_command_card_clicked, data))

            # (新增) 添加右键菜单
            card.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
            # --- (修复) 传递 card 对象, 而不是依赖 self.sender() ---
            card.customContextMenuRequested.connect(
                functools.partial(self.on_command_card_context_menu, card)
            )

            self.command_cards_layout.addWidget(card, row, col)

            col += 1
            if col >= col_count:
                col = 0
                row += 1

    # (新增)
    @Slot(QPushButton, QPoint)  # (修复) 接收 QPushButton 和 QPoint
    def on_command_card_context_menu(self, card, pos):  # (修复)
        """单个命令卡片的右键菜单"""
        # card = self.sender() # (修复) 不再使用 sender
        if not card:
            return

        name = card.objectName()  # (修复)

        menu = QMenu(self)
        edit_action = menu.addAction("编辑...")
        delete_action = menu.addAction("删除")

        action = menu.exec(card.mapToGlobal(pos))

        if action == edit_action:
            self.on_add_command(old_name=name)  # 传入 old_name 来编辑
        elif action == delete_action:
            self.on_delete_command(name)

    # (新增)
    def on_delete_command(self, name):
        reply = QMessageBox.question(
            self, "确认删除",
            f"你确定要删除命令 '{name}' 吗？",
            QMessageBox.Yes | QMessageBox.No, QMessageBox.No
        )

        if reply == QMessageBox.Yes:
            commands = self.settings.value("commands", {})
            if name in commands:
                del commands[name]
                self.settings.setValue("commands", commands)
                self.load_commands()  # 刷新 UI

    def on_command_card_clicked(self, command_data):
        command = command_data.get('command', '')
        if command_data.get('add_cr', True):
            command += "\n"  # 添加回车符

        self.send_to_terminal.emit(command)

    # --- (修改) 文件选项卡方法 ---
    def on_connection_success(self):
        """由会话在连接成功时调用"""
        self.current_path = "/"
        self.setup_file_tree()
        self.start_list_files(self.current_path)

    def start_list_files(self, path):
        """在工作线程中列出文件 (用于表格)"""
        self.current_path_label.setText(f"路径: {path} (加载中...)")
        self.file_table_widget.clearContents()
        self.file_table_widget.setRowCount(0)
        self.request_list_files.emit(path)  # (修改) 发出信号

    @Slot(list, str)
    def on_file_list_result(self, file_list, error_message):
        """文件列表获取完成时由 worker 信号触发 (用于表格)"""
        self.current_path_label.setText(f"路径: {self.current_path}")

        if error_message:
            self.show_error.emit("SFTP 错误", f"无法列出文件: {error_message}")
            if self.current_path != "/":
                self.current_path = os.path.dirname(self.current_path.rstrip('/')) or '/'
                tree_item = self.find_tree_item_by_path(self.current_path)
                if tree_item:
                    self.dir_tree_widget.setCurrentItem(tree_item)
                else:
                    self.start_list_files(self.current_path)
            return

        self.file_table_widget.clearContents()
        self.file_table_widget.setRowCount(0)

        dirs = [f for f in file_list if f["is_dir"]]
        files = [f for f in file_list if not f["is_dir"]]

        dirs.sort(key=lambda x: x['name'])
        files.sort(key=lambda x: x['name'])

        row_count = 0

        if self.current_path != "/":
            self.file_table_widget.insertRow(row_count)
            item_name = QTableWidgetItem(".. (返回)")
            item_name.setData(Qt.ItemDataRole.UserRole, {"is_dir": True, "is_parent": True})
            self.file_table_widget.setItem(row_count, 0, item_name)
            self.file_table_widget.setItem(row_count, 1, QTableWidgetItem(""))
            self.file_table_widget.setItem(row_count, 2, QTableWidgetItem("目录"))
            self.file_table_widget.setItem(row_count, 3, QTableWidgetItem(""))
            self.file_table_widget.setItem(row_count, 4, QTableWidgetItem(""))
            row_count += 1

        for f in dirs:
            self.file_table_widget.insertRow(row_count)
            item_name = QTableWidgetItem(f"📁 {f['name']}")
            item_name.setData(Qt.ItemDataRole.UserRole, {"is_dir": True, "name": f['name']})
            item_size = QTableWidgetItem("")
            item_type = QTableWidgetItem(f['type'])
            item_mtime = QTableWidgetItem(f['mtime'])
            item_perms = QTableWidgetItem(f['perms'])
            self.file_table_widget.setItem(row_count, 0, item_name)
            self.file_table_widget.setItem(row_count, 1, item_size)
            self.file_table_widget.setItem(row_count, 2, item_type)
            self.file_table_widget.setItem(row_count, 3, item_mtime)
            self.file_table_widget.setItem(row_count, 4, item_perms)
            row_count += 1

        for f in files:
            self.file_table_widget.insertRow(row_count)
            item_name = QTableWidgetItem(f"📄 {f['name']}")
            item_name.setData(Qt.ItemDataRole.UserRole, {"is_dir": False, "name": f['name']})
            item_size = QTableWidgetItem(f"{f['size'] // 1024} KB" if f['size'] > 1024 else f"{f['size']} B")
            item_type = QTableWidgetItem(f['type'])
            item_mtime = QTableWidgetItem(f['mtime'])
            item_perms = QTableWidgetItem(f['perms'])
            self.file_table_widget.setItem(row_count, 0, item_name)
            self.file_table_widget.setItem(row_count, 1, item_size)
            self.file_table_widget.setItem(row_count, 2, item_type)
            self.file_table_widget.setItem(row_count, 3, item_mtime)
            self.file_table_widget.setItem(row_count, 4, item_perms)
            row_count += 1

        self.file_table_widget.resizeColumnToContents(0)
        self.file_table_widget.resizeColumnToContents(1)
        self.file_table_widget.resizeColumnToContents(2)

    def on_file_item_double_clicked(self, item):
        row = item.row()
        data_item = self.file_table_widget.item(row, 0)
        data = data_item.data(Qt.ItemDataRole.UserRole)
        if not data:
            return

        if data.get("is_dir"):
            new_path = ""
            if data.get("is_parent"):
                new_path = os.path.dirname(self.current_path.rstrip('/')) or '/'
            else:
                dir_name = data.get("name")
                new_path = os.path.join(self.current_path, dir_name).replace("\\", "/")

            item_to_select = self.find_tree_item_by_path(new_path)
            if item_to_select:
                self.dir_tree_widget.setCurrentItem(item_to_select)
                self.dir_tree_widget.expandItem(item_to_select)
            else:
                self.current_path = new_path
                self.start_list_files(self.current_path)
        else:
            self.start_edit_file()

    def setup_file_tree(self):
        self.dir_tree_widget.clear()
        root_item = QTreeWidgetItem(self.dir_tree_widget, ["/"])
        root_item.setData(0, Qt.ItemDataRole.UserRole, {"path": "/", "populated": False})
        root_item.addChild(QTreeWidgetItem(["加载中..."]))
        self.dir_tree_widget.expandItem(root_item)

    @Slot(QTreeWidgetItem)
    def on_tree_item_expanded(self, item):
        data = item.data(0, Qt.ItemDataRole.UserRole)
        if data and not data.get("populated"):
            path = data.get("path")
            self.request_list_dirs.emit(path)  # (修改) 发出信号

    @Slot(QTreeWidgetItem, QTreeWidgetItem)
    def on_tree_item_selected(self, item, previous_item):
        if item is None:
            return
        data = item.data(0, Qt.ItemDataRole.UserRole)
        path = data.get("path")

        if path and self.current_path != path:
            self.current_path = path
            self.start_list_files(path)

    @Slot(str, list, str)
    def on_tree_dir_list_result(self, parent_path, dir_list, error):
        parent_item = self.find_tree_item_by_path(parent_path)
        if not parent_item:
            return

        parent_item.takeChildren()

        if error:
            parent_item.addChild(QTreeWidgetItem([f"错误: {error}"]))
        else:
            for dir_name in dir_list:
                new_path = os.path.join(parent_path, dir_name).replace("\\", "/")
                child_item = QTreeWidgetItem(parent_item, [dir_name])
                child_item.setData(0, Qt.ItemDataRole.UserRole, {"path": new_path, "populated": False})
                child_item.addChild(QTreeWidgetItem(["加载中..."]))

        data = parent_item.data(0, Qt.ItemDataRole.UserRole)
        data["populated"] = True
        parent_item.setData(0, Qt.ItemDataRole.UserRole, data)

    def find_tree_item_by_path(self, path):
        iterator = QTreeWidgetItemIterator(self.dir_tree_widget)
        while iterator.value():
            item = iterator.value()
            data = item.data(0, Qt.ItemDataRole.UserRole)
            if data and data.get("path") == path:
                return item
            iterator += 1
        return None

    def start_download_file(self):
        selected_row = self.file_table_widget.currentRow()
        if selected_row < 0:
            self.show_warning.emit("未选择", "请先选择一个要下载的文件。")
            return

        data_item = self.file_table_widget.item(selected_row, 0)
        data = data_item.data(Qt.ItemDataRole.UserRole)

        if data.get("is_dir"):
            self.show_warning.emit("无法下载", "无法下载目录。")
            return

        file_name = data.get("name")
        remote_path = os.path.join(self.current_path, file_name).replace("\\", "/")

        local_path, _ = QFileDialog.getSaveFileName(self, "保存文件", file_name)

        if local_path:
            self.request_download.emit(remote_path, local_path)

    @Slot(str)
    def on_download_success(self, message):
        self.show_message.emit("下载完成", message)

    @Slot(str)
    def on_download_failed(self, error):
        self.show_error.emit("下载失败", error)

    def start_upload_file(self):
        local_path, _ = QFileDialog.getOpenFileName(self, "选择要上传的文件")
        if not local_path:
            return

        file_name = os.path.basename(local_path)
        remote_path = os.path.join(self.current_path, file_name).replace("\\", "/")

        self.request_upload.emit(local_path, remote_path)

    @Slot(str)
    def on_upload_success(self, message):
        self.show_message.emit("上传完成", message)
        self.start_list_files(self.current_path)

    @Slot(str)
    def on_upload_failed(self, error):
        self.show_error.emit("上传失败", error)

    def start_edit_file(self):
        selected_row = self.file_table_widget.currentRow()
        if selected_row < 0:
            self.show_warning.emit("未选择", "请先选择一个要编辑的文件。")
            return

        data_item = self.file_table_widget.item(selected_row, 0)
        data = data_item.data(Qt.ItemDataRole.UserRole)

        if data.get("is_dir"):
            self.show_warning.emit("无法编辑", "无法编辑目录。")
            return

        file_name = data.get("name")
        self.editing_remote_path = os.path.join(self.current_path, file_name).replace("\\", "/")
        self.request_fetch_content.emit(self.editing_remote_path)

    @Slot(str)
    def on_file_content_fetched(self, content):
        if self.editor_dialog:
            self.editor_dialog.close()

        self.editor_dialog = TextEditorDialog(content, self)
        self.editor_dialog.accepted.connect(self.on_editor_save)
        self.editor_dialog.show()

    @Slot(str)
    def on_file_content_failed(self, error):
        self.show_error.emit("编辑失败", error)
        self.editing_remote_path = None

    def on_editor_save(self):
        if not self.editor_dialog or not self.editing_remote_path:
            return

        new_content = self.editor_dialog.get_text()
        remote_path = self.editing_remote_path

        self.request_save_content.emit(remote_path, new_content)

        self.editor_dialog.close()
        self.editor_dialog = None
        self.editing_remote_path = None

    @Slot(str)
    def on_file_save_success(self, message):
        self.show_message.emit("保存成功", message)
        self.start_list_files(self.current_path)

    @Slot(str)
    def on_file_save_failed(self, error):
        self.show_error.emit("保存失败", error)


# --- (新增) 会话管理器 ---
class SessionManager(QObject):
    """
    管理所有活动的 SSH 会话。
    """
    # 信号 (发往 MainWindow)
    session_added = Signal(str, QWidget, QWidget, QWidget)  # name, terminal, status, files
    session_closed = Signal(QWidget, QWidget, QWidget)  # terminal, status, files

    connection_failed = Signal(str)
    show_message = Signal(str, str)
    show_error = Signal(str, str)
    show_warning = Signal(str, str)

    def __init__(self, settings, parent=None):
        super().__init__(parent)
        self.settings = settings  # (新增) 共享 QSettings
        self.sessions = []  # 存储 (SshWorker, QThread, TerminalBridge)

    @Slot(dict)
    def create_session(self, account_data):
        # 1. 创建所有对象
        worker = SshWorker()
        thread = QThread()
        bridge = TerminalBridge()

        terminal_view = QWebEngineView()
        web_channel = QWebChannel(terminal_view.page())
        terminal_view.page().setWebChannel(web_channel)
        web_channel.registerObject("py_backend", bridge)
        terminal_view.setHtml(TERMINAL_HTML, baseUrl=QUrl("qrc:///"))

        status_widget = StatusMonitorWidget()
        # (修改) 传入 settings
        file_browser_widget = BottomPaneWidget(self.settings)

        # 2. 移动 worker 到线程
        worker.moveToThread(thread)

        # 3. 连接信号

        # Worker -> Bridge (终端)
        worker.term_read.connect(bridge.on_term_read)
        worker.shell_ready.connect(bridge.on_shell_ready)

        # Bridge -> Worker (终端)
        bridge.bridge_term_write.connect(worker.term_write)
        bridge.bridge_resize_shell.connect(worker.resize_shell)
        bridge.bridge_js_loaded.connect(worker.js_loaded)

        # Worker -> Status Widget
        worker.status_update.connect(status_widget.on_status_update)

        # Worker -> File Browser (数据)
        worker.file_list_result.connect(file_browser_widget.on_file_list_result)
        worker.tree_dir_list_result.connect(file_browser_widget.on_tree_dir_list_result)
        worker.download_success.connect(file_browser_widget.on_download_success)
        worker.download_failed.connect(file_browser_widget.on_download_failed)
        worker.upload_success.connect(file_browser_widget.on_upload_success)
        worker.upload_failed.connect(file_browser_widget.on_upload_failed)
        worker.file_content_fetched.connect(file_browser_widget.on_file_content_fetched)
        worker.file_content_failed.connect(file_browser_widget.on_file_content_failed)
        worker.file_save_success.connect(file_browser_widget.on_file_save_success)
        worker.file_save_failed.connect(file_browser_widget.on_file_save_failed)

        # File Browser -> Worker (请求)
        file_browser_widget.request_list_files.connect(worker.list_files)
        file_browser_widget.request_list_dirs.connect(worker.list_dirs_for_tree)
        file_browser_widget.request_download.connect(worker.download_file)
        file_browser_widget.request_upload.connect(worker.upload_file)
        # --- (修复) 修正方法名称 ---
        file_browser_widget.request_fetch_content.connect(worker.fetch_file_content)
        file_browser_widget.request_save_content.connect(worker.save_file_content)

        # (新增) File Browser -> Bridge (发送命令)
        file_browser_widget.send_to_terminal.connect(bridge.term_write)

        # File Browser -> MainWindow (消息)
        file_browser_widget.show_message.connect(self.show_message)
        file_browser_widget.show_error.connect(self.show_error)
        file_browser_widget.show_warning.connect(self.show_warning)

        # 4. 存储会话对象
        session = {
            "worker": worker,
            "thread": thread,
            "bridge": bridge,
            "terminal": terminal_view,
            "status": status_widget,
            "files": file_browser_widget,  # (修改) 现在是 BottomPaneWidget
            "web_channel": web_channel,  # 防止被垃圾回收
            "account_name": account_data.get('name', 'Session')  # (新增) 存储账户名
        }
        self.sessions.append(session)

        # 5. 连接 Worker 的生命周期信号
        worker.connection_success.connect(
            lambda ssh_client: self.on_session_connected(session, ssh_client)
        )
        worker.connection_failed.connect(
            lambda error: self.on_session_failed(session, error)
        )

        # 6. 启动线程和连接
        thread.start()
        worker.start_connection(account_data)

        # 7. 立即将会话小部件添加到 MainWindow
        self.session_added.emit(
            account_data.get('name', 'Session'),
            terminal_view,
            status_widget,
            file_browser_widget
        )

    def on_session_connected(self, session, ssh_client):
        """会话连接成功"""
        session["worker"].start_shell(ssh_client)
        session["worker"].start_monitoring()
        session["files"].on_connection_success()  # "files" 现在是 BottomPaneWidget

    def on_session_failed(self, session, error):
        """会话连接失败"""
        self.connection_failed.emit(error)  # 转发给 MainWindow
        self.close_session_widgets(
            session["terminal"],
            session["status"],
            session["files"]
        )

    @Slot(QWidget, QWidget, QWidget)
    def close_session_widgets(self, terminal_widget, status_widget, file_widget):
        """
        由 MainWindow 调用 (当标签被关闭时) 或连接失败时。
        """
        session_to_remove = None
        for session in self.sessions:
            if session["terminal"] == terminal_widget:
                session_to_remove = session
                break

        if session_to_remove:
            worker = session_to_remove["worker"]
            thread = session_to_remove["thread"]

            # 安全地关闭 worker 和线程
            QMetaObject.invokeMethod(worker, "close", Qt.QueuedConnection)
            thread.quit()
            thread.wait(2000)  # 等待线程 2 秒

            # 从列表中移除
            self.sessions.remove(session_to_remove)

            # 告诉 MainWindow 移除小部件
            self.session_closed.emit(
                session_to_remove["terminal"],
                session_to_remove["status"],
                session_to_remove["files"]
            )
            print(f"Session closed. Active sessions: {len(self.sessions)}")


# --- (新增) 同步管理器 (Worker) ---
class SyncManager(QObject):
    """
    在后台线程中处理 API 请求
    """
    login_success = Signal(str, str, str)  # (修改) server_url, token, username
    register_success = Signal()
    sync_failure = Signal(str)

    # --- (修复) 信号必须发送 str, 不能发送 dict ---
    download_success = Signal(str, bool)  # (修改) json_str, ask_confirmation
    upload_success = Signal()

    # (新增)
    def __init__(self):
        super().__init__()
        self.is_running = True

    def _get_headers(self, token):
        return {"Authorization": f"Bearer {token}"}

    @Slot(str, str, str)
    def login(self, server_url, username, password):
        if not self.is_running: return
        try:
            url = f"{server_url}/login"
            response = requests.post(url, json={"username": username, "password": password}, timeout=5)
            if response.status_code == 200:
                token = response.json().get('access_token')
                self.login_success.emit(server_url, token, username)  # (修改)
            else:
                self.sync_failure.emit(response.json().get("msg", "登录失败"))
        except Exception as e:
            if self.is_running: self.sync_failure.emit(f"连接服务器失败: {e}")

    @Slot(str, str, str)
    def register(self, server_url, username, password):
        if not self.is_running: return
        try:
            url = f"{server_url}/register"
            response = requests.post(url, json={"username": username, "password": password}, timeout=5)
            if response.status_code == 201:
                self.register_success.emit()
            else:
                self.sync_failure.emit(response.json().get("msg", "注册失败"))
        except Exception as e:
            if self.is_running: self.sync_failure.emit(f"连接服务器失败: {e}")

    # --- (修复) 槽函数必须接收 str, 不能接收 dict ---
    @Slot(str, str, str)  # (修改)
    def upload_accounts(self, server_url, token, accounts_json_str):
        if not self.is_running: return
        try:
            url = f"{server_url}/api/accounts"
            headers = self._get_headers(token)
            # (修改) 直接发送 JSON 字符串
            response = requests.post(url, data=accounts_json_str, headers=headers, timeout=5)
            if response.status_code == 200:
                self.upload_success.emit()
            else:
                if self.is_running: self.sync_failure.emit(f"上传失败: {response.status_code}")
        except Exception as e:
            if self.is_running: self.sync_failure.emit(f"上传失败: {e}")

    @Slot(str, str, bool)  # (修改)
    def download_accounts(self, server_url, token, ask_confirmation):
        if not self.is_running: return
        try:
            url = f"{server_url}/api/accounts"
            headers = self._get_headers(token)
            response = requests.get(url, headers=headers, timeout=5)
            if response.status_code == 200:
                # (修改) 返回原始 JSON 文本，而不是解析后的 dict
                accounts_json_str = response.text
                self.download_success.emit(accounts_json_str, ask_confirmation)  # (修改)
            else:
                if self.is_running: self.sync_failure.emit(f"下载失败: {response.status_code}")
        except Exception as e:
            if self.is_running: self.sync_failure.emit(f"下载失败: {e}")

    # (新增)
    @Slot()
    def close(self):
        self.is_running = False


# --- 主窗口 ---
class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("小龙女她爸自用 SSH 客户端 ")
        self.setGeometry(100, 100, 1000, 700)
        self.setFixedSize(1500, 1200)

        self.settings = QSettings("MySshApp", "SshApp")

        # (新增) 配置文件管理
        self.sync_username = self.settings.value("sync/username")
        if self.sync_username:
            self.active_profile_key = f"accounts_{self.sync_username}"
        else:
            self.active_profile_key = "accounts_local"  # 默认为本地

        # (新增) 会话管理器
        self.session_manager = SessionManager(self.settings)  # (修改) 传入 settings

        # (新增) UI 占位符
        self.terminal_tab_widget = None  # QTabWidget
        self.status_stack = None  # QStackedWidget
        self.file_stack = None  # QStackedWidget

        self.account_name_label = None  # (修改) 重命名
        self.connection_info_label = None  # (新增)

        self.accounts_list_widget = None
        self.add_account_btn = None
        # (移除) self.edit_account_btn = None
        # (移除) self.delete_account_btn = None
        self.import_btn = None
        self.export_btn = None
        self.sync_btn = None  # (新增)

        # --- (新增) 同步管理器 ---
        self.sync_manager = SyncManager()
        self.sync_thread = QThread()
        self.sync_manager.moveToThread(self.sync_thread)
        self.sync_manager.download_success.connect(self.on_download_sync_success)
        self.sync_manager.upload_success.connect(self.on_upload_sync_success)
        self.sync_manager.sync_failure.connect(self.on_sync_failure)
        self.sync_thread.start()

        # --- 连接会话管理器信号 ---
        self.session_manager.session_added.connect(self.on_session_added)
        self.session_manager.session_closed.connect(self.on_session_closed)
        self.session_manager.connection_failed.connect(self.on_connection_failed)
        self.session_manager.show_message.connect(self.show_message_box)
        self.session_manager.show_error.connect(self.show_error_box)
        self.session_manager.show_warning.connect(self.show_warning_box)

        # --- 设置 UI 布局 ---
        self.setup_ui()

        # --- (新增) 添加状态栏 ---
        self.statusBar().showMessage("准备就绪")

        # --- 加载已保存的账户 ---
        self.load_accounts()

        # --- (移除) 启动时自动同步 ---
        # self.trigger_download_sync()

    def setup_ui(self):

        # --- 1. 左侧面板 (状态和账户) ---
        left_panel_widget = QWidget()
        left_panel_layout = QVBoxLayout(left_panel_widget)
        left_panel_widget.setFixedWidth(240)

        # (修改) 减小 VBox 布局的整体间距和边距
        left_panel_layout.setSpacing(5)
        left_panel_layout.setContentsMargins(5, 5, 5, 5)

        # --- (修改) 添加账户名称标签 ---
        self.account_name_label = QLabel("未连接")
        font_bold = self.account_name_label.font()
        font_bold.setBold(True)
        font_bold.setPointSize(14)
        self.account_name_label.setFont(font_bold)
        self.account_name_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.account_name_label.setWordWrap(True)
        left_panel_layout.addWidget(self.account_name_label)

        # --- (新增) 添加连接信息标签 ---
        self.connection_info_label = QLabel("")
        font_small = self.connection_info_label.font()
        font_small.setPointSize(10)
        self.connection_info_label.setFont(font_small)
        self.connection_info_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.connection_info_label.setWordWrap(True)
        left_panel_layout.addWidget(self.connection_info_label)

        # (修改) 状态监视器现在是一个堆叠小部件
        self.status_stack = QStackedWidget()
        # --- (修复) 使用 StatusMonitorWidget 作为空白占位符 ---
        self.blank_status_widget = StatusMonitorWidget()
        self.blank_status_widget.setEnabled(False)
        self.status_stack.addWidget(self.blank_status_widget)
        left_panel_layout.addWidget(self.status_stack)

        # --- (新增) 分割线 ---
        separator = QFrame()
        separator.setFrameShape(QFrame.Shape.HLine)
        separator.setFrameShadow(QFrame.Shadow.Sunken)
        separator.setContentsMargins(0, 2, 0, 2)  # (修改) 减小外边距
        left_panel_layout.addWidget(separator)

        # --- (修改) 账户列表标题栏 ---
        account_list_header_layout = QHBoxLayout()
        account_list_header_layout.addWidget(QLabel("账户列表"))
        account_list_header_layout.addStretch()
        self.add_account_btn = QPushButton("+")
        self.add_account_btn.setStyleSheet("""
                    QPushButton {
                        min-width: 26px;
                        max-width: 26px;
                        min-height: 26px;
                        max-height: 26px;
                        font-size: 15px; /* 控制 '+' 号的大小 */
                        font-weight: bold; /* 让 '+' 号粗一点 */
                    }
                """)
        account_list_header_layout.addWidget(self.add_account_btn)
        left_panel_layout.addLayout(account_list_header_layout)

        # --- (修改) 让列表拉伸 ---
        self.accounts_list_widget = QListWidget()
        self.accounts_list_widget.setAlternatingRowColors(True)
        # --- (新增) 启用多选 ---
        self.accounts_list_widget.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
        # --- (新增) 启用账户右键菜单 ---
        self.accounts_list_widget.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        left_panel_layout.addWidget(self.accounts_list_widget, 1)  # (修改) 添加 stretch factor 1

        # --- (移除) "添加/编辑/删除" 按钮 ---
        # account_btn_layout = QHBoxLayout() ... (已移除)

        # --- (修改) 导入/导出按钮 ---
        import_export_layout = QHBoxLayout()
        self.import_btn = QPushButton("导入")
        self.export_btn = QPushButton("导出")
        import_export_layout.addWidget(self.import_btn)
        import_export_layout.addWidget(self.export_btn)
        left_panel_layout.addLayout(import_export_layout)

        # --- (新增) 同步按钮 ---
        self.sync_btn = QPushButton("账户同步")  # (修改) 重命名
        left_panel_layout.addWidget(self.sync_btn)

        # --- (移除) left_panel_layout.addStretch(1) ---

        # --- 2. 右侧面板 (终端和文件) ---
        right_panel_widget = QWidget()
        right_layout = QVBoxLayout(right_panel_widget)
        right_layout.setContentsMargins(0, 0, 0, 0)

        # --- (修改) 终端区域 (上) 现在是 QTabWidget ---
        self.terminal_tab_widget = QTabWidget()
        self.terminal_tab_widget.setTabsClosable(True)  # (新增)
        self.terminal_tab_widget.setMovable(True)
        self.terminal_tab_widget.tabBar().setExpanding(False)  # (新增) 标签栏左对齐
        self.terminal_tab_widget.setStyleSheet("QTabWidget::tab-bar { alignment: left; }")  # (新增) 样式表

        # (新增) 当没有标签时显示占位符
        self.placeholder_terminal = QLabel("双击左侧账户以开始连接...")
        self.placeholder_terminal.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.placeholder_terminal.setFont(QFont("Arial", 16))

        # --- (修复) 更改启动时的 UI 布局 ---
        # 我们不再使用 QLabel 占位符，而是使用禁用的文件浏览器
        self.terminal_tab_widget.addTab(self.placeholder_terminal, "欢迎")
        self.terminal_tab_widget.tabBar().setTabButton(0, QTabBar.ButtonPosition.RightSide, None)  # 隐藏第一个的关闭按钮

        # --- (修改) 文件浏览器区域 (下) 现在是 QStackedWidget ---
        self.file_stack = QStackedWidget()
        # --- (修复) 使用 BottomPaneWidget 作为空白占位符 ---
        self.blank_files_widget = BottomPaneWidget(self.settings)
        self.blank_files_widget.setEnabled(False)
        self.file_stack.addWidget(self.blank_files_widget)

        # --- 终端/文件分割器 (垂直) ---
        terminal_file_splitter = QSplitter(Qt.Orientation.Vertical)
        terminal_file_splitter.addWidget(self.terminal_tab_widget)
        terminal_file_splitter.addWidget(self.file_stack)
        terminal_file_splitter.setSizes([400, 300])

        right_layout.addWidget(terminal_file_splitter, 1)

        # --- 3. 主分割器 (左/右) ---
        main_splitter = QSplitter(Qt.Orientation.Horizontal)
        main_splitter.addWidget(left_panel_widget)
        main_splitter.addWidget(right_panel_widget)
        main_splitter.setSizes([240, 760])

        self.setCentralWidget(main_splitter)

        # --- 4. 连接 UI 事件 ---
        self.add_account_btn.clicked.connect(self.on_add_account)
        # (移除) self.edit_account_btn.clicked.connect(self.on_edit_account)
        # (移除) self.delete_account_btn.clicked.connect(self.on_delete_account)
        self.accounts_list_widget.itemDoubleClicked.connect(self.on_account_double_clicked)
        self.accounts_list_widget.customContextMenuRequested.connect(self.on_account_context_menu)  # (新增)

        self.import_btn.clicked.connect(self.on_import_accounts)
        self.export_btn.clicked.connect(self.on_export_accounts)
        self.sync_btn.clicked.connect(self.on_sync_button_clicked)  # (新增)

        # (新增) 标签页切换和关闭
        self.terminal_tab_widget.currentChanged.connect(self.on_tab_changed)
        self.terminal_tab_widget.tabCloseRequested.connect(self.on_tab_close_requested)

    # --- 槽函数 (在 GUI 线程中运行) ---

    @Slot(str, str)
    def show_message_box(self, title, message):
        QMessageBox.information(self, title, message)
        self.statusBar().showMessage(message, 3000)  # (新增)

    @Slot(str, str)
    def show_error_box(self, title, error):
        QMessageBox.critical(self, title, error)
        self.statusBar().showMessage(error, 3000)  # (新增)

    @Slot(str, str)
    def show_warning_box(self, title, warning):
        QMessageBox.warning(self, title, warning)
        self.statusBar().showMessage(warning, 3000)  # (新增)

    @Slot(str, QWidget, QWidget, QWidget)
    def on_session_added(self, name, terminal_widget, status_widget, file_widget):
        """当 SessionManager 创建了一个新会话时调用"""

        # --- (修复) 更改添加小部件的顺序 ---

        # 1. 先将小部件添加到堆叠中
        self.status_stack.addWidget(status_widget)
        self.file_stack.addWidget(file_widget)

        # 2. 移除占位符（如果存在）
        if self.terminal_tab_widget.widget(0) == self.placeholder_terminal:
            self.terminal_tab_widget.removeTab(0)

        # 3. 添加新标签页
        tab_index = self.terminal_tab_widget.addTab(terminal_widget, name)

        # 4. 最后，激活新标签页（这将触发 on_tab_changed）
        self.terminal_tab_widget.setCurrentIndex(tab_index)

    @Slot(QWidget, QWidget, QWidget)
    def on_session_closed(self, terminal_widget, status_widget, file_widget):
        """当 SessionManager 清理了一个会话后调用"""
        self.terminal_tab_widget.removeTab(self.terminal_tab_widget.indexOf(terminal_widget))
        self.status_stack.removeWidget(status_widget)
        self.file_stack.removeWidget(file_widget)

        # 销毁小部件
        terminal_widget.deleteLater()
        status_widget.deleteLater()
        file_widget.deleteLater()

        # 如果没有标签了，添加回占位符
        if self.terminal_tab_widget.count() == 0:
            self.terminal_tab_widget.addTab(self.placeholder_terminal, "欢迎")
            self.terminal_tab_widget.tabBar().setTabButton(0, QTabBar.ButtonPosition.RightSide, None)
            self.on_tab_changed(0)  # 重置面板

        self.statusBar().showMessage("准备就绪")  # (新增)

    @Slot(str)
    def on_connection_failed(self, error_message):
        """当会话连接失败时调用"""
        self.show_error_box("连接失败", f"无法连接: {error_message}")
        # SessionManager 应该已经处理了失败会话的关闭

    @Slot(int)
    def on_tab_changed(self, index):
        """当用户切换标签页时"""
        if index < 0:  # (新增) 如果所有标签都关闭了
            self.account_name_label.setText("未连接")
            self.connection_info_label.setText("")
            self.status_stack.setCurrentWidget(self.blank_status_widget)
            self.file_stack.setCurrentWidget(self.blank_files_widget)
            self.statusBar().showMessage("准备就绪")  # (新增)
            return

        current_widget = self.terminal_tab_widget.widget(index)
        if current_widget == self.placeholder_terminal:
            self.account_name_label.setText("未连接")
            self.connection_info_label.setText("")
            self.status_stack.setCurrentWidget(self.blank_status_widget)
            self.file_stack.setCurrentWidget(self.blank_files_widget)
            self.statusBar().showMessage("准备就绪")  # (新增)
            return

        # 找到与此终端小部件关联的会话
        for session in self.session_manager.sessions:
            if session["terminal"] == current_widget:
                self.status_stack.setCurrentWidget(session["status"])
                self.file_stack.setCurrentWidget(session["files"])

                # --- (修改) 设置两个标签 ---
                account_name = session.get("account_name", "已连接")
                self.account_name_label.setText(account_name)

                if session["worker"].ssh_client and session["worker"].ssh_client.get_transport():
                    try:
                        conn_info = (
                                session["worker"].ssh_client.get_transport().get_username() + "@" +
                                session["worker"].ssh_client.get_transport().getpeername()[0]
                        )
                        self.connection_info_label.setText(conn_info)
                        self.statusBar().showMessage(f"已连接到 {account_name}")  # (新增)
                    except Exception as e:
                        print(f"设置标签文本时出错: {e}")
                        self.connection_info_label.setText("已连接")
                        self.statusBar().showMessage(f"已连接到 {account_name}")  # (新增)
                else:
                    self.connection_info_label.setText("正在连接...")
                    self.statusBar().showMessage(f"正在连接到 {account_name}...")  # (新增)
                break

    @Slot(int)
    def on_tab_close_requested(self, index):
        """当用户点击标签上的 'x' 时"""
        terminal_widget = self.terminal_tab_widget.widget(index)

        # 找到对应的会话并关闭它
        # SessionManager 将发出 session_closed 信号，然后我们将在这里清理 UI
        for session in self.session_manager.sessions:
            if session["terminal"] == terminal_widget:
                self.session_manager.close_session_widgets(
                    session["terminal"],
                    session["status"],
                    session["files"]
                )
                break

    # --- (修改) 账户管理方法，使用 self.active_profile_key ---
    def load_accounts(self):
        accounts = self.settings.value(self.active_profile_key, {})  # (修改)
        self.accounts_list_widget.clear()

        for name, data in sorted(accounts.items()):
            item = QListWidgetItem(name)
            item.setData(Qt.ItemDataRole.UserRole, data)
            self.accounts_list_widget.addItem(item)

    def save_accounts(self, accounts):
        self.settings.setValue(self.active_profile_key, accounts)  # (修改)
        self.load_accounts()
        # (移除) 不再自动上传
        # self.trigger_upload_sync()

    # (新增)
    @Slot(QPoint)
    def on_account_context_menu(self, pos):
        item = self.accounts_list_widget.itemAt(pos)
        if not item:  # Clicked on empty space
            return

        menu = QMenu(self)
        edit_action = menu.addAction("编辑...")
        delete_action = menu.addAction("删除")

        action = menu.exec(self.accounts_list_widget.mapToGlobal(pos))

        if action == edit_action:
            self.on_edit_account(item)  # Pass the item
        elif action == delete_action:
            self.on_delete_account(item)  # Pass the item

    # (修改)
    def on_add_account(self):
        dialog = AccountDialog(None, self)
        if dialog.exec() == QDialog.Accepted:
            new_data = dialog.get_data()
            name = new_data.get('name')
            if not name:
                self.show_warning_box("名称无效", "账户名称不能为空。")
                return

            accounts = self.settings.value(self.active_profile_key, {})  # (修改)
            if name in accounts:
                self.show_warning_box("名称冲突", "该名称的账户已存在。")
                return

            accounts[name] = new_data
            self.save_accounts(accounts)

    # (修改)
    def on_edit_account(self, item=None):
        selected_item = item if item else self.accounts_list_widget.currentItem()
        if not selected_item:
            self.show_warning_box("未选择", "请先选择一个要编辑的账户。")
            return

        old_name = selected_item.text()
        account_data = selected_item.data(Qt.ItemDataRole.UserRole)

        dialog = AccountDialog(account_data, self)
        if dialog.exec() == QDialog.Accepted:
            edited_data = dialog.get_data()
            new_name = edited_data.get('name')

            if not new_name:
                self.show_warning_box("名称无效", "账户名称不能为空。")
                return

            accounts = self.settings.value(self.active_profile_key, {})  # (修改)

            if old_name != new_name and new_name in accounts:
                self.show_warning_box("名称冲突", "该名称的账户已存在。")
                return

            if old_name in accounts:
                del accounts[old_name]
            accounts[new_name] = edited_data

            self.save_accounts(accounts)

    # (修改)
    def on_delete_account(self, item=None):
        selected_item = item if item else self.accounts_list_widget.currentItem()
        if not selected_item:
            self.show_warning_box("未选择", "请先选择一个要删除的账户。")
            return

        name = selected_item.text()
        reply = QMessageBox.question(
            self, "确认删除",
            f"你确定要删除账户 '{name}' 吗？",
            QMessageBox.Yes | QMessageBox.No, QMessageBox.No
        )

        if reply == QMessageBox.Yes:
            accounts = self.settings.value(self.active_profile_key, {})  # (修改)
            if name in accounts:
                del accounts[name]
                self.save_accounts(accounts)

    def on_import_accounts(self):
        # 1. (修改) 将 getOpenFileName 改为 getOpenFileNames (复数)
        #    并修改对话框标题
        paths, _ = QFileDialog.getOpenFileNames(
            self,
            "导入账户 (可多选)",  # 修改了标题
            "",
            "JSON 文件 (*.json)"
        )

        # 2. (修改) 检查返回的 'paths' 列表是否为空
        if not paths:
            return

        # 3. (修改) 将这些变量移到循环外部，用于最终统计
        current_accounts = self.settings.value(self.active_profile_key, {})
        imported_count = 0
        skipped_count = 0
        failed_files = []

        # 4. (新增) 循环处理所有被选中的文件路径
        for path in paths:
            try:
                with open(path, 'r', encoding='utf-8') as f:
                    loaded_data = json.load(f)

                accounts_to_process = []

                # --- 以下是你的原始导入逻辑，现在嵌套在循环内 ---
                if isinstance(loaded_data, dict) and 'name' in loaded_data and 'host' in loaded_data:
                    # 格式 1: 单个 FinalShell 账户对象
                    accounts_to_process.append(loaded_data)
                elif isinstance(loaded_data, list):
                    # 格式 2: FinalShell 账户对象列表
                    accounts_to_process = loaded_data
                elif isinstance(loaded_data, dict):
                    # 格式 3: 应用自己的导出格式 (字典)
                    for name, data in loaded_data.items():
                        if name not in current_accounts:
                            current_accounts[name] = data
                            imported_count += 1
                        else:
                            skipped_count += 1
                    # (修改) 处理完这个文件，继续下一个文件
                    continue
                else:
                    raise ValueError(f"无法识别的 JSON 格式: {os.path.basename(path)}")

                # --- (修改) 这部分逻辑现在只处理格式 1 和 2 ---
                for fs_account in accounts_to_process:
                    if isinstance(fs_account, dict) and 'name' in fs_account and 'host' in fs_account:
                        name = fs_account.get('name')
                        if name not in current_accounts:
                            new_account = {
                                'name': name,
                                'host': fs_account.get('host'),
                                'port': str(fs_account.get('port', 22)),
                                'user': fs_account.get('user_name', 'root'),
                                'pass_b64': '',
                                'key_path': ''
                            }
                            current_accounts[name] = new_account
                            imported_count += 1
                        else:
                            skipped_count += 1

            except Exception as e:
                # 5. (新增) 记录失败的文件
                print(f"导入文件 {path} 失败: {e}")
                failed_files.append(os.path.basename(path))

        # 6. (修改) 将保存和显示消息移到循环外部
        if imported_count > 0:
            self.save_accounts(current_accounts)

        # 7. (新增) 创建一个导入总结
        summary_message = []
        if imported_count > 0:
            summary_message.append(f"成功导入 {imported_count} 个新账户。")
        if skipped_count > 0:
            summary_message.append(f"跳过了 {skipped_count} 个名称已存在的账户。")
        if failed_files:
            summary_message.append(f"以下文件导入失败: {', '.join(failed_files)}")

        if not summary_message:
            summary_message.append("没有找到新的账户来导入。")

        # 统一添加 FinalShell 密码警告
        if imported_count > 0:
            summary_message.append("\n\n注意：从 FinalShell 导入的账户密码无法解密，\n"
                                   "请手动 '编辑' 账户并重新输入密码。")

        self.show_message_box("导入完成", "\n".join(summary_message))

    # --- (修改) 导出选定账户 ---
    def on_export_accounts(self):
        """导出所有选中的账户到 JSON 文件"""

        # (修改) 仅获取选中的项目
        selected_items = self.accounts_list_widget.selectedItems()

        if not selected_items:
            self.show_warning_box("无账户", "请在列表中选择一个或多个要导出的账户。")
            return

        accounts_to_export = {}
        for item in selected_items:
            name = item.text()
            data = item.data(Qt.ItemDataRole.UserRole)
            if data:
                accounts_to_export[name] = data

        if not accounts_to_export:
            # 这不应该发生，但作为安全检查
            self.show_warning_box("无数据", "无法获取所选账户的数据。")
            return

        path, _ = QFileDialog.getSaveFileName(self, "导出账户", "my_ssh_accounts.json", "JSON 文件 (*.json)")
        if not path:
            return

        try:
            with open(path, 'w', encoding='utf-8') as f:
                json.dump(accounts_to_export, f, indent=4, ensure_ascii=False)
            self.show_message_box("导出成功", f"已成功导出 {len(accounts_to_export)} 个账户到:\n{path}")
        except Exception as e:
            self.show_error_box("导出失败", f"无法写入文件: {e}")

    def on_account_double_clicked(self, item):
        account_data = item.data(Qt.ItemDataRole.UserRole)
        if not account_data:
            return

        # (修改) 调用会话管理器来创建会话
        self.session_manager.create_session(account_data)

    # --- (修改) 同步功能槽 ---
    def on_sync_button_clicked(self):
        # --- (修复) 传入 self.sync_manager ---
        dialog = SyncDialog(self.settings, self.sync_manager, self)  # (修改)
        # (修改) 连接到手动信号
        dialog.upload_requested.connect(self.trigger_upload_sync)
        dialog.download_requested.connect(self.trigger_download_sync)
        dialog.login_success.connect(self.on_sync_login_success)  # (新增)
        dialog.logout_requested.connect(self.on_sync_logout)  # (新增)
        dialog.exec()

    @Slot(str, str, str)  # (修改)
    def on_sync_login_success(self, server_url, token, username):
        """
        登录成功后，切换到该用户的配置文件
        """
        self.statusBar().showMessage(f"登录为 {username}。")
        self.sync_username = username
        self.active_profile_key = f"accounts_{username}"  # (修改)
        self.load_accounts()  # 加载该用户的配置文件

        # (新增) 登录后自动下载
        self.trigger_download_sync(ask_confirmation=True)

    @Slot()
    def on_sync_logout(self):
        """登出后，切换回本地配置文件"""
        self.statusBar().showMessage("已登出，切换到本地配置。")
        self.sync_username = None
        self.active_profile_key = "accounts_local"
        self.load_accounts()  # 加载本地配置文件

    def trigger_upload_sync(self):
        """将本地账户上传到服务器"""
        server_url = self.settings.value("sync/server_url")
        token = self.settings.value("sync/token")
        if not server_url or not token:
            self.show_warning_box("未登录", "请先登录到你的同步服务器。")
            return

        accounts = self.settings.value(self.active_profile_key, {})  # (修改)
        accounts_json_str = json.dumps(accounts)

        self.statusBar().showMessage("正在上传同步...")
        QMetaObject.invokeMethod(
            self.sync_manager, "upload_accounts",
            Qt.QueuedConnection,
            Q_ARG(str, server_url),
            Q_ARG(str, token),
            Q_ARG(str, accounts_json_str)
        )

    def trigger_download_sync(self, ask_confirmation=False):  # (修改)
        """从服务器下载账户"""
        server_url = self.settings.value("sync/server_url")
        token = self.settings.value("sync/token")
        if not server_url or not token:
            if not ask_confirmation:  # 启动时静默失败
                print("未配置同步或未登录，跳过。")
            else:
                self.show_warning_box("未登录", "请先登录到你的同步服务器。")
            return

        self.statusBar().showMessage("正在从服务器同步...")
        # (修改) 传递确认标志
        QMetaObject.invokeMethod(
            self.sync_manager, "download_accounts",
            Qt.QueuedConnection,
            Q_ARG(str, server_url),
            Q_ARG(str, token),
            Q_ARG(bool, ask_confirmation)
        )

    @Slot(str, bool)  # (修改)
    def on_download_sync_success(self, remote_accounts_json_str, ask_confirmation):
        """
        下载成功，执行合并逻辑
        """
        self.statusBar().showMessage("同步下载成功，正在合并...")

        try:
            remote_accounts = json.loads(remote_accounts_json_str)
            if not isinstance(remote_accounts, dict):
                raise ValueError("下载的数据格式不是一个字典")
        except Exception as e:
            self.on_sync_failure(f"合并失败: {e}")
            return

        # (修改) 你的逻辑：云端覆盖本地
        reply = QMessageBox.Yes
        if ask_confirmation:  # (修改)
            # (修复) 确保 self.sync_username 有值
            profile_name = self.sync_username if self.sync_username else "本地"
            reply = QMessageBox.question(
                self, "确认下载",
                f"从云端发现了 {len(remote_accounts)} 个账户。\n"
                f"这将覆盖你当前配置文件 ({profile_name}) 的所有本地账户，是否继续？",
                QMessageBox.Yes | QMessageBox.No, QMessageBox.No
            )

        if reply == QMessageBox.Yes:
            self.save_accounts(remote_accounts)  # (修改) 直接保存，不再触发上传
            self.statusBar().showMessage("同步下载成功！", 3000)
        else:
            self.statusBar().showMessage("下载已取消", 3000)

    @Slot()
    def on_upload_sync_success(self):
        self.statusBar().showMessage("账户已成功同步到云端！", 3000)

    @Slot(str)
    def on_sync_failure(self, error):
        self.show_error_box("同步失败", error)
        if "token" in error.lower() or "过期" in error:
            # 可能是令牌过期了，清除它
            self.settings.remove("sync/token")

    def closeEvent(self, event: QCloseEvent):
        """关闭窗口时清理所有会话"""
        # 复制会话列表以进行安全迭代
        all_sessions = list(self.session_manager.sessions)
        for session in all_sessions:
            self.session_manager.close_session_widgets(
                session["terminal"],
                session["status"],
                session["files"]
            )

        # (新增) 清理同步线程
        QMetaObject.invokeMethod(self.sync_manager, "close", Qt.QueuedConnection)
        self.sync_thread.quit()
        self.sync_thread.wait()

        event.accept()


# --- 启动应用程序 ---
if __name__ == "__main__":
    app = QApplication(sys.argv)
    window = MainWindow()
    window.show()
    sys.exit(app.exec())

