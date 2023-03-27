#!/bin/bash
cd /etc/wireguard

wg-quick down wirevadmullvad
wg-quick down wirevadhost

sleep 1

FILE=/etc/wireguard/wirevadmullvad.conf
if [ -f "$FILE" ]; then
    echo "$FILE exists. Skipping creation of new keys."
else
    echo "$FILE does not exist. Creating new keys."
    cat > /etc/wireguard/wirevadmullvad.conf <<EOF
    [Interface]
    Address = $MULLVAD_ADDRESS
    FwMark = $FWMARK
    PrivateKey = $MULLVAD_PRIVATEKEY
    DNS = $MULLVAD_DNS
    
    PostUp  = iptables -t mangle -A OUTPUT -d 10.10.12.0/24,$LAN_SUBNET -j MARK --set-mark 51820
    PreDown = iptables -t mangle -D OUTPUT -d 10.10.12.0/24,$LAN_SUBNET -j MARK --set-mark 51820 
    PostUp  = iptables -I OUTPUT ! -o %i -m mark ! --mark 51820 -m addrtype ! --dst-type LOCAL -j REJECT
    PreDown = iptables -D OUTPUT ! -o %i -m mark ! --mark 51820 -m addrtype ! --dst-type LOCAL -j REJECT 
    PostUp =  ip route add $LAN_SUBNET via $(ip route | grep default | awk '{print $3}'); iptables -I OUTPUT -d $LAN_SUBNET -j ACCEPT
    PreDown = ip route del $LAN_SUBNET via $(ip route | grep default | awk '{print $3}'); iptables -D OUTPUT -d $LAN_SUBNET -j ACCEPT

    [Peer]
    # Phone
    PublicKey = $MULLVAD_PUBLICKEY
    AllowedIPs = 0.0.0.0/0
    Endpoint = $MULLVAD_ENDPOINT
EOF
fi


FILE=/etc/wireguard/wirevadhost.conf
if [ -f "$FILE" ]; then
    echo "$FILE exists. Skipping creation of new keys."
else
    echo "$FILE does not exist. Creating new keys."
    sed -i 's/#net.ipv4.ip_forward=/net.ipv4.ip_forward=/'  /etc/sysctl.conf
    umask 077
    wg genkey | tee privatekey_server | wg pubkey > publickey_server
    wg genkey | tee privatekey_client | wg pubkey > publickey_client

    SERVER_PRIVATE=$(cat privatekey_server)
    SERVER_PUBLIC=$(cat publickey_server)
    CLIENT_PRIVATE=$(cat privatekey_client)
    CLIENT_PUBLIC=$(cat publickey_client)

    wg genkey | tee privatekey_client | wg pubkey > publickey_client

    CLIENT_PRIVATE1=$(cat privatekey_client)
    CLIENT_PUBLIC1=$(cat publickey_client)

    wg genkey | tee privatekey_client | wg pubkey > publickey_client

    CLIENT_PRIVATE2=$(cat privatekey_client)
    CLIENT_PUBLIC2=$(cat publickey_client)

    wg genkey | tee privatekey_client | wg pubkey > publickey_client

    CLIENT_PRIVATE3=$(cat privatekey_client)
    CLIENT_PUBLIC3=$(cat publickey_client)

    echo "public: $(cat publickey_server)"

    # Server CONF
    cat > /etc/wireguard/wirevadhost.conf <<EOF
    [Interface]
    Address = 10.10.12.1/24
    FwMark = 51820
    ListenPort = $PORT
    PrivateKey = $SERVER_PRIVATE

    # Forwarding...
    PostUp  = iptables -A FORWARD -o $INTERFACE ! -d $LAN_SUBNET -j REJECT
    PostUp  = iptables -A FORWARD -i %i -j ACCEPT
    PostUp  = iptables -A FORWARD -m state --state RELATED,ESTABLISHED -j ACCEPT
    PostUp  = iptables -A FORWARD -j REJECT
    PreDown = iptables -D FORWARD -o $INTERFACE ! -d $LAN_SUBNET -j REJECT
    PreDown = iptables -D FORWARD -i %i -j ACCEPT
    PreDown = iptables -D FORWARD -m state --state RELATED,ESTABLISHED -j ACCEPT
    PreDown = iptables -D FORWARD -j REJECT

    # NAT...
    PostUp  = iptables -t nat -A POSTROUTING -o $INTERFACE -j MASQUERADE
    PostUp  = iptables -t nat -A POSTROUTING -o wirevadmullvad -j MASQUERADE
    PreDown = iptables -t nat -D POSTROUTING -o $INTERFACE -j MASQUERADE
    PreDown = iptables -t nat -D POSTROUTING -o wirevadmullvad -j MASQUERADE

    [Peer]
    # Phone
    PublicKey = $CLIENT_PUBLIC
    AllowedIPs = 10.10.12.2/32

    [Peer]
    # Phone
    PublicKey = $CLIENT_PUBLIC1
    AllowedIPs = 10.10.12.3/32

    [Peer]
    # Phone
    PublicKey = $CLIENT_PUBLIC2
    AllowedIPs = 10.10.12.4/32

    [Peer]
    # Phone
    PublicKey = $CLIENT_PUBLIC3
    AllowedIPs = 10.10.12.5/32
EOF

    # Client CONF
    cat > /opt/wirevad/wirevad1.conf <<EOF
    [Interface]
    Address = 10.10.12.2/24
    PrivateKey = $CLIENT_PRIVATE
    DNS = $DNS_SERVER

    [Peer]
    PublicKey = $SERVER_PUBLIC
    AllowedIPs = 0.0.0.0/0
    Endpoint = $DOMAIN:$PORT
EOF

    cat > /opt/wirevad/wirevad2.conf <<EOF
    [Interface]
    Address = 10.10.12.3/24
    PrivateKey = $CLIENT_PRIVATE1
    DNS = $DNS_SERVER

    [Peer]
    PublicKey = $SERVER_PUBLIC
    AllowedIPs = 0.0.0.0/0
    Endpoint = $DOMAIN:$PORT
EOF

    cat > /opt/wirevad/wirevad3.conf <<EOF
    [Interface]
    Address = 10.10.12.4/24
    PrivateKey = $CLIENT_PRIVATE2
    DNS = $DNS_SERVER

    [Peer]
    PublicKey = $SERVER_PUBLIC
    AllowedIPs = 0.0.0.0/0
    Endpoint = $DOMAIN:$PORT
EOF
    echo "Your WireGuard config is located at /opt/wirevad/wirevad1.conf and /opt/wirevad/wirevad2.conf and /opt/wirevad/wirevad3.conf - don't forget to update your client devices with the new config!"
fi


sysctl -p

wg-quick up wirevadmullvad

printf "+---------------------------------------------------------------------------+\n"
curl "https://am.i.mullvad.net/connected"
printf "+---------------------------------------------------------------------------+\n"

wg-quick up wirevadhost

chmod -R 777 /opt/wirevad


sleep infinity