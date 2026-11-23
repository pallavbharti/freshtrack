FROM python:3.12-slim AS build

ENV PIP_NO_CACHE_DIR=1 PIP_DISABLE_PIP_VERSION_CHECK=1
WORKDIR /app

RUN python -m venv /venv
ENV PATH="/venv/bin:$PATH"

COPY requirements.lock .
RUN pip install --only-binary :all: --require-hashes -r requirements.lock

COPY app ./app
COPY scripts ./scripts
COPY data ./data
RUN python scripts/train_model.py --data data/sales.csv --out models/forecast_model.joblib \
 && python scripts/check_model.py models/forecast_model.metrics.json

FROM python:3.12-slim

ARG APP_VERSION=dev
ENV PATH="/venv/bin:$PATH" \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    APP_VERSION=${APP_VERSION}

RUN groupadd --system app && useradd --system --gid app --no-create-home app

WORKDIR /app
COPY --from=build /venv /venv
COPY --from=build /app/app ./app
COPY --from=build /app/data ./data
COPY --from=build /app/models ./models

USER app
EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=3s --start-period=20s \
  CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8000/health')" || exit 1

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
