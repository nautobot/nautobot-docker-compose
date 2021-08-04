# LDAP Container Image

The LDAP container image has a different base and has a multi-stage build associated with it. This is to prevent having to have GCC in the final container image for LDAP.

## Getting Started Using LDAP Container

1. Have [Docker](https://docs.docker.com/get-docker/) and [Docker Compose](https://docs.docker.com/compose/install/) installed on the host
1. Clone this repository to your Nautobot host into the `/opt/nautobot` directory with the user account Nautobot
```
sudo useradd --system --shell /bin/bash --create-home --home-dir /opt/nautobot nautobot
sudo -iu nautobot
git clone https://github.com/nautobot/nautobot-docker-compose.git
```

3. Copy `.env.example` to `.env`
```
cp local.env.example local.env
```

4. Make update to the `local.env` file for your environment. Updates are IMPORTANT!
```
vi /opt/nautobot/local.env
```

5. Update the `local.env` to be only available for the Nautobot user
```
chmod 0600 local.env
```

6. Run `docker-compose -f docker-compose.ldap.yml build --no-cache` to build the `companyname/Dockerfile-LDAP` (from the file `docker-compose.ldap.yml`)
> You may want to update `companyname` to your organization/company name
7. Run `docker-compose -f docker-compose.ldap.yml up` to have the containers spun up and seeing the logs

## Environment Controls

There are two environment variables that will control the environment for the container. 

### Python Version

The version of Python used in the Dockerfile defaults to Python3.9
