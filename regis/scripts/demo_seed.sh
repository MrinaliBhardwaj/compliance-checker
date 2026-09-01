#!/usr/bin/env bash
# Repeatable demo state for a walkthrough. Resets the SQLite dev DB, signs up a
# growth-stage NBFC, generates its calendar, publishes three legal updates that
# exercise all three matcher verdicts, and advances a few obligations through the
# maker-checker lifecycle so the tracker has something to show.
#
#   cd regis/backend && ../scripts/demo_seed.sh
#
# Requires the API on :8000 with REGIS_CONTENT_ADMIN_EMAILS including DEMO_EMAIL
# (publishing legal updates is allowlist-gated and crosses tenants by design).
set -euo pipefail

API="${API:-http://localhost:8000}"
DEMO_EMAIL="${DEMO_EMAIL:-demo@regis.example}"
PASS="${PASS:-goodpassword1}"
J="$(mktemp -t regis-demo-XXXXXX.cookies)"
trap 'rm -f "$J"' EXIT

say() { printf '\n\033[1m%s\033[0m\n' "$*"; }
post() { curl -sS -b "$J" -c "$J" -X POST "$API$1" -H 'content-type: application/json' -d "$2"; }

say "1/5  signing up $DEMO_EMAIL"
curl -sS -c "$J" -b "$J" -X POST "$API/auth/signup" -H 'content-type: application/json' \
  -d "{\"organization_name\":\"Meridian Capital\",\"entity_legal_name\":\"Meridian Capital Ltd\",\"email\":\"$DEMO_EMAIL\",\"password\":\"$PASS\"}" \
  -o /tmp/regis_signup.json -w '     signup %{http_code}\n'
ENTITY=$(python3 -c "import json;print(json.load(open('/tmp/regis_signup.json'))['entity_id'])")

say "2/5  generating the compliance calendar"
PROFILE='{"asset_size":"450","turnover":"80","net_worth":"120","net_profit":"9",
"employee_count":45,"branch_count":6,"deposit_taking":"No","is_listed":"No",
"has_listed_debt":"No","gst_registered":"Yes","operating_states":["MH","KA"],
"has_foreign_investment":"Yes","has_nonresident_payments":"No",
"has_international_transactions":"No","has_reportable_accounts":"No",
"has_msme_dues":"Yes","has_sbo":"Yes","has_capital_changes":"Yes","has_ecb":"No",
"has_odi":"No","has_floating_rate_retail":"Yes","does_digital_lending":"Yes",
"has_borrowings":"Yes","is_secured_lender":"Yes","has_dlg_arrangements":"No",
"has_eligible_bonus_employees":"Yes","is_isd":"No","is_large_corporate":"No",
"has_eq_levy":"No"}'
post /onboarding/calendar/generate "{\"entity_id\":\"$ENTITY\",\"raw_input\":$PROFILE}" \
  | python3 -c "import json,sys;d=json.load(sys.stdin);print(f\"     {d['company_obligations']} obligations, {d['instances']} dated instances\")"

say "3/5  publishing legal updates (one per matcher verdict)"
# AFFECTS: gates on a field this profile answers -> deterministic match.
post /legal-updates '{"title":"RBI tightens Default Loss Guarantee caps for digital lending",
  "law_id":"law_rbi_digital","affects_filter":{"does_digital_lending":true},
  "source_url":"https://www.rbi.org.in/Scripts/BS_ViewMasDirections.aspx",
  "ai_summary":"DLG cover on a digital lending portfolio is capped; partners must re-paper arrangements.",
  "ai_impact_note":"Review DLG contracts and the monthly cap monitoring line."}' >/dev/null
# NOT_APPLICABLE: fails on a known value -> correctly filtered out of the feed.
post /legal-updates '{"title":"SEBI LODR amendment - listed equity disclosure timelines",
  "law_id":"law_sebi_lodr","affects_filter":{"is_listed":true},
  "source_url":"https://www.sebi.gov.in/",
  "ai_summary":"Shortened disclosure windows for listed entities."}' >/dev/null
# MAY_AFFECT: references a field no profile answers -> surfaced, never dropped.
post /legal-updates '{"title":"Draft directions on cross-border payment aggregators",
  "law_id":"law_fema","affects_filter":{"is_cross_border_pa":true},
  "source_url":"https://www.rbi.org.in/",
  "ai_summary":"Registration regime proposed for cross-border payment aggregators."}' >/dev/null
curl -sS -b "$J" -c "$J" "$API/legal-updates" \
  | python3 -c "
import json,sys
for u in json.load(sys.stdin):
    print(f\"     [{u['match']:15s}] {u['title'][:62]}  ({u['affected_obligations']} obligations)\")"

say "4/5  advancing a few obligations through maker-checker"
curl -sS -b "$J" -c "$J" "$API/obligations/instances?status=pending&limit=4" \
  -o /tmp/regis_inst.json
python3 - <<'PY' > /tmp/regis_ids.txt
import json
d = json.load(open('/tmp/regis_inst.json'))
rows = d if isinstance(d, list) else d.get('items', d.get('instances', []))
print('\n'.join(r['id'] for r in rows[:3]))
PY
mapfile -t IDS < /tmp/regis_ids.txt
[ "${#IDS[@]}" -ge 3 ] && {
  post "/obligations/instances/${IDS[0]}/start"  '{}' >/dev/null
  post "/obligations/instances/${IDS[1]}/start"  '{}' >/dev/null
  post "/obligations/instances/${IDS[1]}/submit" '{"override_evidence":true,"reason":"demo seed"}' >/dev/null
  post "/obligations/instances/${IDS[2]}/start"  '{}' >/dev/null
  post "/obligations/instances/${IDS[2]}/submit" '{"override_evidence":true,"reason":"demo seed"}' >/dev/null
  # Approve needs the evidence gate waived — the gate refusing an unevidenced
  # completion is a feature worth showing, so IDS[1] is deliberately left sitting
  # at ready_for_review for the demo to hit it live.
  post "/obligations/instances/${IDS[2]}/approve" \
    '{"override_evidence":true,"reason":"demo seed - evidence waived"}' >/dev/null
  echo "     1 in progress, 1 awaiting review (blocked at the evidence gate), 1 completed"
}

say "5/5  final dashboard"
curl -sS -b "$J" -c "$J" "$API/obligations/dashboard" \
  | python3 -c "
import json,sys
d=json.load(sys.stdin)
print(f\"     health {d['health_score']}  tiles {d['tiles']}\")"
printf '\n\033[1mReady.\033[0m  Log in at http://localhost:3000 as %s / %s\n\n' "$DEMO_EMAIL" "$PASS"
