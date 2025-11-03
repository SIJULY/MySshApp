import os
from flask import Flask, jsonify, request
from flask_sqlalchemy import SQLAlchemy
from passlib.hash import pbkdf2_sha256 as sha256
from flask_jwt_extended import create_access_token, jwt_required, get_jwt_identity, JWTManager

# --- 配置 ---
app = Flask(__name__)
base_dir = os.path.abspath(os.path.dirname(__file__))

# 配置数据库：我们将使用 SQLite，数据将存储在 'sync.db' 文件中
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///' + os.path.join(base_dir, 'sync.db')
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

# 配置 JWT 密钥：请务必将其更改为一个长而随机的字符串！
app.config['JWT_SECRET_KEY'] = 'your-super-secret-random-key-change-me' 

db = SQLAlchemy(app)
jwt = JWTManager(app)

# --- 数据库模型 ---

class UserModel(db.Model):
    """
    用户模型：存储同步服务的用户信息（不是你的 VPS 账户）
    """
    __tablename__ = 'users'
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(120), unique=True, nullable=False)
    password_hash = db.Column(db.String(120), nullable=False)

class AccountDataModel(db.Model):
    """
    存储用户加密的 VPS 账户数据
    """
    __tablename__ = 'account_data'
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    # 我们将所有账户信息加密并存储为一个 JSON 字符串
    accounts_json = db.Column(db.Text, nullable=True)
    
    owner = db.relationship('UserModel', backref=db.backref('account_data', lazy=True, uselist=False))

# --- 辅助函数 ---

def hash_password(password):
    """哈希密码"""
    return sha256.hash(password)

def verify_password(password, hash):
    """验证密码"""
    return sha256.verify(password, hash)

# --- 认证 API ---

@app.route('/register', methods=['POST'])
def register():
    """
    注册新用户 API
    """
    data = request.get_json()
    username = data.get('username')
    password = data.get('password')

    if not username or not password:
        return jsonify({"msg": "用户名和密码不能为空"}), 400

    if UserModel.query.filter_by(username=username).first():
        return jsonify({"msg": "用户名已存在"}), 400

    # 创建新用户
    new_user = UserModel(
        username=username,
        password_hash=hash_password(password)
    )
    db.session.add(new_user)
    db.session.commit()
    
    # 为新用户创建一个空的账户数据条目
    new_account_data = AccountDataModel(user_id=new_user.id, accounts_json="{}")
    db.session.add(new_account_data)
    db.session.commit()

    return jsonify({"msg": "用户注册成功"}), 201

@app.route('/login', methods=['POST'])
def login():
    """
    登录 API
    """
    data = request.get_json()
    username = data.get('username')
    password = data.get('password')

    user = UserModel.query.filter_by(username=username).first()

    if not user or not verify_password(password, user.password_hash):
        return jsonify({"msg": "用户名或密码错误"}), 401

    # 创建访问令牌
    access_token = create_access_token(identity=user.id)
    return jsonify(access_token=access_token), 200

# --- 同步 API (受保护) ---

@app.route('/api/accounts', methods=['GET'])
@jwt_required()
def get_accounts():
    """
    获取此用户的账户数据
    """
    user_id = get_jwt_identity()
    user_data = AccountDataModel.query.filter_by(user_id=user_id).first()

    if not user_data:
        # 如果数据丢失，自动创建一个
        new_account_data = AccountDataModel(user_id=user_id, accounts_json="{}")
        db.session.add(new_account_data)
        db.session.commit()
        return jsonify({}), 200

    return user_data.accounts_json, 200 # 直接返回 JSON 文本

@app.route('/api/accounts', methods=['POST'])
@jwt_required()
def update_accounts():
    """
    更新（覆盖）此用户的账户数据
    """
    user_id = get_jwt_identity()
    user_data = AccountDataModel.query.filter_by(user_id=user_id).first()
    
    # 获取原始 JSON 文本数据
    accounts_json = request.get_data(as_text=True)

    if not user_data:
        user_data = AccountDataModel(user_id=user_id)
        db.session.add(user_data)
    
    user_data.accounts_json = accounts_json
    db.session.commit()
    
    return jsonify({"msg": "账户数据同步成功"}), 200

# --- 启动服务器 ---
if __name__ == '__main__':
    # 第一次运行时，创建数据库
    with app.app_context():
        db.create_all()
    
    # 运行服务器，监听所有 IP 地址
    app.run(host='0.0.0.0', port=5000, debug=True)

