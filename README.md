# Wirevad

Inspired by https://www.reddit.com/r/WireGuard/comments/ekeprt/wireguard_to_wireguard_setup_im_sure_many_have/

NOTE: This comes with no support or promise of future changes/fixes

Sets up Wireguard inside Docker with two interfaces - one utilising Mullvad as a client, one acting as a server for your devices. 

Internet traffic is routed via Mullvad, LAN traffic is not - so you can access your local devices such as cameras or self-hosted projects.

Comes with a WebUI serving the QR Codes and config file Download links.

To get started:

Install Wireguard on the host machine/VM by running

```
sudo apt-get update
sudo apt-get install wireguard-dkms
```


Edit docker-compose.yml 

```
version: "3.8"
services:
  wirevad:
    image: ghcr.io/bod1985/wirevad:latest
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
      - NUMBER_OF_CLIENTS=1 #How many client configs (peers) you would like creating
      - WEB_USERNAME=admin #Username for the WebUI
      - WEB_PASSWORD= #Password for the WebUI. If left empty, a random one is generated on each start and printed in the container logs
      - PUID=1000 #Host user ID that should own /opt/wirevad (run: id -u). Leave empty to keep the files root-only
      - PGID=1000 #Host group ID that should own /opt/wirevad (run: id -g)
      - MSS=1240 #Max TCP segment size for VPN clients. The default avoids slow/stalling connections on lines with a reduced MTU (e.g. PPPoE). 0 disables
      - MQTT_HOST= #Optional: MQTT broker for Home Assistant (e.g. 192.168.1.10). Leave empty to disable
      - MQTT_PORT=1883
      - MQTT_USERNAME=
      - MQTT_PASSWORD=
    cap_add:
      - NET_ADMIN
      - SYS_MODULE
    container_name: wirevad
    volumes:
      - /opt/wirevad:/opt/wirevad
    restart: unless-stopped
    ports:
      - 51820:51820/udp
      - 8000:8000/tcp
    privileged: true

```

Run ```docker-compose up -d```

The WebUI is available on port 8000 and asks for the `WEB_USERNAME`/`WEB_PASSWORD` login. It shows every client's private key, so don't expose port 8000 to the internet.

The files in `/opt/wirevad` contain private keys, so only their owner can read them. Set `PUID`/`PGID` to your host user's IDs to read them without `sudo`; otherwise they're owned by root.

## Home Assistant

Set `MQTT_HOST` (and `MQTT_USERNAME`/`MQTT_PASSWORD` if your broker needs them) and Wirevad appears in Home Assistant automatically via MQTT discovery, as a "Wirevad" device with:

- **Mullvad location** - a selector listing every active Mullvad WireGuard server. Choosing one switches the tunnel live, the same as the web UI.
- **Connected to Mullvad** - on/off
- **Exit server** and **Exit IP**
- **Connected clients** - how many VPN clients are connected right now
- For each VPN client: **Client N connected**, **last handshake**, and data **received**/**sent**. Entities are added and removed automatically as you add or remove peers.

To switch server from an automation, publish a server hostname (e.g. `gb-lon-wg-001`) to `wirevad/location/set`, or use the `select.select_option` action on the selector.

The broker should be on your LAN (`LAN_SUBNET`): the kill switch only lets the container reach the LAN or Mullvad. `MQTT_TOPIC` (default `wirevad`) and `MQTT_DISCOVERY_PREFIX` (default `homeassistant`) can be changed if needed.
