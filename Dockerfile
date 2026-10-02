# syntax=docker/dockerfile:1
FROM python:3.12.14-slim-trixie

LABEL org.opencontainers.image.source="https://github.com/wa200508/airsim-rf" \
      org.opencontainers.image.description="AirSim RF CPU test environment with pinned Sionna RT and ProjectAirSim SDK" \
      org.opencontainers.image.licenses="MIT"

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    MPLBACKEND=Agg \
    MPLCONFIGDIR=/tmp/matplotlib \
    PATH="/opt/airsim-rf/.venv/bin:${PATH}"

# The optional CA mount supports builds behind an HTTPS inspection proxy.
# It is never copied into the image. Ordinary home/CI builds need no secret.
RUN --mount=type=secret,id=proxy_ca,mode=0444 \
    set -eu; \
    sed -i 's|http://deb.debian.org|https://deb.debian.org|g' /etc/apt/sources.list.d/debian.sources; \
    if [ -f /run/secrets/proxy_ca ]; then \
        export SSL_CERT_FILE=/run/secrets/proxy_ca; \
        apt-get -o Acquire::https::CaInfo="$SSL_CERT_FILE" update; \
        apt-get -o Acquire::https::CaInfo="$SSL_CERT_FILE" install -y --no-install-recommends \
            git libllvm19 libatomic1 libgl1 libglib2.0-0t64; \
    else \
        apt-get update; \
        apt-get install -y --no-install-recommends git libllvm19 libatomic1 libgl1 libglib2.0-0t64; \
    fi; \
    rm -rf /var/lib/apt/lists/*

WORKDIR /opt/airsim-rf
COPY --chmod=755 pyproject.toml requirements-lock.txt sources.json ./
COPY --chmod=755 scripts/bootstrap.py scripts/bootstrap.py
COPY --chmod=755 src/ src/
RUN --mount=type=secret,id=proxy_ca \
    set -eu; \
    if [ -f /run/secrets/proxy_ca ]; then \
        export SSL_CERT_FILE=/run/secrets/proxy_ca \
               PIP_CERT=/run/secrets/proxy_ca \
               GIT_SSL_CAINFO=/run/secrets/proxy_ca \
               REQUESTS_CA_BUNDLE=/run/secrets/proxy_ca; \
    fi; \
    /usr/local/bin/python scripts/bootstrap.py; \
    rm -rf /root/.cache/pip; \
    groupadd --gid 10001 rf; \
    useradd --uid 10001 --gid rf --create-home rf; \
    mkdir /work; \
    chown rf:rf /work

# Tests, examples and documentation can change without reinstalling dependencies.
COPY --chmod=755 . .

USER rf
WORKDIR /work
CMD ["python", "-m", "pytest", "/opt/airsim-rf/tests", "-q", "-p", "no:cacheprovider"]
