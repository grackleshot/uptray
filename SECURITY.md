# Security policy

topgrade-update runs `topgrade` (and through it `sudo`) on your behalf, so
security reports are taken seriously.

## Reporting a vulnerability

Please report privately through GitHub: open the repository's **Security** tab
and choose **Report a vulnerability**. Don't open a public issue for security
problems.

Include what you found, how to reproduce it, and the version
(`topgrade-update --version`).

## Supported versions

Only the latest release (and `main`) receives fixes.

## How the app handles your sudo password

When topgrade needs `sudo`, the app asks for the password in its own dialog and
hands it to `sudo -A` through a Unix socket. The socket and the small helper
scripts live in `$XDG_RUNTIME_DIR` when that directory is private to you, and
otherwise in a fresh private temporary directory. The password is never written
to disk or to the run transcripts.
