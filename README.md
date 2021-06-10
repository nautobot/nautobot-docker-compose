# nautobot-docker-compose

This is a set of instructions for an example Docker Compose file to help with getting started. You may use this and also make edits. If you would like to contribute different options for a Docker Compose, you may submit a PR to have included. See the Contributing section.

## Docker Compose

The provided Docker Compose makes use of environment variables to control what is to be used. This is tightly coupled with the Docker image that is provided on Docker Hub.

## Getting Started

1. Have [Docker](https://docs.docker.com/get-docker/) and [Docker Compose](https://docs.docker.com/compose/install/) installed on the host
2. Clone this repository to your Nautobot host into the `/opt/nautobot` directory with the user account Nautobot
```
sudo useradd --system --shell /bin/bash --create-home --home-dir /opt/nautobot nautobot
sudo -iu nautobot
git clone https://github.com/nautobot/nautobot-docker-compose.git
```

3. Copy `.env.example` to `.env`
```
cp .env.example .env
```

4. Make update to the `.env` file for your environment. Updates are IMPORTANT!
```
vi /opt/nautobot/.env
```

5. Update the `.env` to be only available for the Nautobot user
```
chmod 0600 .env
```

6. Run `docker-compose up` to start the environment
```
docker-compose up
```

## Super User Account

### Create Super User via Environment

The Docker container has a Docker entrypoint script that allows you to create a super user by the usage of Environment variables. This can be done by updating the example `.env` file environment option of `NAUTOBOT_CREATE_SUPERUSER` to `True`. This will then use the information supplied to create the super user.

### Create Super User via Container

After the containers have started:

1. Verify the containers are running:
```
docker container ls
```
Example Output:
```
❯ docker container ls                                                   
CONTAINER ID   IMAGE                           COMMAND                  CREATED         STATUS                   PORTS                                                                                  NAMES
143f10daa229   networktocode/nautobot:latest   "nautobot-server rqw…"   2 minutes ago   Up 2 minutes (healthy)                                                                                          nautobot-docker-compose_nautobot-worker_1
bb29124d7acb   networktocode/nautobot:latest   "/docker-entrypoint.…"   2 minutes ago   Up 2 minutes (healthy)   0.0.0.0:8080->8080/tcp, :::8080->8080/tcp, 0.0.0.0:8443->8443/tcp, :::8443->8443/tcp   nautobot-docker-compose_nautobot_1
ad57ac1749b3   redis:alpine                    "docker-entrypoint.s…"   2 minutes ago   Up 2 minutes             6379/tcp                                                                               nautobot-docker-compose_redis-queue_1
5ab83264e6fe   postgres:10                     "docker-entrypoint.s…"   2 minutes ago   Up 2 minutes             5432/tcp                                                                               nautobot-docker-compose_postgres_1
a9ec61ce5e30   redis:alpine                    "docker-entrypoint.s…"   2 minutes ago   Up 2 minutes             6379/tcp                                                                               nautobot-docker-compose_redis-cacheops_1
a84a89169300   76e40881ecc6                    "docker-entrypoint.s…"   5 weeks ago     Up 5 hours               5432/tcp                                                                               nautobot_plugin_chatops_ansible_postgres_1
60ef800be813   redis:5-alpine                  "docker-entrypoint.s…"   5 weeks ago     Up 5 hours               6379/tcp                                                                               nautobot_plugin_chatops_ansible_redis_1
```

2. Enter the bash shell for the `nautobot-docker-compose_nautobot_1` container as indicated by the name in the last column for the Nautobot container that has ports listed
```
docker exec -it nautobot-docker-compose_nautobot_1 bash
```

3. Execute Create Super User Command and follow the prompts
```
nautobot-server createsuperuser
```
Example Prompts:
```
nautobot@bb29124d7acb:~$ nautobot-server createsuperuser
Username: administrator
Email address: 
Password: 
Password (again): 
Superuser created successfully.
```

## Plugins

For plugin documentation, see the [docs](docs/plugins.md).
