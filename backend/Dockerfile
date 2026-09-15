FROM python:3.12-slim

WORKDIR /app

# 先装依赖再拷代码，利用镜像层缓存加速重复构建
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY app ./app

# --reload 便于开发期热重载；生产不用这个 Dockerfile
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--reload"]
