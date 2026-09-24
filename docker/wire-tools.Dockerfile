ARG UV_VERSION=0.12.18
FROM ghcr.io/astral-sh/uv:${UV_VERSION} AS uv

FROM ubuntu:26.04

ARG DEBIAN_FRONTEND=noninteractive
ARG UV_VERSION=0.12.18
ARG IMAGE_REVISION=unknown

ENV DEBIAN_FRONTEND=noninteractive
ENV UV_PYTHON_INSTALL_DIR=/opt/uv-python
ENV PATH="/opt/wire/.venv/bin:/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin"
# Keep runtime bytecode caches out of the root-owned /opt/wire tree so the
# non-root `wire` user does not need write access to the sources.
ENV PYTHONPYCACHEPREFIX=/tmp/wire-pycache

LABEL org.opencontainers.image.source="https://github.com/VibeBB/wire-agent" \
      org.opencontainers.image.licenses="BSD-3-Clause" \
      org.opencontainers.image.revision="${IMAGE_REVISION}" \
      wire.uv.version="${UV_VERSION}"

COPY --from=uv /uv /uvx /usr/local/bin/

ARG DRAWIO_DESKTOP_VERSION=31.4.5
ARG DRAWIO_DESKTOP_SHA256=296729ee18f781dc82deb757de2b3399fbe04fe0ddad3093909013e707ee2ae4

# Serve every suite from the master archive: it carries the same -security
# pocket, while security.ubuntu.com can briefly publish an index ahead of its
# pool and 404 packages the index still lists.
RUN grep -q "^URIs: http://security\.ubuntu\.com/ubuntu" \
        /etc/apt/sources.list.d/ubuntu.sources \
    && sed -i "s|^URIs: http://security\.ubuntu\.com/ubuntu/|URIs: http://archive.ubuntu.com/ubuntu/|" \
        /etc/apt/sources.list.d/ubuntu.sources \
    && apt-get -o Acquire::Retries=5 update \
    && apt-get -o Acquire::Retries=5 install --no-install-recommends -y \
        ca-certificates \
        curl \
        fonts-ipafont \
        git \
        libasound2t64 \
        xvfb \
    && curl -fsSL -o /tmp/drawio.deb \
        "https://github.com/jgraph/drawio-desktop/releases/download/v${DRAWIO_DESKTOP_VERSION}/drawio-amd64-${DRAWIO_DESKTOP_VERSION}.deb" \
    && echo "${DRAWIO_DESKTOP_SHA256}  /tmp/drawio.deb" | sha256sum -c - \
    && apt-get install -y /tmp/drawio.deb \
    && rm /tmp/drawio.deb \
    && rm -rf /var/lib/apt/lists/*

RUN uv python install 3.12 \
    && uv venv --python 3.12 /opt/wire/.venv

COPY pyproject.toml uv.lock /opt/wire/
COPY src /opt/wire/src
COPY plugins/wire /opt/wire/plugins/wire
COPY scripts/e2e_authoring.py /opt/wire/scripts/e2e_authoring.py
COPY examples /opt/wire/examples

RUN cd /opt/wire \
    && uv export --frozen --no-dev --no-emit-project --format requirements-txt \
        --output-file /tmp/wire-requirements.txt \
    && uv pip install --python /opt/wire/.venv/bin/python \
        --requirement /tmp/wire-requirements.txt \
    && uv pip install --python /opt/wire/.venv/bin/python --no-deps /opt/wire \
    && python -c "import wire, pydantic; print(wire.__version__)" \
    && python -m wire doctor \
    && rm -f /tmp/wire-requirements.txt

RUN if ! getent group wire >/dev/null; then groupadd wire; fi \
    && if getent passwd 1000 >/dev/null; then \
         existing="$(getent passwd 1000 | cut -d: -f1)"; \
         if [ "$existing" != wire ]; then usermod --login wire --gid wire "$existing"; fi; \
         usermod --home /home/wire wire; \
       else \
         useradd --uid 1000 --gid wire --create-home --shell /bin/bash wire; \
       fi \
    && mkdir -p /home/wire/.cache \
    && chown -R wire:wire /home/wire

WORKDIR /opt/wire
USER wire

# Smoke-check the deterministic pipeline on the shipped example at build
# time; a failing gate fails the image build.
RUN python /opt/wire/scripts/e2e_authoring.py \
      --contract /opt/wire/examples/sensor-harness/sensor-harness.contract.json \
      --out /tmp/smoke-out \
    && python - <<'PY'
import json
report = json.load(open("/tmp/smoke-out/design-report.json", encoding="utf-8"))
assert report["verdict"] == "pass", report
print("image smoke check: verdict pass")
PY
