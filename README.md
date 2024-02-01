# nautobot-docker-compose

Network to Code has an existing published Nautobot Docker Image on Docker Hub. See [here](https://hub.docker.com/repository/docker/networktocode/nautobot). This project uses Docker Compose. The Docker compose file in this project pulls that Nautobot Docker image using the latest stable Nautobot release along with several other Docker images required for Nautobot to function. See the diagram below. This project is for those looking for a multi-container single-node install for Nautobot often coupled with backup & HA capabilities from their hypervisor manager.

![Container Stack](docs/img/container_stack.png)

By default, this project deploys the Nautobot application, a single worker container, Redis containers, and PostgreSQL. It does not deploy NGINX, SSL, or any Nautobot plugins. However, the project is extensible to allow users to tailor it to their specific requirements. For example, if you need to deploy [SSL](docs/create_ssl_cert.md) or [plugins](docs/plugins.md), see the docs linked. The web server used on the application is [pyuwsgi](https://uwsgi-docs.readthedocs.io/en/latest/).

## Docker Compose

This documentation is now written assuming the latest Docker Compose methodology of using the Docker Compose Plugin instead of the independent docker-compose executable. See the [Docker Compose Plugin installation notes](https://docs.docker.com/compose/install/)

## Why Poetry?

Poetry was chosen to replace both **requirements.txt** and **setup.py**. Poetry uses the `pyproject.toml` file to define package details, main package dependencies, development dependencies, and tool-related configurations. Poetry resolves dependencies and stores the hashes and metadata within the `poetry.lock` file that is then similar to performing a `pip freeze > requirements.txt`, but is more secure due to tracking package hashes. The `poetry.lock` is what is used to provide consistency for package versions across the project to make sure anyone who is developing on it is using the same Python dependency versions. Poetry also provides virtual environments by simply being in the same directory as the `pyproject.toml` and `poetry.lock` files and execute the `poetry shell` command.

## Why Invoke?

Invoke is a Python replacement for Make. Invoke looks for a `tasks.py` file that contains functions decorated by `@task` that provides the equivalent of a **Make target**.

The reason it was chosen over Makefile was due to our collective familiarity with Python and the ability to organize and re-use Invoke tasks across Cookiecutter templates.  It also makes managing your Nautobot project vastly simpler by issuing simple commands instead of long command strings that can be confusing.

## How to use this repo

This repo is designed to provide a custom build of Nautobot to include a set of plugins which can then be used in a development environment or deployed in production.  Included in this repo is a skeleton Nautobot plugin which is designed only to provide a quick example of how a plugin could be developed.  Plugins should ultimately be built as packages, published to a PyPI style repository and added to the poetry `pyproject.toml` in this repo.  The plugin code should be hosted in their own repositories with their own CI pipelines and not included here.

## Install Docker

Before beginning, install Docker and verify its operation by running `docker run hello-world`. If you encounter any issues connecting to the Docker service, check that your local user account is permitted to run Docker. **Note:** `docker` v1.10.0 or later is required.

## Install Poetry

It is recommended to follow one of the [installation methods detailed in their documentation](https://python-poetry.org/docs/#installation).  It's advised to install poetry as a system-lvel dependency and not inside a virtual environment.  Once Poetry has been installed you can create the Poetry virtual environment with few simple commands:

1. `poetry shell`
2. `poetry lock`
3. `poetry install`

The last command, `poetry install`, will install all of the project dependencies for you to manage your Nautobot project.  This includes installing the `invoke` Python project.

## Build and start Nautobot

You can build, deploy and populate Nautobot with the following steps

1. `invoke build`
2. `invoke start` or `invoke debug`

Nautobot will be available on port 8080 locally http://localhost

## Cleanup Everything and start from scratch

1. `invoke destroy`
2. `invoke build`
3. `invoke db-import`
4. `invoke start`

## Export current database

While the database is already running

* `invoke db-export`

### Docker Compose Files

Several Docker Compose files are provided as [overrides](https://docs.docker.com/compose/extends/) to allow for various development configurations, these can be thought of as layers to docker compose, each Compose file is described below:

* `docker-compose.postgres.yml` - Starts the required prerequisite PostgreSQL services
* `docker-compose.mysql.yml` - Starts the required prerequisite MySQL services
* `docker-compose.base.yml` - Defines the Nautobot, Celery worker, Celery beats scheduler, and Redis services and how they should be run and built.
* `docker-compose.local.yml` - Defines how the Nautobot and Celery worker containers should run locally.

## CLI Helper Commands

The project comes with a CLI helper based on [invoke](http://www.pyinvoke.org/) to help manage the Nautobot environment. The commands are listed below in 2 categories `environment` and `utility`.

Each command can be executed with a simple `invoke <command>`. Each command also has its own help `invoke <command> --help`.

## Manage Nautobot environment

```bash
  build            Build all docker images.
  debug            Start Nautobot and its dependencies in debug mode.
  destroy          Destroy all containers and volumes.
  start            Start Nautobot and its dependencies in detached mode.
  stop             Stop Nautobot and its dependencies.
  db-export        Export Database data to nautobot_backup.dump.
  db-import        Import test data.
```

## Utility

```bash
  cli              Launch a bash shell inside the running Nautobot container.
  migrate          Run database migrations in Django.
  nbshell          Launch a nbshell session.
```

## NOTE - MySQL

If you want to use MySQL for the database instead of PostgreSQL, perform the below step in place for step #7 below:

```bash
cp invoke.mysql.yml invoke.yml
invoke build start
```

## Getting Started

> **NOTE**: Please be aware that you must be in the Poetry virtual environment before issuing any invoke commands. The steps to do this are detailed above.

1. Have [Docker](https://docs.docker.com/get-docker/) installed on the host.
2. Clone this repository to your Nautobot host into the current user directory.

```bash
git clone https://github.com/nautobot/nautobot-docker-compose.git
```

3. Navigate to the new directory from the git clone.

```bash
cd nautobot-docker-compose
```

4. Copy the `local.env.example` file to `local.env` and `creds.example.env` file to `creds.env` in the environments folder.

```bash
cp environments/local.example.env environments/local.env
cp environments/creds.example.example environments/creds.env
```

5. Update the `.env` files for your environment. **THESE SHOULD BE CHANGED** for proper security and the `creds.env` file should never be synchronized to git as it should contain all secrets for the environment!

```bash
vi environments/local.env
vi environments/creds.env
```

6. Update the `local.env` and `creds.env` files to be only available for the current user.

```bash
chmod 0600 environments/local.env environments/creds.env
```

7. Copy the `invoke.example.yml` file to `invoke.yml`:

```bash
cp invoke.example.yml invoke.yml
```

7. Run `invoke build start` to build the containers and start the environment.

```bash
invoke build start
```

## Getting Started - LDAP

The use of LDAP requires the installation of some additional libraries and some configuration in `nautobot_config.py`. See the [LDAP documentation](docs/ldap.md).

## Getting Started - Plugins

The installation of plugins has a slightly more involved getting-started process. See the [Plugin documentation](docs/plugins.md).

## Super User Account

### Create Super User via Environment

The Docker container has a Docker entry point script that allows you to create a super user by the usage of Environment variables. This can be done by updating the `creds.env` file environment option of `NAUTOBOT_CREATE_SUPERUSER` to `True`. This will then use the information supplied to create the specified superuser.

### Create Super User via Container

After the containers have started:

1. Verify the containers are running:

```bash
docker container ls
```

Example Output:

```bash
❯ docker container ls
CONTAINER ID   IMAGE                           COMMAND                  CREATED         STATUS                   PORTS                                                                                  NAMES
143f10daa229   networktocode/nautobot:latest   "nautobot-server rqw…"   2 minutes ago   Up 2 minutes (healthy)                                                                                          nautobot-docker-compose_celery_worker_1
bb29124d7acb   networktocode/nautobot:latest   "/docker-entrypoint.…"   2 minutes ago   Up 2 minutes (healthy)   0.0.0.0:8080->8080/tcp, :::8080->8080/tcp, 0.0.0.0:8443->8443/tcp, :::8443->8443/tcp   nautobot-docker-compose_nautobot_1
ad57ac1749b3   redis:alpine                    "docker-entrypoint.s…"   2 minutes ago   Up 2 minutes             6379/tcp                                                                               nautobot-docker-compose_redis_1
5ab83264e6fe   postgres:10                     "docker-entrypoint.s…"   2 minutes ago   Up 2 minutes             5432/tcp                                                                               nautobot-docker-compose_postgres_1
```

2. Execute Create Super User Command and follow the prompts

```bash
invoke createsuperuser
```

Example Prompts:

```bash
nautobot@bb29124d7acb:~$ invoke createsuperuser
Username: administrator
Email address:
Password:
Password (again):
Superuser created successfully.
```
