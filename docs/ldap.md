# LDAP Container Image

The LDAP container image has a different base image than the primary Docker file with Nautobot. The Dockerfile-LDAP has a multi-stage build associated to install the Python components that require GCC. But then the final container being used for running Nautobot does not require GCC.

## Getting Started Using LDAP Container

1. Have [Docker](https://docs.docker.com/get-docker/) and [Docker Compose](https://docs.docker.com/compose/install/) installed on the host
2. Clone this repository to your Nautobot host into the current user directory.
```
git clone https://github.com/nautobot/nautobot-docker-compose.git
```

3. Copy `.env.example` to `.env`
```
cp local.env.example local.env
```

4. Make update to the `local.env` file for your environment. Updates are IMPORTANT!
```
vi local.env
```

5. Update the `local.env` to be only available for the Nautobot user
```
chmod 0600 local.env
```

6. Copy the LDAP configuration file from `config/nautobot_config.py.ldap` to `config/nautobot_config.py`

```
cp config/nautobot_config.py.ldap config/nautobot_config.py
```

7. Update settings in the LDAP configuration to match your environment, based on the documentation from [Nautobot docs](https://nautobot.readthedocs.io)

```
vi config/nautobot_config.py
```

8. Update environment vars in the `local.env` file for the configuration file:

* NAUTOBOT_AUTH_LDAP_SERVER_URI
* NAUTOBOT_AUTH_LDAP_BIND_DN
* NAUTOBOT_AUTH_LDAP_BIND_PASSWORD

```
vi local.env
```

1.  Run `docker-compose -f docker-compose.ldap.yml build --no-cache` to build the `companyname/Dockerfile-LDAP` (from the file `docker-compose.ldap.yml`)
> You may want to update `companyname` to your organization/company name

```
docker-compose -f docker-compose.ldap.yml build --no-cache
```

7. Run `docker-compose -f docker-compose.ldap.yml up` to have the containers spun up and seeing the logs

```
docker-compose -f docker-compose.ldap.yml up
```

## Environment Controls

There are two environment variables that will control the environment for the container. 

### Python Version

The version of Python used in the Dockerfile defaults to Python3.9
