# Gmail Setup — one-time, done by a human

**Rules** 30 (send-only scope), 33–34 (autonomous report, JSON attachment),
39–40 (secrets never committed) · **Version** 1.00

The agent e-mails its own match result. That requires a Google OAuth client and
one browser consent, and **both must be done by a person** — granting an OAuth
scope is a decision a human makes, not something an autonomous agent should do on
its own. The code never starts an interactive flow during a match; a missing
token raises a clear configuration error instead.

Until you complete this, everything else still works. `send-report` runs in dry
run by default and composes the exact message without delivering it.

---

## 0. Current state of this machine (2026-08-07)

**All four steps are done. Nothing here is outstanding.** An existing desktop
OAuth client is reused rather than a new one created, and both repositories are
pointed at it by absolute path:

```
P2PCHASE_GMAIL_CREDENTIALS  /home/krayz1a/ex6/best2934-mcp-cop-thief/credentials.json
P2PCHASE_GMAIL_TOKEN        /home/krayz1a/uni-project/gmail_token.json
P2PCHASE_GMAIL_SENDER       eyalkol2@gmail.com
```

Both paths are **outside** both repositories, which is the point. `.env`,
`credentials.json` and `token.json` are all git-ignored as well, but that is the
second line of defence: a path that is never inside a working tree cannot be
committed by an `git add -A` at two in the morning. Both repositories are
public, and a leaked secret stays leaked because history cannot be un-pushed
(rules 39-40).

Those three names live in `.env`, and **the CLI now reads that file itself**
(`shared/dotenv.py`, applied in `cli/main.py` before any subcommand runs). It
did not, at first, and the failure was a good example of a silent one: only
`tools/endpoint.py` read `.env`, for the peer it launched, so a served match was
signed and a hand-run command was not. The visible symptom was
`authorize-gmail` reporting *"no OAuth client file at credentials.json"* — a
relative path — while the operator was looking at the absolute path they had
just written into `.env`. A real export still wins over the file, so anyone
debugging by hand is never overridden.

`email.enabled` is now `true` in both role configs. A send that fails because no
token exists returns a delivery receipt carrying the reason -- it does not
abort the match.

**Step 4 was done by the operator in a browser on 2026-08-07.** Granting an
OAuth scope is a decision a human makes, signed in to the account that will
send, so the agent does not run this:

```bash
cd ~/uni-project/best2934-cop && uv run p2pchase authorize-gmail
```

The token is at the path above, `chmod 600`, and shared by both repositories --
done once, not twice. Verified without widening the scope:

```
scopes                   ('https://www.googleapis.com/auth/gmail.send',)   send-only, rule 30
refresh_token            present, so no re-consent before the deadline
client_id                matches the credentials file
inside a git repository  no
```

### Proving *which* account authorised, on a send-only scope

Worth writing down, because the obvious check is not available. The token file
records no account -- Google fills that field only when an OpenID scope is also
requested, and `users.getProfile` needs `gmail.readonly` or `gmail.metadata`.
Both would mean widening past send-only, which rule 30 forbids. Meanwhile Gmail
sets `From` to the authorising account and ignores the header we build, so
*our* declared sender proves nothing at all: a token minted from the wrong
Google account would compose a perfectly correct-looking message and deliver it
from somewhere else.

So the account was established by sending one message to `eyalkol2@gmail.com`
through the same `build_message` / `send_raw` path a match report uses. The API
returns the message as it exists **in the authorising account's own mailbox**,
and it came back:

```
labelIds  ['UNREAD', 'SENT', 'INBOX']
```

`SENT` *and* `INBOX` on one message is something a single mailbox gets only when
it addressed itself. The authorising account is therefore the address §1 of
[SUBMISSION.md](SUBMISSION.md) declares.

The test was **not** sent through `send-report --live`. That path's recipient is
overwritten at load time with the address fixed by Appendix F, so a test run
through it would have mailed the lecturer a report about a game nobody played.

---

## 1. Create the OAuth client (Google Cloud Console)

1. Go to <https://console.cloud.google.com/> and create a project — e.g.
   `best2934-agent`.
2. **APIs & Services → Library** → enable the **Gmail API**.
3. **APIs & Services → OAuth consent screen**
   - User type: **External**
   - App name: `best2934 agent`, and your own address as support/developer contact
   - **Scopes**: add **only** `https://www.googleapis.com/auth/gmail.send`
     Do not add a read scope. Rule 30 requires send-only, and a compromised
     send-only token is a far smaller problem than one that can read a mailbox.
   - **Test users**: add the Gmail address the agent will send *from*
   - Leave the app in **Testing**. Publishing would require Google verification
     for no benefit here.
4. **APIs & Services → Credentials → Create credentials → OAuth client ID**
   - Application type: **Desktop app**
   - Download the JSON.

## 2. Put the file somewhere git will never see

```bash
mkdir -p ~/.config/p2pchase
mv ~/Downloads/client_secret_*.json ~/.config/p2pchase/credentials.json
chmod 600 ~/.config/p2pchase/credentials.json
```

**Outside the repository.** `.gitignore` covers `credentials.json`, `token.json`,
`*credentials*.json`, `*token*.json` and `client_secret*.json`, but keeping the
file out of the tree entirely removes the possibility of a mistake.

> A secret committed once is compromised permanently. Deleting it in a later
> commit does **not** remove it from git history, and this repository is public.

## 3. Point the agent at it

Copy `.env-example` to `.env` (git-ignored) and fill in:

```bash
P2PCHASE_GMAIL_CREDENTIALS=/home/<you>/.config/p2pchase/credentials.json
P2PCHASE_GMAIL_TOKEN=/home/<you>/.config/p2pchase/token.json
P2PCHASE_GMAIL_SENDER=your.address@gmail.com
```

Only *paths* live here. No secret value is ever written into a config file or a
log line.

## 4. Run the consent flow once

```bash
uv sync --extra gmail
uv run p2pchase authorize-gmail
```

A browser opens and asks you to grant send-only access to your own account.
Approve it. The token is written to `P2PCHASE_GMAIL_TOKEN`.

Google will warn that the app is unverified — expected for an app in Testing.
Choose **Advanced → Go to best2934 agent (unsafe)**.

If the file is missing, the command tells you so and exits with code 2 rather
than raising:

```
Gmail is not set up: no OAuth client file at …/credentials.json.
Create one in Google Cloud Console (see docs/GMAIL_SETUP.md) and point
P2PCHASE_GMAIL_CREDENTIALS at it.
```

## 5. Verify without sending

```bash
uv run p2pchase send-report --result artifacts/result_<game_id>.json
```

Dry run is the default. It prints the receipt — recipient, subject, attachment
name — and sends nothing. Confirm:

- recipient is `rmisegal+uoh26finalgame@gmail.com` (Appendix F Table 20 — the
  final project's address, **not** assignment 06's `rmisegal+uoh26b@`)
- attachment is `result_<game_id>.json`
- `"sent": false`

## 6. Send for real

```bash
uv run p2pchase send-report --result artifacts/result_<game_id>.json --live
```

`--live` is required. There is no configuration setting that makes a real send
the default.

Every send passes through the Gatekeeper — DOS detector, daily quota, token
bucket, overflow queue. There is no second path to the API. See
[PRD_gatekeeper.md](PRD_gatekeeper.md).

---

## Troubleshooting

| Symptom | Cause | Fix |
|---|---|---|
| `no OAuth token at …` | Consent flow never run | `uv run p2pchase authorize-gmail` |
| `the OAuth token … is invalid; re-authorize` | Token revoked or expired without a refresh token | Delete the token file and re-authorize |
| `Gmail support needs the optional extra` | Google libraries not installed | `uv sync --extra gmail` |
| `403 insufficient authentication scopes` | A read scope crept in, or the token predates the scope change | Delete the token, confirm the consent screen lists only `gmail.send`, re-authorize |
| `"sent": false, "reason": "email.enabled is false"` | Disabled in `setup.json` | Set `email.enabled` to `true` |
| Sends are being queued | Gatekeeper backpressure | Expected. Check `uv run p2pchase gate-status` |

## What is never done, by anyone or anything

- The agent does **not** hold, print or log a credential value.
- The agent does **not** start a browser consent flow on its own.
- `credentials.json` and `token.json` do **not** enter the repository — see
  rules 39–40.
- The scope is **not** widened beyond `gmail.send`, and a test asserts the exact
  tuple so a well-meaning edit fails CI.
