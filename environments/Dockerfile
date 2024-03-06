ARG NAUTOBOT_VERSION
ARG PYTHON_VER
FROM ghcr.io/nautobot/nautobot:${NAUTOBOT_VERSION}-py${PYTHON_VER} as nautobot-base

USER 0

RUN apt-get update && \
    apt-get upgrade -y && \
    apt-get autoremove -y && \
    apt-get clean all && \
    rm -rf /var/lib/apt/lists/* && \
    pip --no-cache-dir install --upgrade pip wheel

FROM ghcr.io/nautobot/nautobot-dev:${NAUTOBOT_VERSION}-py${PYTHON_VER} as builder

CMD ["nautobot-server", "runserver", "0.0.0.0:8080", "--insecure"]

RUN apt-get update && \
    apt-get upgrade -y && \
    apt-get autoremove -y && \
    apt-get clean all && \
    rm -rf /var/lib/apt/lists/*

COPY ../pyproject.toml ../poetry.lock /source/
COPY ../plugins /source/plugins
# COPY ../packages /source/packages

# Install the nautobot project to include Nautobot
RUN cd /source && \
    poetry install --no-interaction --no-ansi && \
    mkdir /tmp/dist && \
    poetry export --without-hashes -o /tmp/dist/requirements.txt

# -------------------------------------------------------------------------------------
# Build Apps in plugins folder
# -------------------------------------------------------------------------------------
RUN for plugin in /source/plugins/*; do \
        cd $plugin && \
        poetry build && \
        cp dist/*.whl /tmp/dist; \
    done

COPY ../jobs /opt/nautobot/jobs
# COPY ../metrics /opt/nautobot/metrics
COPY ../config/nautobot_config.py /opt/nautobot/nautobot_config.py

WORKDIR /source

###################################

# -------------------------------------------------------------------------------------
# Final Image
# -------------------------------------------------------------------------------------
FROM nautobot-base as nautobot

# Copy from base the required python libraries and binaries
COPY --from=builder /tmp/dist /tmp/dist
COPY --from=builder /opt/nautobot /opt/nautobot
# COPY ../packages /source/packages

RUN grep -v /source/plugins /tmp/dist/requirements.txt > /tmp/dist/new_requirements.txt && \
    pip install -r /tmp/dist/new_requirements.txt && \
    pip install /tmp/dist/*.whl && \
    rm -rf /source /tmp/dist && \
    chown -R nautobot:nautobot /opt/nautobot

USER nautobot
