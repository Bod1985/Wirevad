# Wirevad

Sets up Wireguard inside Docker with two interfaces - one utilising Mullvad as a client, one acting as a server for your devices. 

Internet traffic is routed via Mullvad, LAN traffic is not - so you can access your local devices such as cameras or self-hosted projects.

To get started:


Edit docker-compose.yml 

```
version: "3.8"
services:
  wirevad:
    image: bod1985/wirevad:latest
    environment:
      - DOMAIN=example.com #The domain used to connect from outside your LAN
      - PORT=51820 #UDP Port that's forwarded for you to establish a connection
      - INTERFACE=eth0 #Internal interface for routing purposes, unlikely this needs to change
      - LAN_SUBNET=192.168.1.0/24 #Your LAN subnet
      - DNS_SERVER=192.168.1.5 #Your local DNS server (Can be used to skip Mullvad DNS and use your Adguard instance for example)
      - FWMARK=51820 #Used to route traffic, unlikely this needs to change
      - MULLVAD_PRIVATEKEY= #Your privatekey copied from a mullvad Wireguard config file
      - MULLVAD_ADDRESS= #The address copied from a mullvad Wireguard config file
      - MULLVAD_DNS=10.64.0.1 #The DNS copied from a mullvad Wireguard config file. 10.64.0.1 is universal for Mullvad
      - MULLVAD_PUBLICKEY= #Your publickey copied from a mullvad Wireguard config file
      - MULLVAD_ENDPOINT= #The endpoint address copied from a mullvad Wireguard config file
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

Run ```docker-compose up -d```

NOTE: 

When restarting the container, the previous config files are used.

If you recreate the container, you will get new public/private keys so will need to reconfigure client devices.
