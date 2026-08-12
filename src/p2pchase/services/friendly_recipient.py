"""Where a *friendly's* report goes, and why it is not where a counted one goes.

Two rules pull in opposite directions and both are right.

Appendix F Table 20 fixes the counted report's recipient, and our config
overwrites it at load time on purpose: a team that could redirect its own report
could opt out of being marked, so that address is not ours to change.

But a friendly is not a report to the lecturer at all. Mailing one there is
noise at best and a false submission at worst. imreeyal make the exchange a
precondition instead -- both peers mail their result to each other and diff the
two files before anything counted, because rule 35 treats contradictory reports
as harshly as missing ones and a counted game is the wrong place to discover
that two mailers disagree. They have run four counted pairings this way and have
never received a report from us, because we had nowhere to send one.

So the override exists, and it **replaces** rather than adds:

* A friendly goes to the addresses named on the command line, and never to the
  lecturer. Adding the lecturer to a friendly is the false-submission case.
* A counted series ignores the override entirely and goes to Table 20's address.
  This is checked against ``setup.json``, the same private file a human arms for
  rule 52, so the protection cannot be bypassed by a flag.

The asymmetry is the point: you can redirect a report that does not count, and
you cannot redirect one that does.
"""

from __future__ import annotations

import logging
from typing import Any

LOGGER = logging.getLogger(__name__)


def resolve(config: Any, opponent: str, override: str) -> tuple[str, str]:
    """Pick the recipient for one report.

    Input:  ``override`` -- comma-separated addresses from ``--to``, or "".
    Output: ``(recipient, refusal)``. A non-empty refusal means do not send.
    """
    fixed = str(config.email.get("recipient", ""))
    wanted = ", ".join(part.strip() for part in override.split(",") if part.strip())
    if not wanted:
        return fixed, ""

    counted, reason = config.counted_series(opponent)
    if counted:
        return "", (
            f"--to was given for a COUNTED series against {opponent!r}, whose recipient is "
            f"fixed by Appendix F Table 20 and is not ours to redirect. The sign-off on "
            f"record is: {reason}. Send it without --to, or disarm the pairing first."
        )
    LOGGER.info("friendly report: sending to %s and NOT to the league address", wanted)
    return wanted, ""
