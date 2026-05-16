FROM python:3.12-slim AS base

ENV PYTHONUNBUFFERED=1
WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends curl \
    && rm -rf /var/lib/apt/lists/*


################################
# API stage
################################
FROM base AS api

COPY services/api/requirements.txt /tmp/requirements-api.txt
COPY services/pipeline/requirements.txt /tmp/requirements-pipeline.txt

RUN pip install --no-cache-dir -r /tmp/requirements-api.txt -r /tmp/requirements-pipeline.txt

COPY services/pipeline/app /app/app
COPY services/pipeline/config /app/config
COPY services/api/app /app/api_app

ENV PYTHONPATH=/app

EXPOSE 8000

CMD ["uvicorn", "api_app.main:app", "--host", "0.0.0.0", "--port", "8000"]


################################
# Pipeline stage
################################
FROM base AS pipeline

COPY services/pipeline/requirements.txt /tmp/requirements-pipeline.txt

RUN pip install --no-cache-dir -r /tmp/requirements-pipeline.txt

COPY services/pipeline /app

ENV PYTHONPATH=/app

CMD ["sleep", "infinity"]


################################
# ML Inference stage — radiografías
################################
FROM base AS ml-inference

COPY services/ml-inference/requirements.txt /tmp/requirements-ml.txt

RUN pip install --no-cache-dir -r /tmp/requirements-ml.txt

COPY services/ml-inference /app

ENV PYTHONPATH=/app

EXPOSE 8001

CMD ["uvicorn", "app.app:app", "--host", "0.0.0.0", "--port", "8001"]


################################
# ML Triage stage — modelo tabular
################################
FROM base AS ml-triage

COPY services/ml-triage/requirements.txt /tmp/requirements-ml-triage.txt

RUN pip install --no-cache-dir -r /tmp/requirements-ml-triage.txt

COPY services/ml-triage /app

ENV PYTHONPATH=/app

EXPOSE 8002

CMD ["uvicorn", "app.app:app", "--host", "0.0.0.0", "--port", "8002"]


################################
# Dashboard stage
################################
FROM base AS dashboard

COPY services/dashboard/requirements.txt /tmp/requirements-dashboard.txt

RUN pip install --no-cache-dir -r /tmp/requirements-dashboard.txt

COPY services/dashboard /app

ENV PYTHONPATH=/app

EXPOSE 8501

CMD ["streamlit", "run", "app.py", "--server.port", "8501", "--server.address", "0.0.0.0"]


################################
# Automation stage
################################
FROM base AS automation

COPY services/automation/requirements.txt /tmp/requirements-automation.txt

RUN pip install --no-cache-dir -r /tmp/requirements-automation.txt

COPY services/automation /app

ENV PYTHONPATH=/app

CMD ["python", "-u", "main.py"]