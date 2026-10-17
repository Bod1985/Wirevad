"""CSRF protection tests for the web UI.

Run from the repo root with: python3 -m unittest discover tests
(needs flask, qrcode, pillow, requests and schedule installed).
"""

import base64
import os
import re
import sys
import tempfile
import unittest
from unittest import mock

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

import server

server.app.template_folder = os.path.join(ROOT, 'templates')
server.app.static_folder = os.path.join(ROOT, 'static')
server.app.config['TESTING'] = True
server.WEB_PASSWORD = 'secret'

AUTH = {'Authorization': 'Basic ' + base64.b64encode(b'admin:secret').decode()}


class CsrfTest(unittest.TestCase):

  def setUp(self):
    self.config_dir = tempfile.TemporaryDirectory()
    with open(os.path.join(self.config_dir.name, 'wirevadclient1.conf'), 'w') as f:
      f.write('[Interface]\n')
    patches = [
      mock.patch.object(server, 'CONFIG_DIR', self.config_dir.name),
      mock.patch.object(server, 'wg_addpeers'),
      mock.patch.object(server, 'wg_removepeer', return_value=True),
      mock.patch.object(server, 'switch_relay', return_value=True),
      mock.patch.object(server, 'current_relay', return_value=None),
      mock.patch.object(server, 'relays', [{'hostname': 'se-got-wg-001', 'country_name': 'Sweden',
                                             'city_name': 'Gothenburg'}]),
    ]
    for p in patches:
      p.start()
      self.addCleanup(p.stop)
    self.addCleanup(self.config_dir.cleanup)
    self.client = server.app.test_client()

  def get_token(self):
    """Load the page like a browser would and return the token from its forms."""
    page = self.client.get('/', headers=AUTH).get_data(as_text=True)
    tokens = re.findall(r'name="csrf_token" value="([^"]+)"', page)
    self.assertEqual(len(tokens), 3, 'expected a token in the location, add and remove forms')
    self.assertEqual(len(set(tokens)), 1)
    return tokens[0]

  def post(self, url, token=None, headers=None):
    data = {'relay': 'se-got-wg-001'}
    if token is not None:
      data['csrf_token'] = token
    return self.client.post(url, data=data, headers={**AUTH, **(headers or {})})

  def test_add_peer_with_token(self):
    response = self.post('/add_peer', self.get_token())
    self.assertEqual(response.status_code, 302)
    server.wg_addpeers.assert_called_once_with(1)

  def test_remove_peer_with_token(self):
    response = self.post('/remove_peer/1', self.get_token())
    self.assertEqual(response.status_code, 302)
    server.wg_removepeer.assert_called_once_with(1)

  def test_set_location_with_token(self):
    response = self.post('/set_location', self.get_token())
    self.assertEqual(response.status_code, 302)
    server.switch_relay.assert_called_once_with('se-got-wg-001')

  def test_same_origin_headers_accepted(self):
    token = self.get_token()
    self.assertEqual(self.post('/add_peer', token, {'Origin': 'http://localhost'}).status_code, 302)
    self.assertEqual(self.post('/add_peer', token, {'Referer': 'http://localhost/'}).status_code, 302)

  def test_missing_token_rejected(self):
    self.get_token()
    for url in ('/add_peer', '/remove_peer/1', '/set_location'):
      with self.subTest(url=url):
        self.assertEqual(self.post(url).status_code, 400)
    server.wg_addpeers.assert_not_called()
    server.wg_removepeer.assert_not_called()
    server.switch_relay.assert_not_called()

  def test_wrong_token_rejected(self):
    self.get_token()
    for url in ('/add_peer', '/remove_peer/1', '/set_location'):
      with self.subTest(url=url):
        self.assertEqual(self.post(url, 'not-the-token').status_code, 400)
    server.wg_addpeers.assert_not_called()
    server.wg_removepeer.assert_not_called()
    server.switch_relay.assert_not_called()

  def test_token_without_session_rejected(self):
    # A token from another session (e.g. one an attacker loaded) doesn't work here
    token = self.get_token()
    self.client = server.app.test_client()
    self.assertEqual(self.post('/add_peer', token).status_code, 400)
    server.wg_addpeers.assert_not_called()

  def test_cross_origin_rejected(self):
    token = self.get_token()
    self.assertEqual(self.post('/add_peer', token, {'Origin': 'https://evil.example'}).status_code, 400)
    self.assertEqual(self.post('/add_peer', token, {'Referer': 'https://evil.example/page'}).status_code, 400)
    self.assertEqual(self.post('/add_peer', token, {'Origin': 'null'}).status_code, 400)
    server.wg_addpeers.assert_not_called()

  def test_get_unaffected(self):
    self.assertEqual(self.client.get('/', headers=AUTH).status_code, 200)

  def test_login_still_required(self):
    response = self.client.post('/add_peer', data={'csrf_token': 'x'})
    self.assertEqual(response.status_code, 401)


if __name__ == '__main__':
  unittest.main()
