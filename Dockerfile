# ═══════════════════════════════════════════════════
# PENOPLAST ERP+ PRODUCTION DOCKERFILE (NON-ROOT)
# ═══════════════════════════════════════════════════

FROM python:3.12-slim as builder

ENV PYTHONDONTWRITEBYTECODE 1
ENV PYTHONUNBUFFERED 1

WORKDIR /app

RUN apt-get update && apt-get install -y \
    postgresql-client \
    libpq-dev \
    gcc \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --upgrade pip && \
    pip install --no-cache-dir -r requirements.txt

# --- Final Production Stage ---
FROM python:3.12-slim

WORKDIR /app

# Install only runtime dependencies
RUN apt-get update && apt-get install -y \
    libpq5 \
    postgresql-client \
    && rm -rf /var/lib/apt/lists/*

# Copy installed packages from builder
COPY --from=builder /usr/local/lib/python3.12/site-packages/ /usr/local/lib/python3.12/site-packages/
COPY --from=builder /usr/local/bin/ /usr/local/bin/

# Create a non-root user
RUN groupadd -r erpuser && useradd -r -g erpuser erpuser
RUN mkdir -p /app/staticfiles /app/media && chown -R erpuser:erpuser /app

# Copy project files
COPY . .
RUN chown -R erpuser:erpuser /app

USER erpuser

# Static files are collected at runtime via docker-compose command
# (python manage.py collectstatic --no-input)

EXPOSE 8000

# Gunicorn start command (overridden by compose for celery)
CMD ["gunicorn", "erp.wsgi:application", "--bind", "0.0.0.0:8000", "--workers", "3", "--timeout", "120"]
