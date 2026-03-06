# 邮件营销系统

为销售服务的邮件营销系统：客户表上传、邮件预览（AI 文案 + 图片）、即刻/循环发送，对接 pltplt SMTP。

## 技术栈

- 后端：Python 3.10+ / FastAPI / SQLAlchemy / Alembic
- 前端：React 18 / Vite / React Router / Axios

## 本地开发

### 后端

```bash
cd backend
python -m venv .venv
# Windows: .venv\Scripts\activate
# Linux/macOS: source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env   # 按需修改
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

- 接口文档：http://127.0.0.1:8000/docs  
- 健康检查：http://127.0.0.1:8000/api/health  

### 前端

```bash
cd frontend
npm install
npm run dev
```

- 开发地址：http://localhost:5173  
- 开发时 API 请求通过 Vite 代理到后端 `http://127.0.0.1:8000`（见 `vite.config.js`）

### 数据库迁移（模块 B 及之后）

```bash
cd backend
alembic revision --autogenerate -m "描述"
alembic upgrade head
```

### 默认管理员（首次启动自动创建）

若数据库中无任何用户，首次启动后端会自动创建管理员：**登录名 admin / 密码 Pltplt2026**。生产环境请及时修改密码或通过管理员后台管理用户。

## 项目结构

```
email-marketing/
├── backend/
│   ├── app/
│   │   ├── main.py       # FastAPI 入口
│   │   ├── config.py     # 配置
│   │   ├── database.py   # 数据库会话
│   │   ├── models/       # ORM 模型
│   │   ├── routers/      # 路由
│   │   └── services/     # 业务逻辑
│   ├── alembic/          # 迁移脚本
│   └── requirements.txt
├── frontend/
│   ├── src/
│   │   ├── api/          # API 封装
│   │   ├── components/
│   │   └── pages/
│   └── package.json
└── README.md
```
