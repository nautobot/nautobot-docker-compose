# SSL Self Signed Certificate
A self signed certificate is required to launch Nautobot via docker-compose. You may provide your own certificate by moving them to the `certs` dir with the names `nginx-selfsigned.key` and `nginx-selfsigned.crt`

```
cp path/to/your/selfsigned-cert.key ./certs/nginx-selfsigned.key
cp path/to/your/selfsigned-cert.crt ./certs/nginx-selfsigned.crt
```

## OpenSSL
If you do not have your own self signed certificate, you may generate them by using OpenSSL.

### Install OpenSSL
OpenSSL is included with many UNIX operating systems, but may need to be installed on your system first.

Check to see if OpenSSL is installed on your system
```
user@ntc# openssl version
LibreSSL 2.8.3
```

If you do not have OpenSSL installed, please follow the [installation guidelines](https://github.com/openssl/openssl#build-and-install).

### Run self sign cert
Once OpenSSL is installed, run the following command to generate the certificates.
```
sudo openssl req -x509 -nodes -days 365 -newkey rsa:2048 -keyout ./certs/nginx-selfsigned.key -out ./certs/nginx-selfsigned.crt
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
nginx-selfsigned.crt    nginx-selfsigned.key
```

## Let's Encrypt
Place holder for Let's Encrypt
