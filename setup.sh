#!/bin/bash
cd /opt/wirevad

FILE=/etc/wireguard/wirevadmullvad.conf
if [ -f "$FILE" ]; then
    echo "$FILE exists. Bringing down interface as a precaution."
    wg-quick down wirevadmullvad
    
fi

FILE=/etc/wireguard/wirevadhost.conf
if [ -f "$FILE" ]; then
    echo "$FILE exists. Bringing down interface as a precaution."
    wg-quick down wirevadhost
fi

sleep 1

FILE=/opt/wirevad/wirevadmullvad.conf
if [ -f "$FILE" ]; then
    echo "$FILE exists. Skipping creation of new keys & config."
else
    echo "$FILE does not exist. Creating new keys & config."
    cat > /opt/wirevad/wirevadmullvad.conf <<EOF
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


FILE=/opt/wirevad/wirevadhost.conf
if [ -f "$FILE" ]; then
    echo "$FILE exists. Skipping creation of new keys & config."
else
    echo "$FILE does not exist. Creating new keys & config."
    rm -f /opt/wirevadclient*.conf
    sed -i 's/#net.ipv4.ip_forward=/net.ipv4.ip_forward=/'  /etc/sysctl.conf
    umask 077
    wg genkey | tee privatekey_server | wg pubkey > publickey_server
    

    SERVER_PRIVATE=$(cat privatekey_server)
    SERVER_PUBLIC=$(cat publickey_server)

    # Server CONF
    cat > /opt/wirevad/wirevadhost.conf <<EOF
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
EOF
    for ((i=1; i<=$NUMBER_OF_CLIENTS; i++))
    do
        wg genkey | tee privatekey_client | wg pubkey > publickey_client
        CLIENT_PRIVATE=$(cat privatekey_client)
        CLIENT_PUBLIC=$(cat publickey_client)
        FILE="/opt/wirevad/wirevadclient$i.conf"
        LAST_IP=$((i+1))
        ALLOWED_IP="10.10.12.$LAST_IP/32"
        IP="10.10.12.$LAST_IP/24"
        echo "[Peer]" >> /opt/wirevad/wirevadhost.conf
        echo "PublicKey = $CLIENT_PUBLIC" >> /opt/wirevad/wirevadhost.conf
        echo "AllowedIPs = $ALLOWED_IP" >> /opt/wirevad/wirevadhost.conf

        cat > $FILE <<EOF
        [Interface]
        Address = $IP
        PrivateKey = $CLIENT_PRIVATE
        DNS = $DNS_SERVER

        [Peer]
        PublicKey = $SERVER_PUBLIC
        AllowedIPs = 0.0.0.0/0
        Endpoint = $DOMAIN:$PORT
EOF

    done
    
    

    echo "Your WireGuard config files are located at /opt/wirevad/- don't forget to update your client devices with the new config!"
fi


sysctl -p


cp /opt/wirevad/wirevadmullvad.conf /etc/wireguard/wirevadmullvad.conf
wg-quick up wirevadmullvad

printf "+---------------------------------------------------------------------------+\n"
curl "https://am.i.mullvad.net/connected"
printf "+---------------------------------------------------------------------------+\n"

cp /opt/wirevad/wirevadhost.conf /etc/wireguard/wirevadhost.conf
wg-quick up wirevadhost

rm -f /opt/wirevad/publickey_*
rm -f /opt/wirevad/privatekey_*

chmod -R 777 /opt/wirevad
sleep infinity