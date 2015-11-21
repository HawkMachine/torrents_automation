import sys
import re
import subprocess
import collections
import datetime
import argparse


TorrentInfo = collections.namedtuple(
    'TorrentInfo',
    ['id', 'name', 'hash', 'magnet', 'state', 'percent_done', 'eta', 'date_added', 'date_finished', 'date_started',
      'latest_activity']
)

def str2date(s):
  return datetime.datetime.strptime(s.strip(), '%a %b %d %H:%M:%S %Y')


TORRENT_INFO_REGEX = {
    'id': (int, 'Id: (?P<value>\d+)'),
    'name': (str, 'Name: (?P<value>.*)$'),
    'hash': (str, 'Hash: (?P<value>.*)$'),
    'magnet': (str, 'Magnet: (?P<value>.*)$'),
    'state': (str, 'State: (?P<value>.*)$'),
    'percent_done': (float, 'Percent Done: (?P<value>.*)%$'),
    'eta': (str, 'ETA: (?P<value>\d+) seconds'),
    'date_added': (str2date, 'Date added: (?P<value>.*)$'),
    'date_finished': (str2date, 'Date finished: (?P<value>.*)$'),
    'date_started': (str2date, 'Date started: (?P<value>.*)$'),
    'latest_activity': (str2date, 'Latest activity: (?P<value>.*)$'),
}

RESULT_REGEX = '^.* responded: "(?P<value>.*)"$'


class TransmissionRemote(object):

  def __init__(self, address, username, password):
    self.address = address
    self.username = username
    self.password = password

  def _GetOutput(self, *args, **kwargs):
    cmd = ['transmission-remote', self.address]
    if self.username and self.password:
      cmd.extend(['-n', self.username + ':' + self.password])
    cmd.extend(args)
    return subprocess.check_output(cmd)

  def _GetValue(self, s, regex, convert):
    m = re.search(regex, s, re.MULTILINE)
    if not m:
      return None
    value = m.group('value')
    if convert:
      value = convert(value)
    return value

  def List(self, torrent='all'):
    output = self._GetOutput('-t', torrent, '-i')
    sections = output.split('NAME')[1:]  # skip the first empty element
    result = []
    for section in sections:
      field_values = {}
      for field, field_opts in TORRENT_INFO_REGEX.iteritems():
        field_convert, field_regex = field_opts
        m = re.search(field_regex, section, re.MULTILINE)
        value = None
        if m:
          value = field_convert(m.group('value'))
        field_values[field] = value
      torrent_info = TorrentInfo(**field_values)
      result.append(torrent_info)
    return result

  def Stop(self, torrents):
    ids_arg = ','.join(str(t.id) for t in torrents)
    output = self._GetOutput('-t', ids_arg, '-S')
    value = self._GetValue(output, RESULT_REGEX, None)
    if not value or value != "success":
      return False
    return True


def main():
  parser = argparse.ArgumentParser()
  parser.add_argument('--address')
  parser.add_argument('--username')
  parser.add_argument('--password')
  args = parser.parse_args()

  if not args.address:
    print '!address is required!'
    return 1

  remote = TransmissionRemote(args.address, args.username, args.password)

  items = remote.List()
  for item in items:
    # print item.id, item.name
    print item


if __name__ == '__main__':
  sys.exit(main())
