# 施工现场 AI 智能监控系统 —— CPU 部署镜像(无需 GPU)
FROM python:3.11-slim

# OpenCV 运行所需的系统库(libGL / glib)
RUN apt-get update && apt-get install -y --no-install-recommends \
        libgl1 libglib2.0-0 \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# 先单独安装 CPU 版 PyTorch(体积大, 独立一层便于构建缓存)
RUN pip install --no-cache-dir torch torchvision \
        --index-url https://download.pytorch.org/whl/cpu

# 再安装其余依赖
COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

# 拷贝应用(代码 + 模型 + 样本清单 + 预渲染结果)
COPY . .

EXPOSE 8000
# 启动 Web 服务; 所有样本已预渲染, 启动即秒开
CMD ["python", "-m", "uvicorn", "webapp.server:app", "--host", "0.0.0.0", "--port", "8000"]
