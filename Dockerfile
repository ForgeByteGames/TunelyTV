FROM python:3.12-slim
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
WORKDIR /app
# gosu lets the entrypoint set permissions on Railway's root-owned volume,
# then run the application as an unprivileged user.
RUN apt-get update && apt-get install -y --no-install-recommends gosu \
 && rm -rf /var/lib/apt/lists/* \
 && groupadd --gid 10001 tunely \
 && useradd --uid 10001 --gid 10001 --home-dir /app tunely
COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt
COPY server.py billing.py discovery.py licensing.py ./
COPY site/ ./site/
COPY railway-entrypoint.sh /usr/local/bin/tunely-entrypoint
RUN chmod +x /usr/local/bin/tunely-entrypoint \
 && mkdir -p /app/instance \
 && chown -R tunely:tunely /app
ENV TUNELY_DB=/app/instance/tunelytv.db TUNELY_ENV=production
EXPOSE 8765
ENTRYPOINT ["/usr/local/bin/tunely-entrypoint"]
