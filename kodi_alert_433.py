#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import time
import datetime
import requests
import json

import logging
import configparser
import os
import sys
import time
import socket
import signal

from rpi_rf import RFDevice


# global settings
#_config_file_ = os.path.splitext(os.path.basename(__file__))[0] + '.ini'
#_log_file_ = None
#_addon_id_ = 'script.securitycam'
#_debug_ = True
#_test_ = False

import argparse


def is_hostname(h):
  try:
    t = h.split('.')[2]
  except:
    return False

  return True


def is_int(n):
  try:
    t = int(n)
  except:
    return False

  return True


def log(message, level='INFO'):
  if _log_file_:
    if level == 'DEBUG' and _debug_:
      logging.debug(message)
    if level == 'INFO':
      logging.info(message)
    if level == 'WARNING':
      logging.warning(message)
    if level == 'ERROR':
      logging.error(message)
    if level == 'CRITICAL':
      logging.crtitcal(message)
  else:
     if level != 'DEBUG' or _debug_:
       print('[' + level + ']: ' + message)


def read_config():
  global _kodi_, _kodi_port_, _kodi_user_, _kodi_passwd_
  global _gpio_rxdata_, _rf_alertcode_, _notify_title_, _notify_text_
  global _exec_local_

  if not os.path.exists(_config_file_):
    log('Could not find configuration file \'{}\'.'.format(_config_file_), level='ERROR')
    return False

  log('Reading configuration from file ...')

  try:
    # Read the config file
    config = configparser.ConfigParser()

    config.read([os.path.abspath(_config_file_)])

    _kodi_          = config.get('KODI JSON-RPC', 'hostname')
    _kodi_port_     = config.get('KODI JSON-RPC', 'port')
    _kodi_user_     = config.get('KODI JSON-RPC', 'username')
    _kodi_passwd_   = config.get('KODI JSON-RPC', 'password')

    if not is_hostname(_kodi_) or not is_int(_kodi_port_):
      log('Wrong or missing value(s) in configuration file (section: [KODI JSON-RPC]).')
      return False

    value           = config.get('GPIO', 'rxdata')
    if not is_int(value):
      log('Wrong or missing value(s) in configuration file (section: [GPIO]).')
      return False
    else:
       _gpio_rxdata_   = int(value)

    value           = config.get('RF Alert', 'code')
    if not is_int(value):
      log('Wrong or missing value(s) in configuration file (section: [RF Alert]).')
      return False
    else:
       _rf_alertcode_  = int(value)

    _notify_title_  = config.get('Alert Notification', 'title')
    _notify_text_   = config.get('Alert Notification', 'text')

    _exec_local_    = config.get('Local', 'command')

  except:
    log('Could not process configuration file.', level='ERROR')
    return False

  log('Configuration OK.')

  return True


def kodi_request(method, params):
  url  = 'http://{}:{}/jsonrpc'.format(_kodi_, _kodi_port_)
  headers = {'content-type': 'application/json'}
  data = {'jsonrpc': '2.0', 'method': method, 'params': params,'id': 1}

  if _kodi_user_ and _kodi_passwd_:
    base64str = base64.encodestring('{}:{}'.format(_kodi_user_, _kodi_passwd_))[:-1]
    header['Authorization'] = 'Basic {}'.format(base64str)

  try:
    response = requests.post(url, data=json.dumps(data), headers=headers, timeout=10)
  except:
    return False

  data = response.json()
  return (data['result'] == 'OK')


def host_is_up(host, port):
  try:
    sock = socket.create_connection((host, port), timeout=3)
  #except socket.timout:
  #  return False
  except:
    return False

  return True


def alert(title, message):
  if not host_is_up(_kodi_, _kodi_port_):
    log('Host {} is down. Requests canceled.'.format(_kodi_))
    return

  if title and message:
    log('Sending notification \'{}: {}\' ...'.format(title, message))
    kodi_request('GUI.ShowNotification', {'title': title, 'message': message, 'displaytime': 2000})

  log('Requsting execution of addon \'{}\' ...'.format(_addon_id_))
  kodi_request('Addons.ExecuteAddon', {'addonid': _addon_id_})


if __name__ == '__main__':
  global _config_file_, _log_file_, _addon_id_, _debug_, _test_

  parser = argparse.ArgumentParser(description='Sends a notification to a kodi host and triggers addon execution on receipt of an external 433 MHz signal')

  parser.add_argument('-d', '--debug', dest='debug', action='store_true', help="Output debug messages (Default: False)")
  parser.add_argument('-l', '--logfile', dest='log_file', default=None, help="Path to log file (Default: None=stdout)")
  parser.add_argument('-c', '--config', dest='config_file', default=os.path.splitext(os.path.basename(__file__))[0] + '.ini', help="Path to config file (Default: <Script Name>.ini)")
  parser.add_argument('-a', '--addonid', dest='addon_id', default='script.securitycam', help="Addon ID (Default: script.securitycam)")
  parser.add_argument('-t', '--test', dest='test', action='store_true', help="Test Alert (Default: False)")

  args = parser.parse_args()

  _config_file_ = args.config_file
  _log_file_ = args.log_file
  _addon_id_ = args.addon_id
  _debug_ = args.debug
  _test_  = args.test

  if _log_file_:
    logging.basicConfig(filename=_log_file_, format='%(asctime)s [%(levelname)s]: %(message)s', datefmt='%m/%d/%Y %H:%M:%S', filemode='w', level=logging.DEBUG)

  log('Output Debug: {}'.format(_debug_), level='DEBUG')
  log('Log file:     {}'.format(_log_file_), level='DEBUG')
  log('Config file:  {}'.format(_config_file_), level='DEBUG')
  log('Addon ID:     {}'.format(_addon_id_), level='DEBUG')

  if not read_config():
    sys.exit(1)

  if _test_:
    alert(_notify_title_, _notify_text_)
    sys.exit(0)

  rfdevice = None

  try:
    rfdevice = RFDevice(_gpio_rxdata_)
    rfdevice.enable_rx()
    timestamp = None

    log('Listening for RF codes ...')

    while True:

      try:
        if rfdevice.rx_code_timestamp != timestamp:
          timestamp = rfdevice.rx_code_timestamp
          log('{} [pulselength {}, protocol {}]'.format(rfdevice.rx_code, rfdevice.rx_pulselength, rfdevice.rx_proto), level='DEBUG')

          if rfdevice.rx_code == _rf_alertcode_:
            log('Received 433 MHz signal with matching alert code {}'.format(_rf_alertcode_))
            if _exec_local_:
              try:
                os.system(_exec_local_)
              except:
                log('Could not execute local command \'{}\'.'.format(_exec_local_), level='ERROR')
                pass
            alert(_notify_title_, _notify_text_)

        time.sleep(0.01)

      except (KeyboardInterrupt, SystemExit):
        log('Abort requested by user or system.')
        break

      except Exception as e:
        log('Abort due to exception: \"{}\"'.format(e))
        break

  finally:
    rfdevice.cleanup()
