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
