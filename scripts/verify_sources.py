"""Retired source check. Always exits 0 and fetches nothing.

This developer script used to read four hard-coded public Lever feeds by
calling the discovery fetch directly, outside the Start Scan flow. ASTRA
discovery is manual-only: postings are fetched only after the Owner reviews
a scan preview and confirms Start Scan in the workspace. The script is kept
so an old command line still runs harmlessly; it does not import the
discovery fetch, open the database or contact any network.
"""
import sys

MESSAGE = ('ASTRA discovery is manual-only. Open the workspace, review the scan preview '
           'and press Start Scan to check sources. This script fetches nothing.')


def main():
    print(MESSAGE)
    return 0


if __name__ == '__main__':
    sys.exit(main())
