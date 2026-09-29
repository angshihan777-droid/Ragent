"""FastAPI 应用入口：注册 lifespan 与路由。路由保持薄，逻辑在 service。"""
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.db import lifespan
from app.routers import config, documents, health, projects, requests, threads

app = FastAPI(title="Ragent", lifespan=lifespan)

# 前端默认走 Vite 同源代理 /api，不需要 CORS；这里只给直连后端的本地开发页放行。
# 不用 "*"：任意网页都能调本机 API（项目无鉴权），白名单把风险收窄到本地前端。
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
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
