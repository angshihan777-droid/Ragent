"""FastAPI 应用入口：注册 lifespan 与路由。路由保持薄，逻辑在 service。"""
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.db import lifespan
from app.routers import config, documents, health, projects, requests, threads

app = FastAPI(title="Ragent", lifespan=lifespan)

# 本地开发决策：前端 Vite 与后端不同端口(源不同)，浏览器会拦跨域请求，
# 故开放 CORS。单机个人项目只在本地跑，直接放开所有源，不做成配置项。
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
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
