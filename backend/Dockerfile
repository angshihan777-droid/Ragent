FROM python:3.12-slim

WORKDIR /app

# 先装依赖再拷代码，利用镜像层缓存加速重复构建
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# 生产镜像不带 --reload；开发态的热重载由 docker-compose 的 command 覆盖。
RUN useradd --create-home --uid 10001 appuser \
    && mkdir -p /tmp/fastembed_cache \
    && chown -R appuser:appuser /tmp/fastembed_cache

COPY --chown=appuser:appuser app ./app
USER appuser

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
