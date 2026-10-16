#!/usr/bin/env python3
"""
Wirevad - A WireGuard setup and management script for Mullvad VPN and LAN access.
"""

import os
import re
import io
import hmac
import secrets
import subprocess
import threading
import qrcode
import base64
from flask import Flask, render_template, request, flash, redirect, url_for, Response
import time, requests, schedule, glob

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

WEB_USERNAME = os.environ.get('WEB_USERNAME') or 'admin'
WEB_PASSWORD = os.environ.get('WEB_PASSWORD')

CONFIG_DIR = '/opt/wirevad'
HOST_CONF = f'{CONFIG_DIR}/wirevadhost.conf'

app = Flask(__name__, template_folder='/app/templates', static_folder='/app/static')
app.config['SECRET_KEY'] = os.environ.get('SECRET_KEY') or secrets.token_hex(32)

# Latest result of the background Mullvad check, shown on the web UI
connected = False

def wg_down(interface):
  """Bring down the WireGuard interface."""
  if interface == 'wirevadmullvad':
    FILE = '/etc/wireguard/wirevadmullvad.conf'
    if os.path.isfile(FILE):
        print(f'{FILE} exists. Bringing down interface as a precaution.')
        subprocess.run(['wg-quick', 'down', 'wirevadmullvad'])

  elif interface == 'wirevadhost':
    FILE = '/etc/wireguard/wirevadhost.conf'
    if os.path.isfile(FILE):
        print(f'{FILE} exists. Bringing down interface as a precaution.')
        subprocess.run(['wg-quick', 'down', 'wirevadhost'])

def wg_up(interface):
  """Bring up the WireGuard interface."""
  if interface == 'wirevadmullvad':
    subprocess.run(['sysctl', '-p'])
    subprocess.run(['cp', f'{CONFIG_DIR}/wirevadmullvad.conf', '/etc/wireguard/wirevadmullvad.conf'])
    subprocess.run(['wg-quick', 'up', interface])
    result = subprocess.run(['curl', 'https://am.i.mullvad.net/connected'], capture_output=True)
    print(result.stdout.decode())
  elif interface == 'wirevadhost':
    subprocess.run(['cp', HOST_CONF, '/etc/wireguard/wirevadhost.conf'])
    subprocess.run(['wg-quick', 'up', interface])

def lock_down_config_dir():
  """Make the config directory and the keys inside it readable by root only."""
  os.chmod(CONFIG_DIR, 0o700)
  for path in glob.glob(f'{CONFIG_DIR}/*'):
    os.chmod(path, 0o600)

def gen_keypair():
  """Generate a WireGuard private/public key pair without writing either to disk."""
  private_key = subprocess.run(['wg', 'genkey'], capture_output=True, text=True, check=True).stdout.strip()
  public_key = subprocess.run(['wg', 'pubkey'], input=private_key, capture_output=True, text=True, check=True).stdout.strip()
  return private_key, public_key

def add_client(index, server_public):
  """Append a peer to the host config and write the matching client config."""
  private_key, public_key = gen_keypair()

  with open(HOST_CONF, 'a') as f:
    f.write(\
f"""# Client {index}
[Peer]
PublicKey = {public_key}
AllowedIPs = 10.10.12.{index + 1}/32

""")

  with open(f'{CONFIG_DIR}/wirevadclient{index}.conf', 'w') as f:
    f.write(\
f"""[Interface]
Address = 10.10.12.{index + 1}/24
PrivateKey = {private_key}
DNS = {DNS_SERVER}

[Peer]
PublicKey = {server_public}
AllowedIPs = 0.0.0.0/0
Endpoint = {DOMAIN}:{PORT}
""")

def peer_indexes(conf):
  """Return the client indexes present in a host config."""
  return [int(n) for n in re.findall(r'(?m)^# Client (\d+)\s*$', conf)]

def wg_createmullvad():
  """Create Mullvad WireGuard configuration."""
  FILE = f'{CONFIG_DIR}/wirevadmullvad.conf'
  if os.path.isfile(FILE):
    print(f'{FILE} exists. Skipping creation of new keys & config.')
  else:
    print(f'{FILE} does not exist. Creating new keys & config.')
    with open(FILE, 'w') as f:
      f.write(\
f"""[Interface]
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
PublicKey = {MULLVAD_PUBLICKEY}
AllowedIPs = 0.0.0.0/0
Endpoint = {MULLVAD_ENDPOINT}
""")

def wg_createhost(num_of_clients):
  """Create client and peers WireGuard configuration."""
  if os.path.isfile(HOST_CONF):
    print(HOST_CONF + " exists. Skipping creation of new keys & config.")
  else:
    print(HOST_CONF + " does not exist. Creating new keys & config.")
    # Client configs from a previous server key are useless now, so clear them out
    for path in glob.glob(f'{CONFIG_DIR}/wirevadclient*.conf'):
      os.remove(path)
    os.system("sed -i 's/#net.ipv4.ip_forward=/net.ipv4.ip_forward=/' /etc/sysctl.conf")
    SERVER_PRIVATE, SERVER_PUBLIC = gen_keypair()

    with open(f'{CONFIG_DIR}/publickey_server', 'w') as f:
      f.write(SERVER_PUBLIC + '\n')

    # Server CONF
    with open(HOST_CONF, "w") as f:
      f.write(\
f"""[Interface]
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
      add_client(i, SERVER_PUBLIC)

    print(f"Your WireGuard config files are located at {CONFIG_DIR}/ - don't forget to update your client devices with the new config!")
  lock_down_config_dir()


def wg_addpeers(num_of_peers):
  """Add additional peers to an existing WireGuard configuration."""
  if not os.path.isfile(HOST_CONF):
    print("Error: " + HOST_CONF + " does not exist.")
    return

  with open(HOST_CONF) as f:
    conf = f.read()
  last_peer = max(peer_indexes(conf), default=0)

  with open(f'{CONFIG_DIR}/publickey_server') as f:
    SERVER_PUBLIC = f.read().strip()

  for i in range(last_peer + 1, last_peer + int(num_of_peers) + 1):
    add_client(i, SERVER_PUBLIC)

  wg_down('wirevadhost')
  time.sleep(1)
  wg_up('wirevadhost')
  lock_down_config_dir()
  print(f"Added {num_of_peers} peers to {HOST_CONF} and generated new client config files. Don't forget to update your client devices with the new config!")

def wg_removepeer(peer_index):
  """Remove a specific peer from a WireGuard configuration file by its index."""
  if not os.path.isfile(HOST_CONF):
    print("Error: " + HOST_CONF + " does not exist.")
    return False

  with open(HOST_CONF) as f:
    conf = f.read()

  # Match the exact index so that removing peer 1 can't touch peer 10
  match = re.search(rf'(?m)^# Client {peer_index}\s*$', conf)
  if match is None:
    print(f"Error: peer index {peer_index} not found.")
    return False

  start = match.start()
  next_peer = re.compile(r'(?m)^# Client \d+\s*$').search(conf, match.end())
  end = next_peer.start() if next_peer else len(conf)

  updated_conf = conf[:start] + conf[end:]

  client_conf = f'{CONFIG_DIR}/wirevadclient{peer_index}.conf'
  if os.path.isfile(client_conf):
    os.remove(client_conf)
  with open(HOST_CONF, 'w') as f:
    f.write(updated_conf.rstrip() + "\n\n")

  wg_down('wirevadhost')
  time.sleep(1)
  wg_up('wirevadhost')
  print(f"Removed peer {peer_index} from {HOST_CONF}.")
  return True

def check_mullvad():
  global connected
  try:
    response = requests.get('https://am.i.mullvad.net/json', timeout=10)
    connected = response.json()
  except Exception as e:
    print(e)
    connected = False

def run_scheduler():
  """Check the Mullvad connection now and every 30 seconds after."""
  check_mullvad()
  schedule.every(30).seconds.do(check_mullvad)
  while True:
    schedule.run_pending()
    time.sleep(1)

@app.before_request
def require_login():
  """Protect every page (static files included) with HTTP basic auth."""
  auth = request.authorization
  if auth and auth.type == 'basic' \
     and hmac.compare_digest((auth.username or '').encode(), WEB_USERNAME.encode()) \
     and hmac.compare_digest((auth.password or '').encode(), WEB_PASSWORD.encode()):
    return None
  return Response('Login required', 401, {'WWW-Authenticate': 'Basic realm="Wirevad"'})

@app.route('/')
def index():
    qr_codes = []
    for file_name in os.listdir(CONFIG_DIR):
      if file_name.endswith('.conf') and file_name.startswith('wirevadclient'):
        with open(os.path.join(CONFIG_DIR, file_name), 'rb') as f:
          config_data = f.read()

        # Render the QR code in memory so client keys never land in the public static folder
        image = io.BytesIO()
        qrcode.make(config_data).save(image, format='PNG')
        image_uri = 'data:image/png;base64,' + base64.b64encode(image.getvalue()).decode('utf-8')
        download_link = 'data:application/octet-stream;base64,' + base64.b64encode(config_data).decode('utf-8')
        qr_codes.append({'name': file_name, 'image': image_uri, 'link': download_link})
    qr_codes.sort(key=lambda x: int(x['name'][len('wirevadclient'):].split('.')[0]))

    return render_template('index.html', qr_codes=qr_codes, connected=connected)

@app.route('/add_peer', methods=['POST'])
def add_peer():
  wg_addpeers(1)
  flash('New peer added successfully!')
  return redirect(url_for('index'))

@app.route('/remove_peer/<int:peer_index>', methods=['POST'])
def remove_peer(peer_index):
  """Remove a peer from the WireGuard configuration by its index."""
  if wg_removepeer(peer_index):
    flash('Peer removed successfully!')
  else:
    flash(f'Peer {peer_index} was not found.')
  return redirect(url_for('index'))

def run_flask_app():
  app.run(host='0.0.0.0', port=8000)


def main():
  """Main function to execute the script."""
  global WEB_PASSWORD
  if not WEB_PASSWORD:
    WEB_PASSWORD = secrets.token_urlsafe(16)
    print(f"WEB_PASSWORD is not set. Generated a password for this run - log in to the web UI as '{WEB_USERNAME}' with: {WEB_PASSWORD}")

  # Anything written from here on (keys, configs) is readable by root only
  os.umask(0o077)
  wg_createmullvad()
  wg_createhost(NUMBER_OF_CLIENTS)
  wg_up('wirevadmullvad')
  wg_up('wirevadhost')


if __name__ == '__main__':
  main()
  threading.Thread(target=run_scheduler, daemon=True).start()
  run_flask_app()
