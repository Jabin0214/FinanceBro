FROM python:3.13-slim

WORKDIR /app

# 安装依赖（单独一层，代码改动时不重新安装）
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# 复制项目代码
COPY . .

CMD ["python", "main.py"]
