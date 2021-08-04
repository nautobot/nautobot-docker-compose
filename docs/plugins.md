# PLUGINS

To add plugins you will need to build a custom container with the plugin installed.

## Getting Started Using Plugins

1. Have [Docker](https://docs.docker.com/get-docker/) and [Docker Compose](https://docs.docker.com/compose/install/) installed on the host
1. Clone this repository to your Nautobot host into the `/opt/nautobot` directory with the user account Nautobot
```
sudo useradd --system --shell /bin/bash --create-home --home-dir /opt/nautobot nautobot
sudo -iu nautobot
git clone https://github.com/nautobot/nautobot-docker-compose.git
```

3. Copy `local.env.example` to `local.env`
```
cp local.env.example local.env
```

4. Make update to the `local.env` file for your environment. Updates are IMPORTANT!
```
vi /opt/nautobot/local.env
```

5. Update the `.env` to be only available for the Nautobot user
```
chmod 0600 local.env
```

6. Move the files from the `plugin_example` directory
```
mv plugin_example/* ./
```

7. Update the file `config/nautobot_config.py` settings of `PLUGINS` and `PLUGINS_CONFIG` to match your configuration updates for the plugins (PLUGINS_CONFIG is optional, if not adjusting from the default settings)
```
vi config/nautobot_config.py
```
8. Update the `./plugin_requirements.txt` file with the Python packages that need to be installed. These will be installed via the `pip install -r plugin_requirements.txt` command (This example file has the Nautobot Onboarding Plugin)
```
vi plugin_requirements.txt
```
1. Create the custom Docker Container, see [Custom Docker Container](#custom-docker-container)
2.  Run `docker-compose build --no-cache` to build the Dockerfile-Plugins (from the file `docker-compose.override.yml`, see below for more details)
3.  Run `docker-compose up` to have the compose package installed

## Custom Docker Container

The first step is to create a custom Docker container that will handle the installation of the packages. The recommendation is to use `Dockerfile-Plugins` as the file name. It can be whatever is meaningful and is not a requirement. The Dockerfile then looks like:

```docker
FROM networktocode/nautobot:1.1.0

COPY ./plugin_requirements.txt /opt/nautobot/
RUN /opt/nautobot/bin/pip install --no-warn-script-location -r /opt/nautobot/plugin_requirements.txt

COPY config/nautobot_config.py /opt/nautobot/nautobot_config.py
RUN nautobot-server post_upgrade
```

## Docker Compose Override

The `docker-compose.override.yml` overrides settings from the primary docker-compose file. In this case there needs to be a new Docker image file that is used to provide the Nautobot container. The key within the `docker-compose.override.yml` file is:

```yaml
    image: "companyname/nautobot-plugins:latest"
    build:
      context: .
      dockerfile: Dockerfile-Plugins
```

This indicates to build the image name `companyname/nautobot-plugins:latest` from the Dockerfile `Dockerfile-Plugins`. Then that image is what is used for the Nautobot container image. Substitute `companyname` with something that is meaningful to your organization.

## Nautobot Configuration

The configuration file is the same file that is used by the Dockerfile in the Nautobot repo. This file should be updated to match what is required for each of the plugins. An example update for the Onboarding Plugin looks like:

```python
# Enable installed plugins. Add the name of each plugin to the list.
PLUGINS = ["nautobot_device_onboarding"]

# Plugins configuration settings. These settings are used by various plugins that the user may have installed.
# Each key in the dictionary is the name of an installed plugin and its value is a dictionary of settings.
PLUGINS_CONFIG = {}
```
