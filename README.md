# MySshApp (简易 SSH 客户端)

一个使用 Python 和 PySide6 构建的、受 FinalShell 启发的简易 SSH 客户端。

本项目包含一个功能丰富的 SSH 客户端 (`ssh_client.py`) 和一个可选的、用于账户云同步的后端服务器 (`sync_server.py`)。

## 核心功能

* **多标签终端**: 支持同时连接和管理多个 VPS 会话。
* **实时状态监控**: 以文本和图形方式显示 CPU、内存、磁盘和系统负载（受 FinalShell 启发）。
* **SFTP 文件管理器**: 支持树状目录导航、文件/目录列表、上传、下载和简单的文本编辑。
* **命令卡片**: 保存你常用的命令片段，一键发送到终端执行。
* **会话管理**:
    * 在本地保存和管理你的 VPS 账户信息。
    * 支持密码和私钥 (`.pem`, `id_rsa`) 两种登录方式。
    * 支持从 FinalShell 导出的 `.json` 文件导入账户。
    * 支持多选导出账户。
* **(可选) 账户云同步**:
    * 配套 `sync_server.py` 后端，可自行搭建。
    * 支持多配置文件（每个同步账户完全独立）。
    * 手动上传（覆盖云端）和下载（覆盖本地）账户列表，防止误删。

## 项目结构

```plaintext
MySshApp/
├── ssh_client.py       # 客户端主程序
└── sync_server.py      # (可选) 同步服务器的 Flask 后端
```
## 1. 如何运行客户端 (ssh_client.py)

这是你的本地电脑上需要运行的主程序。

### 1.1 安装依赖

你需要 Python 3 和以下库。请在你的本地电脑（Windows、Mac 或 Linux）上安装它们：

```bash
# 1. 安装 PySide6 (用于 UI 界面)
pip install PySide6

# 2. 安装 Paramiko (用于 SSH 和 SFTP)
pip install paramiko

# 3. 安装 Requests (用于云同步 API)
pip install requests
```

### 1.2 运行
安装完依赖后，直接运行 ssh_client.py 即可：
```bash
python3 ssh_client.py
```
## 2. (可选) 如何搭建同步服务器 (sync_server.py)

如果你想在多台设备间同步你的 VPS 账户列表，你需要搭建这个后端服务。

### 2.1 VPS 服务器准备

你需要一台有公网 IP 的 VPS (例如 Ubuntu/Debian)。

1.  SSH 登录到你的 VPS。
2.  安装 `python3` 和 `pip`：

    ```bash
    sudo apt update
    sudo apt install python3 python3-pip -y
    ```

3.  创建服务器目录：

    ```bash
    mkdir ~/sync_server
    cd ~/sync_server
    ```

4.  安装服务器所需的 Python 库：

    ```bash
    pip3 install Flask Flask-SQLAlchemy Flask-JWT-Extended passlib
    ```

### 2.2 上传和配置

1.  将 `sync_server.py` 文件上传到你 VPS 的 `~/sync_server` 目录中。
2.  **(极其重要!)** 编辑 `sync_server.py` 文件，修改 `JWT_SECRET_KEY`：

    ```bash
    nano sync_server.py
    ```

3.  找到这一行：

    ```python
    app.config['JWT_SECRET_KEY'] = 'your-super-secret-random-key-change-me'
    ```

    把 `'your-super-secret-random-key-change-me'` 替换成一个你自己编的、长而随机的字符串。

### 2.3 首次运行 (创建数据库)

1.  在 `~/sync_server` 目录中，运行脚本：

    ```bash
    python3 sync_server.py
    ```

    服务器会启动并显示类似 `* Running on http://1.2.3.4:5000` 的信息。

2.  现在，按 `Ctrl+C` 停止它。
3.  输入 `ls`，你会看到一个新文件 `sync.db` 已经被创建。数据库已准备就绪。

### 2.4 在后台运行

为了让你退出 SSH 后服务器还能继续运行，我们使用 `nohup`：

```bash
nohup python3 sync_server.py > sync.log 2>&1 &
```
### 2.5 打开防火墙

最后，你必须允许外部访问 5000 端口。

**如果你使用 ufw 防火墙:**

```bash
sudo ufw allow 5000/tcp
sudo ufw reload
```
### 2.6 在客户端中使用
打开 MySshApp 客户端，点击左下角的“账户同步”按钮。

在“服务器 URL”中填入你的服务器地址，例如: http://[你的VPS_IP]:5000

输入一个全新的用户名和密码（这是你的同步账户，不是 VPS 账户），点击“注册”。

注册成功后，使用相同的账户信息，点击“登录”。

登录成功后，你就可以使用“上传”和“下载”按钮来手动同步你的 VPS 列表了。

## 3. 如何打包客户端 (创建 .exe 和 .app)

将 `.py` 文件打包成本地应用，最常用的工具是 PyInstaller。

### 3.1 安装 PyInstaller

```bash
pip install pyinstaller
```

### 3.2 打包为 Windows (.exe)
由于我们的应用使用了 PySide6.QtWebEngine（全功能终端），打包过程会比较复杂。

推荐的方法 (使用 .spec 文件):

PyInstaller 可能无法自动找到 QtWebEngine 的所有组件。你需要先生成一个 .spec 文件：
```bash
pyinstaller --noconsole --name MySSshApp ssh_client.py
```
这会生成一个 MySshApp.spec 文件。打开它，你可能需要手动添加 PySide6 的数据：
```bash
# MySshApp.spec

from PyInstaller.utils.hooks import copy_metadata

# ... (已有的 a, pyz, exe 设置) ...

# 添加 PySide6 需要的 binaries
a.binaries += copy_metadata('PySide6')

exe = EXE(pyz,
          a.scripts,
          a.binaries, # 确保 binaries 被添加
          # ... (其余设置) ...
          )
```
然后，使用 .spec 文件进行打包：
```bash
pyinstaller --noconsole --onefile MySshApp.spec
```
如果 QtWebEngine 仍然失败，你可能需要手动添加 QtWebEngineProcess.exe。一个更简单的命令可能是：
```bash
pyinstaller --noconsole --onefile --name MySshApp --add-data "venv\Lib\site-packages\PySide6\QtWebEngineProcess.exe;." ssh_client.py
```

### 3.3 打包为 macOS (.app)

在 macOS 上打包 QtWebEngine 应用是极其困难的，因为它涉及到沙盒、权限和 `QtWebEngineProcess` 辅助程序。

**基础命令 (通常会失败):**

```bash
pyinstaller --windowed --onefile --name MySshApp ssh_client.py
```
推荐的方法 (使用 .spec 和 codesign):

你需要一个 .spec 文件（如上所述）来确保 PySide6 的所有部分被包含。

由于 macOS 的安全策略，QtWebEngineProcess 必须被正确地代码签名才能运行。

你需要一个 Apple 开发者 ID 来进行签名，或者创建一个自签名证书。

打包命令（在有了 .spec 文件后）会是：
```bash
pyinstaller --windowed MySshApp.spec --osx-sign-identity "你的签名ID" --osx-entitlements-file "entitlements.plist"
```
entitlements.plist 文件需要包含允许 JIT 和网络访问的权限。

打包总结: 在 Windows 和 macOS 上打包 QtWebEngine 应用非常复杂，远远超出了简单 pyinstaller 命令的范畴，需要对特定平台的打包和签名有深入的了解。
