# Sunday Source-Triage Schema

## Primary node

`play`

A node is a play. Teams and games are attributes until SCHEMA.md is revised.

## Allowed attributes

- `game`
- `offense_team_name`
- `defense_team_name`
- `source`
- `external_id`
- `source_play_class`
- `tag_state`

The Play Finder returns source evidence separately from program-scoped tag state. [FACT — `app/wedge.py`]

`plays.play_family` and `plays.formation` may be read only for the required UNKNOWN counts. Both columns exist on the play row. [FACT — `db/schema.sql`]

Edges: NOT IN THE EVIDENCE.

Customer, buyer, school, and quote nodes are forbidden. `customer.md` is NOT IN THE EVIDENCE.
