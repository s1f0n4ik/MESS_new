FROM python:3.12-slim

WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir --default-timeout=120 --retries 10 -r requirements.txt
COPY app ./app
RUN mkdir -p /data
EXPOSE 8081
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8081", "--proxy-headers"]

