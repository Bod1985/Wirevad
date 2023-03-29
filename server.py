#!/usr/bin/env python3
"""
Wirevad - A WireGuard setup and management script for Mullvad VPN and LAN access.
"""

import os
import subprocess
import qrcode
import base64
from flask import Flask, render_template, send_file, flash, redirect, url_for


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

app = Flask(__name__)
app.config['SECRET_KEY'] = 'LOLGPTWROTETHISFORMELOL'

def wg_down():
  """Bring down the WireGuard interface."""
  FILE = '/etc/wireguard/wirevadmullvad.conf'
  if os.path.isfile(FILE):
      print(f'{FILE} exists. Bringing down interface as a precaution.')
      subprocess.run(['wg-quick', 'down', 'wirevadmullvad'])

  FILE = '/etc/wireguard/wirevadhost.conf'
  if os.path.isfile(FILE):
      print(f'{FILE} exists. Bringing down interface as a precaution.')
      subprocess.run(['wg-quick', 'down', 'wirevadhost'])    

def wg_up(interface):
  """Bring up the WireGuard interface."""
  subprocess.run(['wg-quick', 'up', interface])

def wg_createmullvad():
  """Create Mullvad WireGuard configuration."""
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
      PostUp =  ip route add {LAN_SUBNET} via $(ip route | grep default | awk '{{print $3}}'); iptables -I OUTPUT -d {LAN_SUBNET} -j ACCEPT
      PreDown = ip route del {LAN_SUBNET} via $(ip route | grep default | awk '{{print $3}}'); iptables -D OUTPUT -d {LAN_SUBNET} -j ACCEPT
      
      [Peer]
      # Phone
      PublicKey = {MULLVAD_PUBLICKEY}
      AllowedIPs = 0.0.0.0/0
      Endpoint = {MULLVAD_ENDPOINT}
      """)
    
def wg_createclientandpeers(num_of_clients):
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

    # Server CONF
    with open("/opt/wirevad/wirevadhost.conf", "w") as f:
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
          qr_code.save(image_name)
          with open(file_path, 'rb') as f:
              data_uri = base64.b64encode(f.read()).decode('utf-8')
              download_link = f"data:application/octet-stream;base64,{data_uri}"
          qr_codes.append({'name': file_name, 'image': image_name, 'link': download_link})
    qr_codes.sort(key=lambda x: x['name'])

    return render_template('index.html', qr_codes=qr_codes)

@app.route('/add_peer', methods=['POST'])
def add_peer():
    wg_createclientandpeers(1)
    flash('New peer added successfully!')
    return redirect(url_for('index'))

@app.route('/download/<path:file_path>')
def download(file_path):
    return send_file(file_path, as_attachment=True)

def main():
  """Main function to execute the script."""
  os.chdir('/opt/wirevad')

  wg_createmullvad()
  wg_createclientandpeers(NUMBER_OF_CLIENTS)

  subprocess.run(['sysctl', '-p'])
  subprocess.run(['cp', '/opt/wirevad/wirevadmullvad.conf', '/etc/wireguard/wirevadmullvad.conf'])
  subprocess.run(['wg-quick', 'up', 'wirevadmullvad'])
  result = subprocess.run(['curl', 'https://am.i.mullvad.net/connected'], capture_output=True)
  print(result.stdout.decode())
  subprocess.run(['cp', '/opt/wirevad/wirevadhost.conf', '/etc/wireguard/wirevadhost.conf'])
  subprocess.run(['wg-quick', 'up', 'wirevadhost'])
  subprocess.run(['rm', '-f', '/opt/wirevad/publickey_*'])
  subprocess.run(['rm', '-f', '/opt/wirevad/privatekey_*'])
  subprocess.run(['chmod', '-R', '777', '/opt/wirevad'])

  app.run(host='0.0.0.0', port=8000)


  if __name__ == '__main__':
      main()