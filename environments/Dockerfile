ARG NAUTOBOT_VERSION="2.3.6"
ARG PYTHON_VER="3.11"
FROM ghcr.io/nautobot/nautobot-dev:${NAUTOBOT_VERSION}-py${PYTHON_VER} AS nautobot

USER 0

CMD ["nautobot-server", "runserver", "0.0.0.0:8080", "--insecure"]

RUN apt-get update && \
    apt-get upgrade -y && \
    apt-get autoremove -y && \
    apt-get clean all && \
    rm -rf /var/lib/apt/lists/* && \
    pip --no-cache-dir install --upgrade pip wheel

COPY ../pyproject.toml ../poetry.lock /source/
COPY ../plugins /source/plugins

# Install the nautobot project to include Nautobot
RUN cd /source && \
    poetry install --no-interaction --no-ansi && \
    mkdir /tmp/dist && \
    poetry export --without-hashes -o /tmp/dist/requirements.txt

# Copy in the source code
WORKDIR /source
COPY . /source
COPY ../jobs /opt/nautobot/jobs
COPY ../config/nautobot_config.py /opt/nautobot/nautobot_config.py

# Install Poetry manually via its installer script;
# We might be using an older version of Nautobot that includes an older version of Poetry
# and CI and local development may have a newer version of Poetry
# Since this is only used for development and we don't ship this container, pinning Poetry back is not expressly necessary
# We also don't need virtual environments in container
RUN which poetry || curl -sSL https://install.python-poetry.org | python3 - && \
  poetry config virtualenvs.create false

ENV INVOKE_NAUTOBOT_DOCKER_COMPOSE_LOCAL=false

# Verify that pyuwsgi was installed correctly, i.e. with SSL support
SHELL ["/bin/bash", "-o", "pipefail", "-c"]
RUN pyuwsgi --cflags | sed 's/ /\n/g' | grep -e "^-DUWSGI_SSL$"
