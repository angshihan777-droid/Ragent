"""FastAPI 应用入口：注册 lifespan 与路由。路由保持薄，逻辑在 service。"""
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.db import lifespan
from app.middleware.owner import OwnerCookieMiddleware
from app.routers import config, documents, health, metrics, projects, requests, threads

app = FastAPI(title="Ragent", lifespan=lifespan)

# ⚠️ 中间件注册顺序：add_middleware 是往栈顶插，最后注册的最先执行（最外层）。
# 身份中间件必须在 CORS 里层：跨域预检 OPTIONS 由 CORS 直接短路返回，
# 不该经过身份逻辑白发一个 Cookie（预检响应上的 Set-Cookie 浏览器也不会存）。
# 所以先写 Owner、后写 CORS —— 顺序颠倒会让每次预检都生成一个用不上的身份。
app.add_middleware(OwnerCookieMiddleware)

# 前端默认走 Vite 同源代理 /api，不需要 CORS；这里只给直连后端的本地开发页放行。
# 不用 "*"：任意网页都能调本机 API（项目无鉴权），白名单把风险收窄到本地前端。
# allow_credentials=True 是身份 Cookie 跨域可用的前提；⚠️ 它与 allow_origins=["*"]
# 不能共存（浏览器规范禁止），所以这里必须维持白名单，不要图省事改成 "*"。
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# 入口只负责挂载路由，不写业务
app.include_router(health.router)
app.include_router(requests.router)
app.include_router(documents.router)
app.include_router(config.router)
app.include_router(projects.router)
app.include_router(threads.router)
app.include_router(metrics.router)
