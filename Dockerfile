# FinSent dashboard image. FinBERT (torch + transformers) is optional and large:
#   docker build -t finsent .                          # runtime only, heuristic sentiment fallback
#   docker build -t finsent --build-arg WITH_FINBERT=1 .   # adds FinBERT
FROM python:3.12-slim

ARG WITH_FINBERT=0
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    DASHBOARD_HOST=0.0.0.0 \
    DASHBOARD_PORT=8050

WORKDIR /app

COPY requirements.txt requirements-dev.txt requirements-research.txt ./
RUN pip install --no-cache-dir -r requirements.txt \
    && if [ "$WITH_FINBERT" = "1" ]; then pip install --no-cache-dir -r requirements-research.txt; fi

COPY finsent ./finsent
COPY output/research ./output/research
COPY docs ./docs
COPY README.md ./

RUN useradd --create-home finsent && mkdir -p /app/data && chown -R finsent /app
USER finsent

EXPOSE 8050
HEALTHCHECK --interval=30s --timeout=5s --start-period=60s CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8050/', timeout=4)"
CMD ["python", "-m", "finsent.scripts.run_dashboard"]
