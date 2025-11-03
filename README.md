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
