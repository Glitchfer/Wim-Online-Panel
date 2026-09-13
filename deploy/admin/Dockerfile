# admin-panel — WIM Online admin app
FROM python:3.13-slim
WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY admin-server.py .

EXPOSE 8001
CMD ["python", "admin-server.py"]