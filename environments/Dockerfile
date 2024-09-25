ARG NAUTOBOT_VERSION
ARG PYTHON_VER
FROM ghcr.io/nautobot/nautobot-dev:${NAUTOBOT_VERSION}-py${PYTHON_VER} as nautobot-base

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
# RUN for plugin in /source/plugins/*; do \
#         cd $plugin && \
#         poetry build && \
#         cp dist/*.whl /tmp/dist; \
#     done

COPY ../jobs /opt/nautobot/jobs
# COPY ../metrics /opt/nautobot/metrics
COPY ../config/nautobot_config.py /opt/nautobot/nautobot_config.py

WORKDIR /source

###################################

# -------------------------------------------------------------------------------------
# Final Image
# -------------------------------------------------------------------------------------
FROM nautobot-base as nautobot

ARG PYTHON_VER

# Install Poetry manually via its installer script;
# We might be using an older version of Nautobot that includes an older version of Poetry
# and CI and local development may have a newer version of Poetry
# Since this is only used for development and we don't ship this container, pinning Poetry back is not expressly necessary
# We also don't need virtual environments in container
RUN which poetry || curl -sSL https://install.python-poetry.org | python3 - && \
  poetry config virtualenvs.create false

# Copy from base the required python libraries and binaries
COPY --from=builder /tmp/dist /tmp/dist
COPY --from=builder /opt/nautobot /opt/nautobot
COPY --from=builder /usr/local/lib/python${PYTHON_VER}/site-packages /usr/local/lib/python${PYTHON_VER}/site-packages
COPY --from=builder /usr/local/bin /usr/local/bin
# COPY ../packages /source/packages
# Copy in the source code
WORKDIR /source
COPY . /source

ENV INVOKE_NAUTOBOT_DOCKER_COMPOSE_LOCAL=false

# Verify that pyuwsgi was installed correctly, i.e. with SSL support
SHELL ["/bin/bash", "-o", "pipefail", "-c"]
RUN pyuwsgi --cflags | sed 's/ /\n/g' | grep -e "^-DUWSGI_SSL$"

# USER nautobot
