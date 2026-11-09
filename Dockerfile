FROM python:3.12-slim AS runtime
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 OMP_NUM_THREADS=1
WORKDIR /app
COPY pyproject.toml README.md LICENSE requirements-runtime-lock.txt ./
COPY src ./src
RUN python -m pip install --no-cache-dir -r requirements-runtime-lock.txt && python -m pip install --no-cache-dir --no-deps . && useradd --uid 10001 --create-home loanflow
USER 10001:10001
ENV LOANFLOW_RELEASES=/releases
EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=3s --start-period=10s CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/readyz',timeout=2)"
CMD ["uvicorn", "loanflow.service:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "1", "--no-access-log", "--timeout-keep-alive", "5", "--limit-concurrency", "32"]
