# nautobot-docker-compose

This is a set of instructions for an example Docker Compose file to help with getting started. You may use this and also make edits. If you would like to contribute different options for a Docker Compose, you may submit a PR to have included. See the Contributing section.

## Docker Compose

The provided Docker Compose makes use of environment variables to control what is to be used. This is tightly coupled with the Docker image that is provided on Docker Hub.

## Getting Started

### Git

1. Clone this repository to your Nautobot host
2. Have [Docker](https://docs.docker.com/get-docker/) and [Docker Compose](https://docs.docker.com/compose/install/) installed
3. Copy `.env.example` to `.env`
4. Make update to the `.env` file for your environment. Updates are IMPORTANT!
5. Update the `.env` to be only available for the user, `sudo chmod 0600 .env`
6. Run `docker-compose up` to start the environment

### Copy Files

There is no code specifically in this repository. Just a few examples to get started. 

1. Copy the `docker-compose.yml` file contents to your own `docker-compose.yml`
2. Copy the `.env.example` file contents to your own `.env` file and make the updates
3. Update the `.env` to be only available for the user, `sudo chmod 0600 .env`

## Super User Account

### Use Environment

The Docker container has an entrypoint that allows you to create a super user by the usage of Environment variables. This can be done by updating the example `.env` file environment option of `NAUTOBOT_CREATE_SUPERUSER` to `True`. This will then use the information supplied to create the super user.

### Container

After the containers have started:

1. Enter the bash shell for the `nautobot` container
2. Execute `nautobot-server createsuperuser`

## Plugins

For plugin documentation, see the [docs](docs/plugins.md).
