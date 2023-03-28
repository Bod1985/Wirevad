#!/usr/bin/env python3
import os
import time
import subprocess
import qrcode
import http.server
import socketserver
import base64

MULLVAD_ADDRESS = os.environ.get('MULLVAD_ADDRESS')
FWMARK = os.environ.get('FWMARK')
MULLVAD_PRIVATEKEY = os.environ.get('MULLVAD_PRIVATEKEY')
MULLVAD_DNS = os.environ.get('MULLVAD_DNS')

MULLVAD_PUBLICKEY = os.environ.get('MULLVAD_PUBLICKEY')
MULLVAD_ENDPOINT = os.environ.get('MULLVAD_ENDPOINT')
LAN_SUBNET = os.environ.get('LAN_SUBNET')
PORT = os.environ.get('PORT')
INTERFACE = os.environ.get('INTERFACE')
NUMBER_OF_CLIENTS = os.environ.get('NUMBER_OF_CLIENTS')
DNS_SERVER = os.environ.get('DNS_SERVER')
DOMAIN = os.environ.get('DOMAIN')


os.chdir('/opt/wirevad')

def wg_down(interface):
  subprocess.run(['wg-quick', 'down', interface])

def wg_up(interface):
  subprocess.run(['wg-quick', 'up', interface])

def wg_createmullvad():
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
      PostUp =  ip route add {LAN_SUBNET} via $(ip route | grep default | awk '{{print $3}}'); iptables -I OUTPUT -d {LAN_SUBNET} -j ACCEPT
      PreDown = ip route del {LAN_SUBNET} via $(ip route | grep default | awk '{{print $3}}'); iptables -D OUTPUT -d {LAN_SUBNET} -j ACCEPT
      
      [Peer]
      # Phone
      PublicKey = {MULLVAD_PUBLICKEY}
      AllowedIPs = 0.0.0.0/0
      Endpoint = {MULLVAD_ENDPOINT}
      """)
    
def wg_createclientandpeers(num_of_clients):
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

    for i in range(1, int(num_of_clients) + 1):
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

def createHTML():
  # Define the directory containing the configuration files
  config_dir = '/opt/wirevad/'

  qr_codes = []
  for file_name in os.listdir(config_dir):
      if file_name.endswith('.conf') and file_name.startswith('wirevadclient'):
          file_path = os.path.join(config_dir, file_name)
          with open(file_path, 'rb') as f:
              config_data = f.read()
              qr_code = qrcode.make(config_data)
              image_name = f'{file_name}.png'
              qr_code.save(image_name)
              with open(file_path, 'rb') as f:
                  data_uri = base64.b64encode(f.read()).decode('utf-8')
                  download_link = f"data:application/octet-stream;base64,{data_uri}"
              qr_codes.append({'name': file_name, 'image': image_name, 'link': download_link})
  qr_codes.sort(key=lambda x: x['name'])

  css = f'''
  body {{
    background-color: #1C1C1E;
    color: #FFFFFF;
    font-family: "Helvetica Neue", Helvetica, Arial, sans-serif;
    font-size: 16px;
    line-height: 1.6;
    margin: 0;
    padding: 0;
  }}

  h1 {{
    color: #FFFFFF;
    font-size: 28px;
    font-weight: bold;
    margin: 0;
    padding: 20px 0;
    text-align: center;
    text-shadow: 0 1px 2px rgba(0,0,0,0.5);
  }}

  .qr-codes-container {{
    display: flex;
    flex-wrap: wrap;
    justify-content: center;
    margin: 0;
    padding: 20px;
  }}

  .qr-code {{
    display: flex;
    flex-direction: column;
    align-items: center;
    margin: 20px;
    padding: 20px;
    background-color: #2C2C2E;
    border-radius: 10px;
    box-shadow: 0 2px 4px rgba(0,0,0,0.08);
    transition: box-shadow 0.2s ease-in-out;
  }}

  .qr-code:hover {{
    box-shadow: 0 4px 8px rgba(0,0,0,0.12);
  }}

  .qr-code img {{
    width: 200px;
    height: 200px;
    margin-bottom: 10px;
  }}

  .qr-code span {{
    color: #FFFFFF;
    font-size: 18px;
    font-weight: bold;
    text-align: center;
    text-shadow: 0 1px 2px rgba(0,0,0,0.5);
  }}

  .qr-code .download-link {{
    display: inline-block;
    background-color: #428bca;
    color: white;
    padding: 8px 12px;
    border-radius: 5px;
    text-decoration: none;
    margin-top: 10px;
    transition: background-color 0.2s ease-in-out;
  }}

  .qr-code .download-link:hover {{
    background-color: #3071a9;
  }}
  '''
  with open('style.css', 'w') as f:
      f.write(css)

  html = f'''
  <!DOCTYPE html>
  <html>
  <head>
    <title>QR Codes</title>
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <link rel="stylesheet" type="text/css" href="style.css">
  </head>
  <body>
    <h1>Wirevad</h1>
    
    <div class="qr-codes-container">
  '''

  for qr_code in qr_codes:
      html += f'''
      <div class="qr-code">
        <img src="{qr_code['image']}" alt="{qr_code['name']} QR code">
        <span>{qr_code['name']}</span>
        <a href="{qr_code['name']}" class="download-link">Download</a>
      </div>
      '''
  html += f'''
    </div>
  </body>
  </html>
  '''

  with open('index.html', 'w') as f:
      f.write(html)

FILE = '/etc/wireguard/wirevadmullvad.conf'
if os.path.isfile(FILE):
    print(f'{FILE} exists. Bringing down interface as a precaution.')
    wg_down('wirevadmullvad')

FILE = '/etc/wireguard/wirevadhost.conf'
if os.path.isfile(FILE):
    print(f'{FILE} exists. Bringing down interface as a precaution.')
    wg_down('wirevadhost')

FILE = '/opt/wirevad/wirevadmullvad.conf'
if os.path.isfile(FILE):
    print(f'{FILE} exists. Skipping creation of new keys & config.')
else:
    print(f'{FILE} does not exist. Creating new keys & config.')
    wg_createmullvad()

FILE = "/opt/wirevad/wirevadhost.conf"

if os.path.isfile(FILE):
    print(FILE + " exists. Skipping creation of new keys & config.")
else:
    print(FILE + " does not exist. Creating new keys & config.")
    wg_createclientandpeers(NUMBER_OF_CLIENTS)

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


createHTML()
# Serve the HTML file and the QR code images with a local web server
PORT = 8000
Handler = http.server.SimpleHTTPRequestHandler
httpd = socketserver.TCPServer(("", PORT), Handler)
print(f"Serving on port {PORT}")

try:
    httpd.serve_forever()
except KeyboardInterrupt:
    pass

httpd.server_close()
print("Server stopped.")
