#!/usr/bin/env bash
set -euo pipefail
CHAGENT="/home/yusuf/dev/chagent/chagent.py"
PASS=0; FAIL=0
RED='\033[91m'; GREEN='\033[92m'; Y='\033[93m'; RST='\033[0m'
ok(){ echo -e "${GREEN}✔ $*${RST}"; PASS=$((PASS+1)); }
fail(){ echo -e "${RED}✘ $*${RST}"; FAIL=$((FAIL+1)); }
say(){ echo -e "${Y}▶ $*${RST}"; }

TMPBASE=$(mktemp -d /tmp/chagent-test-XXXXXX)
trap 'rm -rf "$TMPBASE"' EXIT

# Helper: setup fake HOME with opencode.json and agents
setup_fake() {
  local ID=$1
  local BASE="$TMPBASE/$ID"
  mkdir -p "$BASE/cfg/agents" "$BASE/omo"
  cat > "$BASE/cfg/opencode.json" <<'JSON'
{
  "model": "omniroute/auto/best-free",
  "small_model": "omniroute/auto/best-free",
  "agent": {
    "oracle": {"model": "omniroute/auto/best-free"},
    "explore": {"model": "omniroute/auto/best-free"}
  }
}
JSON
  cat > "$BASE/cfg/agents/ctf.md" <<'MD'
---
description: Test agent
model: omniroute/auto/best-free
---
hello
MD
  # omo.jsonc with comments + URL
  cat > "$BASE/omo/omo.jsonc" <<'JSONC'
// OMO config with comment
{
  "$schema": "https://raw.githubusercontent.com/code-yeongyu/oh-my-openagent/dev/assets/omo.schema.json",
  "[opencode]": {
    "agents": {
      // pin oracle deliberately different to test conflict flag
      "oracle": {"model": "omniroute/auto/best-free"},
      "explore": {"model": "opencode/x-preview-f-free"}
    },
    "categories": {
      "quick": {"model": "omniroute/auto/best-free"},
      "artistry": {"model": "omniroute/auto/best-free"}
    }
  }
}
JSONC
  echo "$BASE"
}

# Test 1: JSONC stripper preserves URL
say "Test 1: JSONC stripper preserves URL //"
# direct test
BASE=$(setup_fake t1)
export OMO_CONFIG_DIR="$BASE/cfg"
export CHAGENT_OMO_JSONC="$BASE/omo/omo.jsonc"
python3 - <<PY
import json
import sys
sys.path.insert(0, "/home/yusuf/dev/chagent")
import importlib.util
spec = importlib.util.spec_from_file_location("chagent", "/home/yusuf/dev/chagent/chagent.py")
mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)
raw = open("$BASE/omo/omo.jsonc").read()
data = json.loads(mod.strip_jsonc(raw))
assert data["\$schema"].startswith("https://"), "URL rusak"
assert data["[opencode]"]["agents"]["oracle"]["model"] == "omniroute/auto/best-free"
print("strip ok")
PY
if [ $? -eq 0 ]; then ok "JSONC strip preserves URL"; else fail "JSONC strip"; fi

# Test each scenario using chagent menu via stdin

# Need to re-setup for isolation per test
# Test 2: show displays pins + conflict flag
say "Test 2: show displays pins + conflict"
BASE=$(setup_fake t2)
export OMO_CONFIG_DIR="$BASE/cfg"
export CHAGENT_OMO_JSONC="$BASE/omo/omo.jsonc"
OUT=$(printf '1\n0\n' | python3 "$CHAGENT" 2>&1)
if echo "$OUT" | grep -q "Pin OMO" && echo "$OUT" | grep -q "oracle" && echo "$OUT" | grep -q "quick"; then
  ok "show pins displayed"
else
  fail "show pins"
  echo "$OUT" | tail -20
fi
if echo "$OUT" | grep -q "beda vs opencode"; then
  ok "conflict flag shown"
else
  fail "conflict flag"
fi

# Test 3: change-one updates both layers + backups + .md
say "Test 3: change-one oracle"
BASE=$(setup_fake t3)
export OMO_CONFIG_DIR="$BASE/cfg"
export CHAGENT_OMO_JSONC="$BASE/omo/omo.jsonc"
# options sorted: categories+agents => artistry, explore, oracle, quick, etc. Find oracle index
# We need to probe menu: send '2' then list: capture options order by running with debug? 
# Easier: brute force - change-one picks sorted options. Let's list options via python
OPTS=$(python3 - <<PY
import os
os.environ["OMO_CONFIG_DIR"]="$BASE/cfg"
os.environ["CHAGENT_OMO_JSONC"]="$BASE/omo/omo.jsonc"
import json
cfg=json.load(open("$BASE/cfg/opencode.json"))
agents=cfg.get("agent",{})
KNOWN_AGENTS=["build","plan","general","explore","deep","metis","momus","multimodal-looker","oracle","librarian","atlas","hephaestus","prometheus","Sisyphus-Junior","sisyphus"]
KNOWN_CATS=["visual-engineering","ultrabrain","deep","artistry","quick","unspecified-low","unspecified-high","writing"]
options=sorted(set(list(agents.keys()) + [a for a in KNOWN_AGENTS if a not in agents] + [c for c in KNOWN_CATS if c not in agents and c not in KNOWN_AGENTS]))
# actually code does sorted(set(options)) where options = names + KNOWN_AGENTS not in names + KNOWN_CATS not in options
# reproduce exactly:
names=sorted(set(list(agents.keys())))
options2=names + [a for a in KNOWN_AGENTS if a not in names]
for cat in KNOWN_CATS:
    if cat not in options2:
        options2.append(cat)
options2=sorted(set(options2))
for i,o in enumerate(options2,1):
    print(f"{i}:{o}")
PY
)
echo "$OPTS"
ORACLE_IDX=$(echo "$OPTS" | grep -n ":oracle$" | cut -d: -f1)
echo "oracle idx $ORACLE_IDX"
printf "2\n${ORACLE_IDX}\n1\n1\n0\n" | python3 "$CHAGENT" 2>&1 | tail -5
# Verify both files updated to quick pick 1 = omniroute/auto/best-free? Actually quick pick 1 is omniroute/auto/best-free same as old, so change not visible. Use quick pick 6 = opencode/x-preview-f-free
# redo with pick 6
BASE=$(setup_fake t3b)
export OMO_CONFIG_DIR="$BASE/cfg"
export CHAGENT_OMO_JSONC="$BASE/omo/omo.jsonc"
OPTS=$(python3 - <<PY
import json, os
os.environ["OMO_CONFIG_DIR"]="$BASE/cfg"
cfg=json.load(open("$BASE/cfg/opencode.json"))
agents=cfg.get("agent",{})
KNOWN_AGENTS=["build","plan","general","explore","deep","metis","momus","multimodal-looker","oracle","librarian","atlas","hephaestus","prometheus","Sisyphus-Junior","sisyphus"]
KNOWN_CATS=["visual-engineering","ultrabrain","deep","artistry","quick","unspecified-low","unspecified-high","writing"]
names=sorted(set(list(agents.keys())))
options2=names + [a for a in KNOWN_AGENTS if a not in names]
for cat in KNOWN_CATS:
    if cat not in options2:
        options2.append(cat)
options2=sorted(set(options2))
for i,o in enumerate(options2,1):
    print(f"{i}:{o}")
PY
)
ORACLE_IDX=$(echo "$OPTS" | grep -n ":oracle$" | cut -d: -f1)
printf "2\n${ORACLE_IDX}\n1\n6\n0\n" | python3 "$CHAGENT" 2>&1 | grep -q "Tersimpan" && ok "change-one saved" || fail "change-one save"
python3 - <<PY
import json
op=json.load(open("$BASE/cfg/opencode.json"))
assert op["agent"]["oracle"]["model"]=="opencode/x-preview-f-free", op["agent"]["oracle"]
import importlib.util
spec=importlib.util.spec_from_file_location("c","/home/yusuf/dev/chagent/chagent.py")
m=importlib.util.module_from_spec(spec); spec.loader.exec_module(m)
omo=json.loads(m.strip_jsonc(open("$BASE/omo/omo.jsonc").read()))
assert omo["[opencode]"]["agents"]["oracle"]["model"]=="opencode/x-preview-f-free"
print("both layers ok")
PY
if [ $? -eq 0 ]; then ok "change-one both layers"; else fail "change-one both layers"; fi
if ls "$BASE/cfg/backups"/opencode.json.*.auto.bak >/dev/null 2>&1 && ls "$BASE/cfg/backups"/omo.jsonc.*.auto.bak >/dev/null 2>&1; then ok "backups both"; else fail "backups"; ls "$BASE/cfg/backups" 2>&1 | head; fi

# Test 4: .md frontmatter edit
say "Test 4: .md frontmatter"
BASE=$(setup_fake t4)
export OMO_CONFIG_DIR="$BASE/cfg"
export CHAGENT_OMO_JSONC="$BASE/omo/omo.jsonc"
OPTS=$(python3 - <<PY
import json
cfg=json.load(open("$BASE/cfg/opencode.json"))
agents=cfg.get("agent",{})
KNOWN_AGENTS=["build","plan","general","explore","deep","metis","momus","multimodal-looker","oracle","librarian","atlas","hephaestus","prometheus","Sisyphus-Junior","sisyphus"]
KNOWN_CATS=["visual-engineering","ultrabrain","deep","artistry","quick","unspecified-low","unspecified-high","writing"]
names=sorted(set(list(agents.keys())))
options2=names + [a for a in KNOWN_AGENTS if a not in names]
for cat in KNOWN_CATS:
    if cat not in options2:
        options2.append(cat)
options2=sorted(set(options2))
for i,o in enumerate(options2,1):
    print(f"{i}:{o}")
PY
)
CTF_IDX=$(echo "$OPTS" | grep -n ":ctf$" | cut -d: -f1 || echo "")
# ctf not in options because it's not in KNOWN lists and not in opencode.json agents — but we add ctf via custom? Actually options includes only agents+KNOWN, ctf not included. So test change-one on ctf requires via add? Instead test via direct edit: we added code to handle md if name matches file. Oracle already tested .md? ctf is separate. We test editing ctf via change-one after adding it as override? For now test that editing oracle does NOT affect ctf, but ctf frontmatter stays. Instead add test for ctf via manual edit function
python3 - <<PY
import importlib.util
spec=importlib.util.spec_from_file_location("c","/home/yusuf/dev/chagent/chagent.py")
m=importlib.util.module_from_spec(spec); spec.loader.exec_module(m)
import os
os.environ["OMO_CONFIG_DIR"]="$BASE/cfg"
os.environ["CHAGENT_OMO_JSONC"]="$BASE/omo/omo.jsonc"
m.edit_md_frontmatter_model("ctf", "opencode/x-preview-f-free")
assert open("$BASE/cfg/agents/ctf.md").read().count("opencode/x-preview-f-free")==1
print("md edit ok")
PY
if [ $? -eq 0 ]; then ok ".md frontmatter edit"; else fail ".md frontmatter"; fi

# Test 5: repin all menu 10
say "Test 5: repin all"
BASE=$(setup_fake t5)
export OMO_CONFIG_DIR="$BASE/cfg"
export CHAGENT_OMO_JSONC="$BASE/omo/omo.jsonc"
printf '10\n1\n1\ny\n0\n' | python3 "$CHAGENT" 2>&1 | grep -q "Semua.*pin OMO" && ok "repin all" || fail "repin all"
python3 - <<PY
import json, importlib.util
spec=importlib.util.spec_from_file_location("c","/home/yusuf/dev/chagent/chagent.py")
m=importlib.util.module_from_spec(spec); spec.loader.exec_module(m)
omo=json.loads(m.strip_jsonc(open("$BASE/omo/omo.jsonc").read()))
for sec in ("agents","categories"):
    for k,v in omo["[opencode]"][sec].items():
        assert v["model"]=="omniroute/auto/best-free", f"{sec}.{k} {v}"
print("repin ok")
PY
if [ $? -eq 0 ]; then ok "repin all verified"; else fail "repin verify"; fi

# Test 6: corrupt omo.jsonc handling
say "Test 6: corrupt omo.jsonc"
BASE=$(setup_fake t6)
echo '{ broken json' > "$BASE/omo/omo.jsonc"
export OMO_CONFIG_DIR="$BASE/cfg"
export CHAGENT_OMO_JSONC="$BASE/omo/omo.jsonc"
OUT=$(printf '1\n0\n' | python3 "$CHAGENT" 2>&1)
if echo "$OUT" | grep -q "omo.jsonc rusak"; then ok "corrupt flagged"; else fail "corrupt flagged"; echo "$OUT" | tail; fi
# change-one should warn and not crash, but opencode.json still saves
printf '2\n1\n1\n1\n0\n' | python3 "$CHAGENT" 2>&1 | grep -q "corrupt" && ok "corrupt change handled" || fail "corrupt change"

# Test 7: regresi tanpa omo.jsonc
say "Test 7: no omo.jsonc regression"
BASE=$(setup_fake t7)
rm "$BASE/omo/omo.jsonc"
export OMO_CONFIG_DIR="$BASE/cfg"
export CHAGENT_OMO_JSONC="$BASE/omo/omo.jsonc"
OUT=$(printf '1\n0\n' | python3 "$CHAGENT" 2>&1)
if echo "$OUT" | grep -q "tidak ada file"; then ok "no omo handled"; else fail "no omo"; echo "$OUT" | tail; fi
printf '2\n1\n1\n1\n0\n' | python3 "$CHAGENT" 2>&1 | grep -q "Tersimpan" && ok "no omo change-one works" || fail "no omo change"

# Test 8: preset with categories
say "Test 8: preset"
BASE=$(setup_fake t8)
export OMO_CONFIG_DIR="$BASE/cfg"
export CHAGENT_OMO_JSONC="$BASE/omo/omo.jsonc"
printf '3\n1\n1\ny\n0\n' | python3 "$CHAGENT" 2>&1 | grep -q "sekarang pakai" && ok "preset" || fail "preset"
python3 - <<PY
import json, importlib.util
spec=importlib.util.spec_from_file_location("c","/home/yusuf/dev/chagent/chagent.py")
m=importlib.util.module_from_spec(spec); spec.loader.exec_module(m)
omo=json.loads(m.strip_jsonc(open("$BASE/omo/omo.jsonc").read()))
assert "quick" in omo["[opencode]"]["categories"]
print("preset categories ok")
PY
if [ $? -eq 0 ]; then ok "preset categories"; else fail "preset categories"; fi

echo ""
echo "RESULTS: $PASS passed, $FAIL failed"
if [ $FAIL -ne 0 ]; then exit 1; fi
