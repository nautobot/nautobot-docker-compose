# SSL Self Signed Certificate

By default the Docker image comes with a self signed certificate that is valid for one year. To provide a different certificate, the file names names `nautobot.key` and `nautobot.crt` within the `/opt/nautobot/` directory is required. With these files present on the host running the Docker compose, use the following as volume mounts into the `nautobot` container.

```yaml
  nautobot:
    image: "networktocode/nautobot:latest"
    env_file:
      - "local.env"
    ports:
      - "8443:8443"
      - "8080:8080"
    restart: "unless-stopped"
    volumes:
      - path/to/your/nautobot.key /opt/nautobot/nautobot.key
      - path/to/your/nautobot.crt /opt/nautobot/nautobot.crt
```

## Make Own Cert Options (Not Required)

### OpenSSL

If you do not have your own self signed certificate, you may generate them by using OpenSSL.

#### Install OpenSSL

OpenSSL is included with many UNIX operating systems, but may need to be installed on your system first.

Check to see if OpenSSL is installed on your system
```
user@ntc# openssl version
LibreSSL 2.8.3
```

If you do not have OpenSSL installed, please follow the [installation guidelines](https://github.com/openssl/openssl#build-and-install).

#### Example Self Sign Cert

Once OpenSSL is installed, run the following command to generate the certificates.
```
sudo openssl req -x509 -nodes -days 365 -newkey rsa:2048 -keyout ./certs/nautobot.key -out ./certs/nautobot.crt
```

You will be prompted with information to fill out for your certificate.
```
Country Name (2 letter code) [AU]:US
State or Province Name (full name) [Some-State]:New York
Locality Name (eg, city) []:New York City
Organization Name (eg, company) [Internet Widgits Pty Ltd]:Bouncy Castles, Inc.
Organizational Unit Name (eg, section) []:Ministry of Water Slides
Common Name (e.g. server FQDN or YOUR name) []:server_IP_address
Email Address []:admin@your_domain.com
```

Finally, ensure your newly generated certificates are in the correct location.
```
user@ntc# ls ./certs/
nautobot.crt    nautobot.key
```
