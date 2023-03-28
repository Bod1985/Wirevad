#!/usr/bin/env python3
import os
import time
import subprocess
import qrcode
import http.server
import socketserver

MULLVAD_ADDRESS = os.env.get('MULLVAD_ADDRESS')
FWMARK = os.env.get('FWMARK')
MULLVAD_PRIVATEKEY = os.env.get('MULLVAD_PRIVATEKEY')
MULLVAD_DNS = os.env.get('MULLVAD_DNS')

MULLVAD_PUBLICKEY = os.env.get('MULLVAD_PUBLICKEY')
MULLVAD_ENDPOINT = os.env.get('MULLVAD_ENDPOINT')
LAN_SUBNET = os.env.get('LAN_SUBNET')
PORT = os.env.get('PORT')
INTERFACE = os.env.get('INTERFACE')
NUMBER_OF_CLIENTS = os.env.get('NUMBER_OF_CLIENTS')
DNS_SERVER = os.env.get('DNS_SERVER')
DOMAIN = os.env.get('DOMAIN')


os.chdir('/opt/wirevad')

FILE = '/etc/wireguard/wirevadmullvad.conf'
if os.path.isfile(FILE):
    print(f'{FILE} exists. Bringing down interface as a precaution.')
    subprocess.run(['wg-quick', 'down', 'wirevadmullvad'])

FILE = '/etc/wireguard/wirevadhost.conf'
if os.path.isfile(FILE):
    print(f'{FILE} exists. Bringing down interface as a precaution.')
    subprocess.run(['wg-quick', 'down', 'wirevadhost'])

time.sleep(1)

FILE = '/opt/wirevad/wirevadmullvad.conf'
if os.path.isfile(FILE):
    print(f'{FILE} exists. Skipping creation of new keys & config.')
else:
    print(f'{FILE} does not exist. Creating new keys & config.')
    with open('/opt/wirevad/wirevadmullvad.conf', 'w') as f:
        f.write(f"""
        [Interface]
        Address = {MULLVAD_ADDRESS}
        FwMark = {FWMARK}
        PrivateKey = {MULLVAD_PRIVATEKEY}
        DNS = {MULLVAD_DNS}

        PostUp  = iptables -t mangle -A OUTPUT -d 10.10.12.0/24,{LAN_SUBNET} -j MARK --set-mark 51820
        PreDown = iptables -t mangle -D OUTPUT -d 10.10.12.0/24,{LAN_SUBNET} -j MARK --set-mark 51820
        PostUp  = iptables -I OUTPUT ! -o %i -m mark ! --mark 51820 -m addrtype ! --dst-type LOCAL -j REJECT
        PreDown = iptables -D OUTPUT ! -o %i -m mark ! --mark 51820 -m addrtype ! --dst-type LOCAL -j REJECT
        PostUp =  ip route add {LAN_SUBNET} via $(ip route | grep default | awk "{{print $3}}"); iptables -I OUTPUT -d {LAN_SUBNET} -j ACCEPT
        PreDown = ip route del {LAN_SUBNET} via $(ip route | grep default | awk "{{print $3}}"); iptables -D OUTPUT -d {LAN_SUBNET} -j ACCEPT
        
        [Peer]
        # Phone
        PublicKey = {MULLVAD_PUBLICKEY}
        AllowedIPs = 0.0.0.0/0
        Endpoint = {MULLVAD_ENDPOINT}')
        """)

FILE = "/opt/wirevad/wirevadhost.conf"

if os.path.isfile(FILE):
    print(FILE + " exists. Skipping creation of new keys & config.")
else:
    print(FILE + " does not exist. Creating new keys & config.")
    os.system("rm -f /opt/wirevadclient*.conf")
    os.system("sed -i 's/#net.ipv4.ip_forward=/net.ipv4.ip_forward=/' /etc/sysctl.conf")
    os.umask(0o77)
    os.system("wg genkey | tee privatekey_server | wg pubkey > publickey_server")

    with open("privatekey_server") as f:
        SERVER_PRIVATE = f.read().strip()

    with open("publickey_server") as f:
        SERVER_PUBLIC = f.read().strip()

    # Server CONF
    with open(FILE, "w") as f:
        f.write(
        f"""
        [Interface]
        Address = 10.10.12.1/24
        FwMark = 51820
        ListenPort = {PORT}
        PrivateKey = {SERVER_PRIVATE}

        # Forwarding...
        PostUp  = iptables -A FORWARD -o {INTERFACE} ! -d {LAN_SUBNET} -j REJECT
        PostUp  = iptables -A FORWARD -i %i -j ACCEPT
        PostUp  = iptables -A FORWARD -m state --state RELATED,ESTABLISHED -j ACCEPT
        PostUp  = iptables -A FORWARD -j REJECT
        PreDown = iptables -D FORWARD -o {INTERFACE} ! -d {LAN_SUBNET} -j REJECT
        PreDown = iptables -D FORWARD -i %i -j ACCEPT
        PreDown = iptables -D FORWARD -m state --state RELATED,ESTABLISHED -j ACCEPT
        PreDown = iptables -D FORWARD -j REJECT

        # NAT...
        PostUp  = iptables -t nat -A POSTROUTING -o {INTERFACE} -j MASQUERADE
        PostUp  = iptables -t nat -A POSTROUTING -o wirevadmullvad -j MASQUERADE
        PreDown = iptables -t nat -D POSTROUTING -o {INTERFACE} -j MASQUERADE
        PreDown = iptables -t nat -D POSTROUTING -o wirevadmullvad -j MASQUERADE
        """)

    for i in range(1, NUMBER_OF_CLIENTS + 1):
        private_key = os.popen('wg genkey').read().strip()
        with open('privatekey_client', 'w') as f:
            f.write(private_key)
        public_key = os.popen('wg pubkey < privatekey_client').read().strip()
        with open('publickey_client', 'w') as f:
            f.write(public_key)

        file_path = f'/opt/wirevad/wirevadclient{i}.conf'
        last_ip = i + 1
        allowed_ip = f'10.10.12.{last_ip}/32'
        ip = f'10.10.12.{last_ip}/24'

        with open('/opt/wirevad/wirevadhost.conf', 'a') as f:
            peer_config = f"""
                [Peer]
                PublicKey = {public_key}
                AllowedIPs = {allowed_ip}
                """
            f.write(peer_config)

        with open(file_path, 'w') as f:
            file_config = f"""
            [Interface]
            Address = {ip}
            PrivateKey = {private_key}
            DNS = {DNS_SERVER}

            [Peer]
            PublicKey = {SERVER_PUBLIC}
            AllowedIPs = 0.0.0.0/0
            Endpoint = {DOMAIN}:{PORT}
            """
            f.write(file_config)

    print("Your WireGuard config files are located at /opt/wirevad/- don't forget to update your client devices with the new config!")

# Reload sysctl configuration
subprocess.run(['sysctl', '-p'])

# Copy wirevadmullvad.conf to /etc/wireguard/
subprocess.run(['cp', '/opt/wirevad/wirevadmullvad.conf', '/etc/wireguard/wirevadmullvad.conf'])

# Start the wireguard VPN
subprocess.run(['wg-quick', 'up', 'wirevadmullvad'])

# Check if connected to Mullvad VPN
result = subprocess.run(['curl', 'https://am.i.mullvad.net/connected'], capture_output=True)
print(result.stdout.decode())

# Copy wirevadhost.conf to /etc/wireguard/
subprocess.run(['cp', '/opt/wirevad/wirevadhost.conf', '/etc/wireguard/wirevadhost.conf'])

# Start the wireguard host
subprocess.run(['wg-quick', 'up', 'wirevadhost'])

# Remove generated public/private keys
subprocess.run(['rm', '-f', '/opt/wirevad/publickey_*'])
subprocess.run(['rm', '-f', '/opt/wirevad/privatekey_*'])

# Change permissions of /opt/wirevad directory
subprocess.run(['chmod', '-R', '777', '/opt/wirevad'])


# Define the directory containing the configuration files
config_dir = '/opt/wirevad/'

# Generate a QR code for each configuration file in the directory
qr_codes = []
for file_name in os.listdir(config_dir):
    if file_name.endswith('.conf'):
        file_path = os.path.join(config_dir, file_name)
        with open(file_path, 'r') as f:
            config_data = f.read()
            qr_code = qrcode.make(config_data)
            qr_codes.append(qr_code)

# Define the HTML code for displaying the QR codes in a simple web interface
html = '<html><body>'
for i, qr_code in enumerate(qr_codes):
    image_name = f'image_{i}.png'
    qr_code.save(image_name)
    html += f'<img src="{image_name}" /><br>'
html += '</body></html>'

# Save the HTML code to a file
with open('index.html', 'w') as f:
    f.write(html)

# Serve the HTML file and the QR code images with a local web server
PORT = 8000
Handler = http.server.SimpleHTTPRequestHandler
httpd = socketserver.TCPServer(("", PORT), Handler)
print(f"Serving on port {PORT}")
httpd.serve_forever()
