# gcp_incidents.json

Captured from `https://status.cloud.google.com/incidents.json` on 2026-09-05. Six incidents. Each item was trimmed: `updates` cut to two entries with text shortened to 200 characters, `most_recent_update.text` cut to 300 characters, `affected_products` cut to three.

The first item, `J5ia5t9p3g9Q5Wi7r8Ev`, was hand-edited to look open because no incident was open at capture time:

- `end` set to `null`
- `currently_affected_locations` set to `us-east1`
- `previously_affected_locations` left as `us-central1`

The live item had `end` set and `currently_affected_locations` empty.
