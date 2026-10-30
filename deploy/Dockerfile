FROM python:3.12-slim-bookworm

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PLAYWRIGHT_BROWSERS_PATH=/ms-playwright

# pg_dump for nightly backups (Supabase runs Postgres 17; Debian ships 15, so use PGDG),
# and Xvfb so Chrome can run headed (much harder for bot managers to spot than headless).
RUN apt-get update \
 && apt-get install -y --no-install-recommends ca-certificates curl gnupg xvfb xauth fonts-liberation \
 && install -d /usr/share/postgresql-common/pgdg \
 && curl -fsSL https://www.postgresql.org/media/keys/ACCC4CF8.asc -o /usr/share/postgresql-common/pgdg/apt.postgresql.org.asc \
 && echo "deb [signed-by=/usr/share/postgresql-common/pgdg/apt.postgresql.org.asc] https://apt.postgresql.org/pub/repos/apt bookworm-pgdg main" \
      > /etc/apt/sources.list.d/pgdg.list \
 && apt-get update \
 && apt-get install -y --no-install-recommends postgresql-client-17 \
 && rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY pyproject.toml README.md ./
COPY tcgpings ./tcgpings
RUN pip install . \
 && patchright install --with-deps chrome \
 && rm -rf /var/lib/apt/lists/*

COPY deploy/entrypoint.sh /usr/local/bin/entrypoint.sh
RUN chmod +x /usr/local/bin/entrypoint.sh \
 && useradd --create-home --uid 1000 app && mkdir -p /app/data && chown app /app/data
USER app

HEALTHCHECK --interval=30s --timeout=5s --start-period=60s --retries=3 CMD ["python", "-m", "tcgpings", "health"]
ENTRYPOINT ["/usr/local/bin/entrypoint.sh"]
CMD ["run"]
