"""Retired headless discovery entry point. Always exits 0 and does nothing.

ASTRA discovery is manual-only: a scan starts only when the Owner presses
Start Scan in the workspace and confirms the previewed scope. This script was
the command a Windows scheduled task ("ASTRA Local Discovery") used to run.
It is kept so that any such task still installed on a machine -- enabled or
not -- runs harmlessly: it does not open the database, back it up, sync the
workbook, contact any network or start a scan, whatever arguments it is given.
"""
import argparse
import sys

MESSAGE = ('ASTRA discovery is manual-only. Open the workspace and press Start Scan '
           'to review and start a scan. This scheduled entry point does nothing.')


def main():
    parser = argparse.ArgumentParser()
    # Accepted only so an existing task's command line still parses.
    parser.add_argument('--force', action='store_true')
    parser.add_argument('--trigger', choices=['MANUAL', 'SCHEDULED', 'CATCHUP'], default='SCHEDULED')
    parser.parse_args()
    print(MESSAGE)
    return 0


if __name__ == '__main__':
    sys.exit(main())
