# Sub-games played outside the declared series — best2934 vs gal-roy1

These logs and configs record real sub-games really played against gal-roy1 on
2026-08-14, between 13:53 and 14:18 UTC. They are kept because deleting played
evidence would be worse than filing it. They are **not** part of the reported
series, and they live in this subdirectory so that the artifact globs — which
are deliberately non-recursive — cannot see them.

## Why they are not in the report

The declared series is six sub-games. Two independent records say so:

- `declaration_best2934-vs-gal-roy1.json` carries `num_sub_games: 6`;
- the series was settled publicly with gal-roy1 as **six of six, 75–35, 5–1**,
  and they audited it barrier by barrier when we (wrongly) suspected a rule-47
  defect in our own thief.

`refresh_result` rebuilds the series from *every* `log_<game_id>_g*.json` on
disk, so these twelve later sub-games were being folded into that settled six
under the same `game_id`. The published result silently became eighteen
sub-games and stopped matching the number both teams had agreed.

## What that produced

Two result artifacts for one `game_id` and one `game_uid`, disagreeing with
each other and with the settled number:

    cop repo    115–55, 5–3, num_sub_games 8   (best2934 police in ALL 8)
    thief repo   95–55, 9–1, num_sub_games 10
    agreed        75–35, 5–1, num_sub_games 6

Filing either would have been the rule-35 contradiction that voids a match for
**both** teams — and this was the series we were about to designate as one of
the two counted games we need in order to pass.

Rebuilt from the declared six alone, both repositories now produce 75–35, 5–1
with an identical `mutual_agreement.sha256`. Nothing about the series changed;
only which sub-games the report is assembled from.

## The second cause, which was in the code

`series_logs` merged the two repositories into a dict keyed on the filename.
Against gal-roy1 both repos numbered from `g01`, so the same filename named two
different sub-games and one silently overwrote the other. Fixed 2026-08-15 to
key on `(sub_game_number, role)`; see
`tests/unit/test_services/test_cross_repo_log_collision.py`.
