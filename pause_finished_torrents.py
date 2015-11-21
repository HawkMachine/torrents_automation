"""Simple tool to pause torrents that have completed."""
import sys
import argparse

from torrents_automation import transmission_remote

def main():
  parser = argparse.ArgumentParser()

  # Tranmission parameters
  parser.add_argument('--address')
  parser.add_argument('--username')
  parser.add_argument('--password')

  # Resend emails for conditions that persist.
  args = parser.parse_args()

  if not args.address:
    print '!address is required!'
    return 1

  remote = transmission_remote.TransmissionRemote(args.address, args.username, args.password)
  torrents = remote.List()
  finished_torrents = [t for t in torrents if t.percent_done == 100 and t.state.lower() != 'stopped']
  if finished_torrents:
    print 'Finishing the following torrents'
    print '\n  '.join(t.name + ' ' + t.state for t in finished_torrents)
    remote.Stop(finished_torrents)


if __name__ == '__main__':
  sys.exit(main())
