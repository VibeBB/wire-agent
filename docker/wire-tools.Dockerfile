ARG UV_VERSION=0.12.21
ARG UV_DIGEST=sha256:a7aed3216253ee804de3e2d8afa5073baa1a177335345d43845cd4165e43b711
FROM ghcr.io/astral-sh/uv:${UV_VERSION}@${UV_DIGEST} AS uv

FROM debian:13-slim@sha256:a99cfc517144bc59b1978475ec53b46ecabec7e43635402ee5b77cc54cd1b20a

ARG DEBIAN_FRONTEND=noninteractive
ARG UV_VERSION=0.12.21
ARG IMAGE_REVISION=unknown

# Fail the build when the left side of a verification pipe (curl|sha256sum)
# breaks instead of silently passing the right side.
SHELL ["/bin/bash", "-o", "pipefail", "-c"]

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

ARG DRAWIO_DESKTOP_VERSION=31.7.0
ARG DRAWIO_DESKTOP_SHA256=eb9695e208fcc5ccfbfc496aa8ab2f52a273297d83715de2177b231c172c13de

RUN apt-get -o Acquire::Retries=5 update \
    && apt-get -o Acquire::Retries=5 install --no-install-recommends -y \
        ca-certificates \
        curl \
        fonts-ipafont \
        git \
        libasound2t64 \
        xvfb \
        xauth \
    && curl -fsSL --retry 5 --retry-delay 10 --retry-all-errors -o /tmp/drawio.deb \
        "https://github.com/jgraph/drawio-desktop/releases/download/v${DRAWIO_DESKTOP_VERSION}/drawio-amd64-${DRAWIO_DESKTOP_VERSION}.deb" \
    && echo "${DRAWIO_DESKTOP_SHA256}  /tmp/drawio.deb" | sha256sum -c - \
    && apt-get install --no-install-recommends -y /tmp/drawio.deb \
    && rm /tmp/drawio.deb \
    && rm -rf /var/lib/apt/lists/*

# The uv-managed CPython bundles pip with vendored copies of urllib3,
# msgpack, and setuptools that nothing in the image invokes — dependencies
# install via uv and the shipped venv is pip-less — so strip the payload
# instead of shipping unused vulnerable vendored packages.
RUN uv python install 3.12 \
    && rm -rf /opt/uv-python/bin/pip* \
              /opt/uv-python/cpython-*/bin/pip* \
              /opt/uv-python/cpython-*/lib/python3.12/site-packages/pip \
              /opt/uv-python/cpython-*/lib/python3.12/site-packages/pip-*.dist-info \
              /opt/uv-python/cpython-*/lib/python3.12/ensurepip \
    && uv venv --python 3.12 /opt/wire/.venv

COPY pyproject.toml uv.lock /opt/wire/
COPY src /opt/wire/src
COPY plugins/wire /opt/wire/plugins/wire
COPY scripts/e2e_authoring.py /opt/wire/scripts/e2e_authoring.py
COPY examples /opt/wire/examples

WORKDIR /opt/wire

RUN uv export --frozen --no-dev --no-emit-project --format requirements-txt \
        --output-file /tmp/wire-requirements.txt \
    && uv pip install --python /opt/wire/.venv/bin/python \
        --requirement /tmp/wire-requirements.txt \
    && uv pip install --python /opt/wire/.venv/bin/python --no-deps /opt/wire \
    && python -c "import wire, pydantic; print(wire.__version__)" \
    && python -m wire doctor \
    && rm -f /tmp/wire-requirements.txt

# The pinned debian:13-slim digest keeps shipping the deb Trivy flags at
# publish (CVE-2026-103111 libpcre2-8-0). Upgrade just that package inside
# the build so the publish gate stays green.
RUN apt-get -o Acquire::Retries=5 update \
    && apt-get -o Acquire::Retries=5 install -y --no-install-recommends \
        --only-upgrade \
        libpcre2-8-0 \
    && rm -rf /var/lib/apt/lists/*

# Tighten the login.defs umask to 027 (Lynis AUTH-9328): the image has no
# interactive users, so files created at runtime stay group-readable only.
RUN printf 'UMASK 027\n' >> /etc/login.defs

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
