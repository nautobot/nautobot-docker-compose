# PLUGINS

To add plugins you will need to build a custom container with the plugin installed.

## Getting Started

1. Update the file `config/nautobot_config` `PLUGINS` and  `PLUGINS_CONFIG` to match your configuration updates for the plugins
2. Update the `./plugin_requirements.txt` file with the Python packages that need to be installed. These will be installed via the `pip install -r plugin_requirements.txt` command
3. Run `docker-compose build --no-cache` to build the Dockerfile-Plugins
4. Run `docker-compose up` to have the compose package installed

## Custom Docker Container

The first step is to create a custom Docker container that will handle the installation of the packages. The recommendation is to use `Dockerfile-Plugins` as the file name. It can be whatever is meaningful and is not a requirement. The Dockerfile then looks like:

```docker
FROM networktocode/nautobot:latest

COPY ./plugin_requirements.txt /opt/nautobot/
RUN /opt/nautobot/bin/pip install --no-warn-script-location -r /opt/nautobot/plugin_requirements.txt

COPY config/nautobot_config.py /opt/nautobot/nautobot_config.py
RUN nautobot-server post_upgrade
```

## Docker Compose Override

The `docker-compose.override.yml` overrides settings from the primary docker-compose file. In this case there needs to be a new Docker image file that is used to provide the Nautobot container. The key within the `docker-compose.override.yml` file is:

```yaml
    image: "networktocode/nautobot-plugins:latest"
    build:
      context: .
      dockerfile: Dockerfile-Plugins
```

This indicates to build the image name `networktocode/nautobot-plugins:latest` from the Dockerfile `Dockerfile-Plugins`. Then that image is what is used for the Nautobot container image.

## Nautobot Configuration

The configuration file is the same file that is used by the Dockerfile in the Nautobot repo. This file should be updated to match what is required for each of the plugins. An example update for the Onboarding Plugin looks like:

```python
# Enable installed plugins. Add the name of each plugin to the list.
PLUGINS = ["nautobot_device_onboarding"]

# Plugins configuration settings. These settings are used by various plugins that the user may have installed.
# Each key in the dictionary is the name of an installed plugin and its value is a dictionary of settings.
PLUGINS_CONFIG = {}
```
