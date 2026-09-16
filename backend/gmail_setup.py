"""Configure the Gmail OAuth client secret: `python -m backend.gmail_setup`.

Issue #44. Google's installed-app documentation marks `client_secret`
optional and states that installed apps cannot keep a secret confidential,
but a Desktop OAuth client can still enforce client authentication at the
token endpoint -- live validation proved this one does. This command is the
only way a secret enters ASTRA.

Why a console command and not a settings field in the web UI: a browser
form would place the secret in page state, in the DOM, and in a request
body that passes through the local HTTP stack. A hidden console prompt
keeps it in one process's memory until it reaches the OS credential store.

The value is read with `getpass`, which reads the console directly rather
than stdin, so it is not echoed, cannot be piped in from a file or another
process, and does not land in shell history. It is never accepted as a
command-line argument, never written to a file, and never printed.
"""
import getpass
import sys


def _report(message):
    print(message, flush=True)


def main(argv=None):
    from .gmail_accounts import (client_secret_status, credential_store_status,
                                 delete_client_secret, store_client_secret)
    from .gmail_oauth import (CLIENT_ID_ENVIRONMENT_VARIABLE, OAuthError, Secret,
                              configuration_status)

    argv = sys.argv[1:] if argv is None else list(argv)
    if any(argument not in ('--status', '--remove') for argument in argv):
        _report('Usage: python -m backend.gmail_setup [--status | --remove]')
        return 2
    # A secret passed as an argument would be visible to every process on
    # the machine and would land in shell history, so it is never accepted.
    if any(argument.startswith('--secret') for argument in argv):
        _report('The client secret is never accepted as a command-line argument.')
        return 2

    store = credential_store_status()
    _report(f'Credential store : {store["state"]}')
    if store['state'] != 'OS_SECURE_STORE':
        _report('A supported native OS credential store is unavailable. ASTRA '
                'never falls back to storing a secret in plaintext.')
        return 1
    configuration = configuration_status()
    _report(f'Client ID        : {configuration["state"]} '
            f'(from {CLIENT_ID_ENVIRONMENT_VARIABLE})')
    _report(f'Client secret    : {client_secret_status()["state"]}')

    if '--status' in argv:
        return 0

    if '--remove' in argv:
        delete_client_secret()
        _report(f'Client secret    : {client_secret_status()["state"]} (removed)')
        return 0

    _report('')
    _report('Paste the client secret for your own Desktop OAuth client.')
    _report('It is not echoed, not written to any file, and never appears in')
    _report('the database, logs, exports, backups, diagnostics or the UI.')
    _report('It is stored only in your OS credential store, protected for')
    _report('your Windows user account. Press Enter with nothing to cancel.')
    try:
        entered = getpass.getpass('Client secret (hidden): ')
    except Exception as error:
        _report(f'No interactive console available for a hidden prompt '
                f'({type(error).__name__}). Run this command from a real '
                f'terminal window.')
        return 1
    if not entered.strip():
        _report('Cancelled. Nothing was stored.')
        return 1
    secret = Secret(entered)
    del entered
    try:
        store_client_secret(secret)
    except OAuthError as error:
        # `error` is authored by ASTRA and carries no credential value.
        _report(f'Not stored: {error}')
        return 1
    finally:
        secret.clear()
    _report('')
    _report(f'Client secret    : {client_secret_status()["state"]}')
    _report('Stored in the OS credential store. Connect Gmail from '
            'Privacy & Local Data.')
    return 0


if __name__ == '__main__':
    sys.exit(main())
