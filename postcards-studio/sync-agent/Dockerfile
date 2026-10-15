FROM python:3.12-slim

WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY agent.py .

ENV PYTHONUNBUFFERED=1 \
    POSTCARDS_DESTINATION=/releases \
    POSTCARDS_APPLICATION="" \
    POSTCARDS_INTERVAL=30

VOLUME ["/releases"]
CMD ["python", "agent.py"]
