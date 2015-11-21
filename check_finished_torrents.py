import sys
import argparse
import pickle
import datetime
import bsddb
import subprocess
import collections

from transmission import transmission_remote


def ClearDB(db):
  keys = list(db.keys())
  for k in keys:
    del db[k]


DATE_FORMAT = '%A %H:%M %d-%m-%Y'

def FormatTable(rows, headers):
  col_widths = []
  for col_nr, header in enumerate(headers):
    col_width = len(header)
    for row in rows:
      if col_nr < len(row):
        col_width = max(col_width, len(row[col_nr]))
    col_widths.append(col_width)

  # add padding
  col_widths = [x + 2 for x in col_widths]

  # Build rows separator
  rows_separator = ''
  for width in col_widths:
    rows_separator += '+' + (width * '-')
  rows_separator += '+\n'

  # result string
  s = rows_separator

  # Header names line
  for col_nr, header in enumerate(headers):
    s += '| ' + header + (' ' * (col_widths[col_nr] - len(header) - 1))
  s += '|\n' + rows_separator
  
  for row in rows:
    for col_nr in xrange(len(headers)):
      v = row[col_nr]
      s += '| ' + v + (' ' * (col_widths[col_nr] - len(v) - 1))
  s += '|\n' + rows_separator

  return s

def FormatList(rows, headers):
  w = max(len(h) for h in headers)

  s = ''
  for row in rows:
    s += '\n'.join('%s: %s' % (
      h.rjust(w+1), e) for e, h in zip(row, headers))
    s += '\n\n'
  return s


def FormatRows(rows, headers):
  # return FormatTable(rows, headers)
  return FormatList(rows, headers)

def FormatTorrents(torrents):
  rows = []
  now = datetime.datetime.now()
  for t in torrents:
    rows.append([
      t.name,
      t.state,
      str(t.percent_done) + '%',
      t.latest_activity.strftime(DATE_FORMAT) if t.latest_activity else '-',
      t.date_finished.strftime(DATE_FORMAT) if t.date_finished else '-',
      '%s' % (now - t.date_finished) if t.date_finished else '-',
      ])
  sorted(rows, key=lambda e: e[0])

  formatter_torrents = FormatRows(
      rows,
      ['Name', 'State', 'Percent done', 'Latest activity', 'Date finished', 'Since finished'])
  return formatter_torrents


def FormatNotifications(notification_events):
  res = ''
  for category, torrents in notification_events.iteritems():
    res += '========= ' + category + ' =========\n'
    res += FormatTorrents(torrents)
    res += '\n'
  return res
    

def SendEmail(subject, message, email):
  print 'Sending email to', email
  p = subprocess.Popen(['mail', '-s', subject, email], stdin=subprocess.PIPE)
  p.communicate(message)


def GetLastNotification(db, category_name, torrent):
  if torrent.name not in db:
    return None
  last_notification = pickle.loads(db[torrent.name])
  return last_notification.get(category_name, None)


def FilterTorrents(now, threshold, torrents_per_category, db):
  threshold_timedelta = datetime.timedelta(seconds=threshold)
  filtered_torrents_per_category = {}
  for category_name, torrents in torrents_per_category.iteritems():
    filtered_torrents = []
    for torrent in torrents:
      last_notification = GetLastNotification(db, category_name, torrent)
      if not last_notification or (now - last_notification) > threshold_timedelta:
        filtered_torrents.append(torrent)
    if filtered_torrents:
      filtered_torrents_per_category[category_name] = filtered_torrents
  return filtered_torrents_per_category


def SaveNotificationTimes(db, now, torrents_per_category):
  categories_by_torrents = collections.defaultdict(list)
  for category_name, torrents in torrents_per_category.iteritems():
    for torrent in torrents:
      categories_by_torrents[torrent.name].append(category_name)
  for name, categories_names in categories_by_torrents.iteritems():
    db[name] = pickle.dumps({n: now for n in categories_names})
  db.sync()


def main():
  parser = argparse.ArgumentParser()

  parser.add_argument('--dump_db', default=False, action='store_const', const=True)

  # Tranmission parameters
  parser.add_argument('--address')
  parser.add_argument('--username')
  parser.add_argument('--password')

  parser.add_argument('--email', default=None)
  parser.add_argument('--db', default=None)

  # Resend emails for conditions that persist.
  parser.add_argument('--remind_threshold ', dest='remind_threshold',
      type=int, default=5*60*60) # 5h
  parser.add_argument('--stopped_threshold', dest='stopped_threshold',
      type=int, default=60*60) # 1h
  args = parser.parse_args()

  # DB that keeps last notification datetime for each of the events.
  db = bsddb.hashopen(args.db)
  if args.dump_db:
    for k, v in db.iteritems():
      print k, pickle.loads(v)
    return 0

  if not args.address or not args.db: 
    print 'Required address, email and db flags!'
    return 1

  stopped_threshold = datetime.timedelta(seconds=args.stopped_threshold)

  now = datetime.datetime.now()


  remote = transmission_remote.TransmissionRemote(args.address, args.username, args.password)
  torrents = remote.List()
  print FormatTorrents(sorted(torrents, key=lambda t: t.name))

  # First delete entries for torrents that do not exist.
  clear_keys = set(db.keys()) - set([t.name for t in torrents])
  for k in clear_keys:
    del db[k]

  # Remove last notification timestamp for running torrent so that we notify for the conditions above as soon as
  # possible.
  running = [t for t in torrents
      if t.percent_done != 100.0
      and t.state.lower() != 'stopped'
      ]
  for t in running:
    if t.name in db:
      del db[t.name]
  db.sync()

  # Find torrents for which I want to send notifications - preferably torrent should be just in one of them.
  torrents_per_category = {
      'Finished': [t for t in torrents if t.percent_done == 100.0],
      'Stopped for too long': [t for t in torrents
        if t.percent_done != 100.0
        and t.state.lower() == 'stopped'
        and t.latest_activity < (now - stopped_threshold)
        ],
  }
  print torrents_per_category

  # Filter out torrents for which notification was sent recently.
  torrents_per_category = FilterTorrents(now, args.remind_threshold, torrents_per_category, db)
  print torrents_per_category

  if torrents_per_category:
    formatted_events = FormatNotifications(torrents_per_category)
    if args.email:
      SendEmail('Torrents need your attention', formatted_events, args.email)
    else:
      print formatted_events

  # Save notification in db.
  SaveNotificationTimes(db, now, torrents_per_category)


if __name__ == '__main__':
  sys.exit(main())
