#!/usr/bin/env bash
# Sandbox pentest for untrusted bot execution.
#
# Verifies the 4-layer design actually holds:
#   1. (netns)   empty network namespace -> no external connectivity
#   2. (seccomp) dangerous syscalls (ptrace/mount/...) are KILLed
#   3. (iptables/gVisor) defense-in-depth (configured at host/runtime)
#   4. legitimate Python bots still run (compute works)
#
# Run on the Linux host (WSL2 or the worker container):
#   bash deploy/sandbox_test.sh
#
# Env overrides: NSJAIL (binary), CFG (nsjail config), WORK (bind-mounted dir).
set -u
NSJAIL="${NSJAIL:-nsjail}"
CFG="${CFG:-$(cd "$(dirname "$0")" && pwd)/nsjail.cfg}"
WORK="${WORK:-/work}"
POLICY_SRC="${POLICY_SRC:-$(cd "$(dirname "$0")" && pwd)/seccomp.policy}"

mkdir -p "$WORK"
# Ensure the seccomp policy is where the config expects it.
if [ -f "$POLICY_SRC" ] && [ "$(realpath "$POLICY_SRC")" != "/etc/nsjail/seccomp.policy" ]; then
    sudo install -m 0644 "$POLICY_SRC" /etc/nsjail/seccomp.policy 2>/dev/null || \
        cp "$POLICY_SRC" /etc/nsjail/seccomp.policy 2>/dev/null || true
fi

cat > "$WORK/t_compute.py" <<'PY'
import hashlib, json
h = hashlib.sha256(b"nexus").hexdigest()
print("compute OK", h[:8])
PY

cat > "$WORK/t_net.py" <<'PY'
import socket
try:
    s = socket.create_connection(("1.1.1.1", 53), timeout=3)
    print("NET_LEAK: connected to external host!")
except OSError as e:
    print(f"NET_BLOCKED (good): {e}")
PY

cat > "$WORK/t_seccomp.py" <<'PY'
import ctypes
# ptrace is not in the allowlist -> must be killed by seccomp.
libc = ctypes.CDLL("libc.so.6", use_errno=True)
ret = libc.ptrace(0, 0, 0, 0)  # PTRACE_TRACEME
print("SECCOMP_FAIL: ptrace was allowed (ret=%d)" % ret)
PY

pass=0; fail=0
check() { # $1=name $2=expected-substring $3=output
    if printf '%s' "$3" | grep -q "$2"; then
        echo "PASS  $1"; pass=$((pass+1))
    else
        echo "FAIL  $1"; echo "      output: $3"; fail=$((fail+1))
    fi
}

out_compute=$("$NSJAIL" -C "$CFG" -- /usr/bin/python3 "$WORK/t_compute.py" 2>&1)
check "compute (python bot runs)" "compute OK" "$out_compute"

out_net=$("$NSJAIL" -C "$CFG" -- /usr/bin/python3 "$WORK/t_net.py" 2>&1)
check "net egress blocked" "NET_BLOCKED" "$out_net"

out_sec=$("$NSJAIL" -C "$CFG" -- /usr/bin/python3 "$WORK/t_seccomp.py" 2>&1)
if printf '%s' "$out_sec" | grep -q "SIGSYS\|terminated with signal"; then
    echo "PASS  seccomp kills ptrace"; pass=$((pass+1))
elif printf '%s' "$out_sec" | grep -q "SECCOMP_FAIL"; then
    echo "FAIL  seccomp kills ptrace"; echo "      output: $out_sec"; fail=$((fail+1))
else
    echo "FAIL  seccomp kills ptrace (unexpected)"; echo "      output: $out_sec"; fail=$((fail+1))
fi

echo "----"
echo "PASS=$pass FAIL=$fail"
[ "$fail" -eq 0 ]
