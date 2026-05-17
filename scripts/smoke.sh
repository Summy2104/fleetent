#!/usr/bin/env bash
# Smoke test: exercise key agent flows and report PASS/FAIL.
set -euo pipefail

PASS=0; FAIL=0

check() {
    local label="$1"; local result="$2"; local pattern="$3"
    if echo "$result" | grep -qi "$pattern"; then
        echo "PASS: $label"; PASS=$((PASS+1))
    else
        echo "FAIL: $label (got: $(echo "$result" | head -1))"; FAIL=$((FAIL+1))
    fi
}

echo "=== Session 1: tool use ==="
rm -f data/traces.jsonl data/memories.jsonl

OUT=$(uv run mini-agent "What is 99 * 101?")
check "calculate 99*101=9999" "$OUT" "9[,.]\\?999"

OUT=$(uv run mini-agent "What time is it right now? Reply with just the UTC time.")
check "get_current_time returns UTC" "$OUT" "UTC"

if [ -f data/traces.jsonl ]; then echo "PASS: traces.jsonl written"; PASS=$((PASS+1))
else echo "FAIL: traces.jsonl missing"; FAIL=$((FAIL+1)); fi

echo ""
echo "=== Session 2: cross-session memory ==="
rm -f data/memories.jsonl

uv run mini-agent "My name is SmokeTestUser and I only want responses in English." > /dev/null
if [ -f data/memories.jsonl ]; then echo "PASS: memories.jsonl written"; PASS=$((PASS+1))
else echo "FAIL: memories.jsonl missing"; FAIL=$((FAIL+1)); fi

OUT=$(uv run mini-agent "What is my name?")
check "memory: recalls SmokeTestUser" "$OUT" "SmokeTestUser"

echo ""
echo "=== Summary ==="
echo "PASS: $PASS  FAIL: $FAIL"
[ "$FAIL" -eq 0 ] && exit 0 || exit 1
