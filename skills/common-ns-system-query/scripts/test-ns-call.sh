#!/bin/bash
# Integration tests for scripts/ns-call.sh
# fleetent: the wrapper validates uid + builds the armada__armada_<method>
# MCP-call args and prints them to stdout (the agent then issues the tool call).

set -uo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
WRAPPER="$SCRIPT_DIR/ns-call.sh"

fail=0

assert_contains() {
  local name="$1" needle="$2" haystack="$3"
  if [[ "$haystack" == *"$needle"* ]]; then
    echo "  PASS: $name"
  else
    echo "  FAIL: $name"
    echo "    needle:   $needle"
    echo "    haystack: $haystack"
    fail=$((fail + 1))
  fi
}

assert_not_contains() {
  local name="$1" needle="$2" haystack="$3"
  if [[ "$haystack" != *"$needle"* ]]; then
    echo "  PASS: $name"
  else
    echo "  FAIL: $name (should not contain '$needle')"
    echo "    haystack: $haystack"
    fail=$((fail + 1))
  fi
}

echo "== Test 1: missing all args =="
out=$("$WRAPPER" 2>&1 || true)
assert_contains "usage hint on missing uid" "usage:" "$out"

echo "== Test 2: invalid uid format =="
out=$("$WRAPPER" "badformat" get "/v1/countries" 2>&1 || true)
assert_contains "invalid uid rejected" "ERR_AUTH_INVALID" "$out"

echo "== Test 3: valid uid, armada tool call built with _meta =="
out=$("$WRAPPER" "U05K7R8TBST" get "/v1/countries" 2>&1)
assert_contains "armada call emitted" "ARMADA_CALL" "$out"
assert_contains "path injected" "path=/v1/countries" "$out"
assert_contains "slackUserId injected" '_meta={"slackUserId":"U05K7R8TBST"}' "$out"
assert_contains "method mapped" "armada__armada_get" "$out"

echo "== Test 4: invalid method =="
out=$("$WRAPPER" "U05K7R8TBST" delete "/v1/countries" 2>&1 || true)
assert_contains "delete rejected" "ERR_METHOD_INVALID" "$out"

echo "== Test 5: duplicate _meta rejected =="
out=$("$WRAPPER" "U05K7R8TBST" get "/v1/countries" '_meta={"foo":"bar"}' 2>&1 || true)
assert_contains "duplicate _meta rejected" "ERR_META_DUPLICATE" "$out"

echo "== Test 6: extra kv args pass through =="
out=$("$WRAPPER" "U05K7R8TBST" get "/v1/customers" 'query_params={"page":1}' 2>&1)
assert_contains "kv passthrough" 'query_params={"page":1}' "$out"

echo "== Test 7: POST method =="
out=$("$WRAPPER" "U05K7R8TBST" post "/v1/accounts/digital_coin" 'body={"platform":"bitget"}' 2>&1)
assert_contains "POST mapped" "armada__armada_post" "$out"
assert_contains "body passthrough" 'body={"platform":"bitget"}' "$out"

echo "== Test 8: bypass mode ignores uid, no _meta injection =="
out=$(NS_CALL_BYPASS=1 "$WRAPPER" "Uxxxxxxxxx" get "/v1/countries" 2>&1)
assert_contains "bypass warning to stderr" "NS_CALL_BYPASS=1" "$out"
assert_contains "bypass still emits armada call" "ARMADA_CALL" "$out"
assert_not_contains "bypass skips _meta" "_meta=" "$out"

echo "== Test 9: bypass mode still requires 3 positional args =="
out=$(NS_CALL_BYPASS=1 "$WRAPPER" 2>&1 || true)
assert_contains "bypass usage enforced" "usage:" "$out"

echo
if [ $fail -gt 0 ]; then
  echo "FAILED: $fail assertion(s)"
  exit 1
else
  echo "OK: all tests passed"
fi
