FROM python:3.11-slim
WORKDIR /app
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PORT=8080 STORAGE_MODE=none
COPY requirements-cloud.txt .
RUN pip install --no-cache-dir -r requirements-cloud.txt
COPY ticketpilot/ ./ticketpilot/
COPY data/knowledge_base.json ./data/knowledge_base.json
COPY artifacts/model_numpy.npz artifacts/vectorizer.joblib ./artifacts/
RUN useradd -r -u 10001 appuser && mkdir -p /app/state && chown -R appuser:appuser /app
USER appuser
EXPOSE 8080
CMD ["sh","-c","exec uvicorn ticketpilot.api:app --host 0.0.0.0 --port ${PORT:-8080}"]
