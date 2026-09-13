# wim-api — WIM Online middleware (serve.py)
FROM python:3.13-slim
WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY serve.py .

# serve.py serves API only in this container (static handled by sales-app/nginx)
EXPOSE 8000
CMD ["python", "serve.py"]