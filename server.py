#!/usr/bin/env python3
"""
Wirevad - A WireGuard setup and management script for Mullvad VPN and LAN access.
"""

import os
import subprocess
import qrcode
import base64
from flask import Flask, render_template, request, send_file, flash, redirect, url_for
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

app = Flask(__name__, template_folder='/app/templates', static_folder='/app/static')
app.config['SECRET_KEY'] = 'LOLGPTWROTETHISFORMELOL'

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
    subprocess.run(['cp', '/opt/wirevad/wirevadmullvad.conf', '/etc/wireguard/wirevadmullvad.conf'])
    subprocess.run(['wg-quick', 'up', interface])
    result = subprocess.run(['curl', 'https://am.i.mullvad.net/connected'], capture_output=True)
    print(result.stdout.decode())
  elif interface == 'wirevadhost':
    subprocess.run(['cp', '/opt/wirevad/wirevadhost.conf', '/etc/wireguard/wirevadhost.conf'])
    subprocess.run(['wg-quick', 'up', interface])
  
def wg_createmullvad():
  """Create Mullvad WireGuard configuration."""
  FILE = '/opt/wirevad/wirevadmullvad.conf'
  if os.path.isfile(FILE):
    print(f'{FILE} exists. Skipping creation of new keys & config.')
  else:
    print(f'{FILE} does not exist. Creating new keys & config.')
    with open('/opt/wirevad/wirevadmullvad.conf', 'w') as f:
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
    
    os.system("cp publickey_server /opt/wirevad/publickey_server")

    # Server CONF
    with open("/opt/wirevad/wirevadhost.conf", "w") as f:
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
        peer_config = \
f"""# Client {i}
[Peer]
PublicKey = {public_key}
AllowedIPs = {allowed_ip}

"""
        f.write(peer_config)

      with open(file_path, 'w') as f:
        file_config = \
f"""[Interface]
Address = {ip}
PrivateKey = {private_key}
DNS = {DNS_SERVER}

[Peer]
PublicKey = {SERVER_PUBLIC}
AllowedIPs = 0.0.0.0/0
Endpoint = {DOMAIN}:{PORT}
"""
        f.write(file_config)

    print("Your WireGuard config files are located at /opt/wirevad/ - don't forget to update your client devices with the new config!")
    os.system("rm -f /opt/wirevad/privatekey_*")
    subprocess.run(['chmod', '-R', '777', '/opt/wirevad'])


def wg_addpeers(num_of_peers):
  """Add additional peers to an existing WireGuard configuration."""
  FILE = "/opt/wirevad/wirevadhost.conf"
  if not os.path.isfile(FILE):
    print("Error: " + FILE + " does not exist.")
    return

  with open(FILE) as f:
      conf = f.read()

  peer_sections = conf.split("# Client ")
  last_peer = 0
  for section in reversed(peer_sections):
    section_lines = section.strip().split('\n')
    if len(section_lines) >= 2:
      peer_index = section_lines[0].split()[-1]
      if peer_index.isdigit():
        last_peer = int(peer_index)
        break

  private_key = os.popen('wg genkey').read().strip()
  with open('privatekey_client', 'w') as f:
    f.write(private_key)
  public_key = os.popen('wg pubkey < privatekey_client').read().strip()
  with open('publickey_client', 'w') as f:
    f.write(public_key)
  with open("/opt/wirevad/publickey_server") as f:
    SERVER_PUBLIC = f.read().strip()
  for i in range(last_peer + 1, last_peer + int(num_of_peers) + 1):
    private_key = os.popen('wg genkey').read().strip()
    with open(f'privatekey_client{i}', 'w') as f:
      f.write(private_key)
    public_key = os.popen(f'wg pubkey < privatekey_client{i}').read().strip()
    with open(f'publickey_client{i}', 'w') as f:
      f.write(public_key)

    allowed_ip = f'10.10.12.{i+1}/32'
    ip = f'10.10.12.{i+1}/24'
    file_path = f'/opt/wirevad/wirevadclient{i}.conf'

    with open(FILE, 'a') as f:
      peer_config = \
f"""# Client {i}
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
  wg_down('wirevadhost')
  time.sleep(1)
  wg_up('wirevadhost')
  print(f"Added {num_of_peers} peers to {FILE} and generated new client config files. Don't forget to update your client devices with the new config!")
  os.system("rm -f /opt/wirevad/privatekey_*")
  subprocess.run(['chmod', '-R', '777', '/opt/wirevad'])

def wg_removepeer(peer_index):
  """Remove a specific peer from a WireGuard configuration file by its index."""
  FILE = "/opt/wirevad/wirevadhost.conf"
  if not os.path.isfile(FILE):
    print("Error: " + FILE + " does not exist.")
    return

  with open(FILE) as f:
    conf = f.read()

  peer_sections = conf.strip().split("# Client ")
  peer_to_remove = None
  for i, section in enumerate(peer_sections):
    if section.strip().startswith(str(peer_index)):
      peer_to_remove = section.strip()
      break

  if peer_to_remove is None:
    print(f"Error: peer index {peer_index} not found.")
    return

  # Find the start and end of the peer section
  start = conf.find(f"# Client {peer_index}")
  end = conf.find("# Client ", start + 1)
  if end == -1:
    end = len(conf)

  # Remove the peer section from the configuration file
  updated_conf = conf[:start] + conf[end:]

  # Remove any leftover empty lines
  updated_conf = "\n".join([line for line in updated_conf.split("\n") if line.strip()])

  os.system(f"rm -f /opt/wirevad/wirevadclient{peer_index}.conf")
  os.system(f"rm -f /app/static/wirevadclient{peer_index}.conf.png")
  with open(FILE, 'w') as f:
    f.write(updated_conf + "\n")

  wg_down('wirevadhost')
  time.sleep(1)
  wg_up('wirevadhost')
  subprocess.run(['chmod', '-R', '777', '/opt/wirevad'])
  print(f"Removed peer {peer_index} from {FILE}.")
  
def check_mullvad():
  global connected
  try:
    response = requests.get('https://am.i.mullvad.net/json')
    connected = response.json()
  except Exception as e:
    print(e)
    connected = False

@app.route('/')
def index():
    config_dir = '/opt/wirevad/'

    qr_codes = []
    for file_name in os.listdir(config_dir):
      if file_name.endswith('.conf') and file_name.startswith('wirevadclient'):
        file_path = os.path.join(config_dir, file_name)
        with open(file_path, 'rb') as f:
          config_data = f.read()
          qr_code = qrcode.make(config_data)
          image_name = f'{file_name}.png'
      
          qr_code.save(f'static/{image_name}')
          with open(file_path, 'rb') as f:
            data_uri = base64.b64encode(f.read()).decode('utf-8')
            download_link = f"data:application/octet-stream;base64,{data_uri}"
          qr_codes.append({'name': file_name, 'image': image_name, 'link': download_link})
    qr_codes.sort(key=lambda x: int(x['name'][len('wirevadclient'):].split('.')[0]))

    # Perform Mullvad check
    try:
        response = requests.get('https://am.i.mullvad.net/json')
        connected = response.json()
    except Exception as e:
        print(e)
        connected = False

    # Render HTML template with Mullvad check result
    return render_template('index.html', qr_codes=qr_codes, connected=connected)

@app.route('/add_peer', methods=['POST'])
def add_peer():
  wg_addpeers(1)
  flash('New peer added successfully!')
  return redirect(url_for('index'))

@app.route('/remove_peer/<int:peer_index>', methods=['POST'])
def remove_peer(peer_index):
  """Remove a peer from the WireGuard configuration by its index."""
  wg_removepeer(peer_index)
  flash('Peer removed successfully!')
  return redirect(url_for('index'))

@app.route('/download/<path:file_path>')
def download(file_path):
  return send_file(file_path, as_attachment=True)

def run_flask_app():
  app.run(host='0.0.0.0', port=8000, debug=True)


def main():
  """Main function to execute the script."""
  wg_createmullvad()
  wg_createhost(NUMBER_OF_CLIENTS)
  wg_up('wirevadmullvad')
  wg_up('wirevadhost')
  

if __name__ == '__main__':
  main()
  run_flask_app()
  # Start Mullvad check scheduler
  schedule.every(30).seconds.do(check_mullvad)

  # Run Flask app and Mullvad check scheduler in a single thread
  while True:
    # Check Mullvad every 30 seconds
    schedule.run_pending()

    # Update Flask app with current Mullvad status
    with app.app_context():
      index()

    # Sleep for 1 second
    time.sleep(1)
