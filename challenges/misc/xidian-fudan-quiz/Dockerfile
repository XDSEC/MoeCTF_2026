# CTF 答题平台镜像
# 构建：docker build -t ctf-platform .
# 运行：docker run -d -p 5000:5000 -e FLAG=moectf{your_flag_here} ctf-platform

FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    FLASK_DEBUG=0 \
    PORT=5000

WORKDIR /app

# 先复制依赖文件，利用 Docker 层缓存加速重建
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# 复制应用代码（本地 __pycache__ / 数据库等已由 .dockerignore 排除）
COPY app.py .
COPY templates ./templates
COPY static ./static

# 使用非 root 用户运行；SQLite 数据库在首次启动时写入 /app/ctf_platform.db
RUN useradd -m -u 1000 ctf && chown -R ctf:ctf /app
USER ctf

EXPOSE 5000

CMD ["python", "app.py"]
