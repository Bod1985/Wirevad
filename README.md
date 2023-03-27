# Wirevad

Sets up Wireguard inside Docker with two interfaces - one utilising Mullvad as a client, one acting as a server for your devices. 

Internet traffic is routed via Mullvad, LAN traffic is not - so you can access your local devices such as cameras or self-hosted projects.

To get started:

Copy docker-compose.yml to your host device, I use /opt/wirevad as the folder.

Edit docker-compose.yml 

```
version: "3.8"
services:
  wirevad:
    image: bod1985/wirevad:latest
    environment:
      - DOMAIN=example.com
      - PORT=51820
      - INTERFACE=eth0
      - LAN_SUBNET=192.168.1.0/24
      - DNS_SERVER=192.168.1.5
      - FWMARK=51820
      - MULLVAD_PRIVATEKEY=
      - MULLVAD_ADDRESS=
      - MULLVAD_DNS=
      - MULLVAD_PUBLICKEY=
      - MULLVAD_ENDPOINT=
    cap_add:
      - NET_ADMIN
      - SYS_MODULE
    container_name: wirevad
    volumes:
      - /opt/wirevad:/opt/wirevad
    restart: unless-stopped
    ports:
      - 51820:51820/udp
    privileged: true

```
