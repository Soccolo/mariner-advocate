FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    STREAMLIT_SERVER_HEADLESS=true \
    STREAMLIT_BROWSER_GATHER_USAGE_STATS=false

WORKDIR /app

RUN groupadd --system mariner && \
    useradd --system --gid mariner --create-home mariner

COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

COPY --chown=mariner:mariner mariner_core.py streamlit_app.py ./
COPY --chown=mariner:mariner .streamlit/config.toml ./.streamlit/config.toml

USER mariner

EXPOSE 8501

HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
  CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8501/_stcore/health', timeout=3)"

CMD ["streamlit", "run", "streamlit_app.py", "--server.address=0.0.0.0", "--server.port=8501"]
