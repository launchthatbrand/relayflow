FROM python:3.12-slim
RUN useradd --uid 10001 --create-home --shell /usr/sbin/nologin app
WORKDIR /app
COPY pyproject.toml README.md ./
COPY api ./api
RUN pip install --no-cache-dir .
WORKDIR /app/api
USER 10001
EXPOSE 8000
ENTRYPOINT ["sh", "/app/api/bin/serve.sh"]
CMD ["api"]
