FROM python:3.12-slim
ENV PYTHONUNBUFFERED=1 PIP_NO_CACHE_DIR=1 TZ=Asia/Shanghai
WORKDIR /app
COPY requirements.txt .
RUN pip install -r requirements.txt -i https://mirrors.aliyun.com/pypi/simple/
COPY app ./app
COPY scripts ./scripts
COPY demo ./demo
EXPOSE 8080
CMD ["python", "-m", "app.main"]
