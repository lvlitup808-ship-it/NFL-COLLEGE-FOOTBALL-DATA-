# Pilot Credentials Example

Commit placeholders only. Never commit the values printed by the provisioner.

| Seat | Role | Email example | Secret placeholder |
| --- | --- | --- | --- |
| Owner | `owner` | `owner@example.invalid` | `FIELDMIND_OWNER_TOKEN=<printed-once-token>` |
| Coach | `coach` | `coach@example.invalid` | `FIELDMIND_COACH_TOKEN=<printed-once-token>` |
| GA A | `ga` | `ga-a@example.invalid` | `FIELDMIND_GA_A_TOKEN=<printed-once-token>` |
| GA B | `ga` | `ga-b@example.invalid` | `FIELDMIND_GA_B_TOKEN=<printed-once-token>` |

Create the owner first:

```bash
docker compose run --rm web python scripts/provision_pilot_user.py \
  --program-name 'Demo Football Program' \
  --email 'owner@example.invalid' \
  --display-name 'Demo Owner' \
  --role owner \
  --days 7
```

Copy the printed `program_id` into your shell. This is an example placeholder, not a real program ID:

```bash
export FIELDMIND_PROGRAM_ID='<program-uuid-printed-above>'
```

Create the coach and two independent GA seats in that same program:

```bash
docker compose run --rm web python scripts/provision_pilot_user.py \
  --program-id "$FIELDMIND_PROGRAM_ID" \
  --email 'coach@example.invalid' \
  --display-name 'Demo Coach' \
  --role coach \
  --days 7

docker compose run --rm web python scripts/provision_pilot_user.py \
  --program-id "$FIELDMIND_PROGRAM_ID" \
  --email 'ga-a@example.invalid' \
  --display-name 'Demo GA A' \
  --role ga \
  --days 7

docker compose run --rm web python scripts/provision_pilot_user.py \
  --program-id "$FIELDMIND_PROGRAM_ID" \
  --email 'ga-b@example.invalid' \
  --display-name 'Demo GA B' \
  --role ga \
  --days 7
```

Each command prints one bearer token once; only its SHA-256 hash is stored. Keep the four raw tokens outside the repository and paste one into the UI's `Pilot bearer token` field. [Source: `scripts/provision_pilot_user.py`; `README.md`]
