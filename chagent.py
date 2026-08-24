#!/usr/bin/env python3
"""
chagent — Manajer agent OhMyOpenCode / OpenCode
Ganti model agent, preset cepat, backup otomatis. Menu interaktif, zero dependency.

Config yang dikelola (3 lapisan):
  1. ~/.config/opencode/opencode.json   → bagian "agent" + "model" global
  2. ~/.omo/omo.jsonc                   → pin model OMO (agents + categories)
  3. ~/.config/opencode/agents/*.md     → agent custom (frontmatter model)

Backup otomatis      : ~/.config/opencode/backups/ (+ omo.jsonc ikut dibackup)
Preset tersimpan     : ~/.config/opencode/omo-agent-presets.json
"""

import json
import os
import re
import shutil
import subprocess
import sys
from datetime import datetime

# ---------------------------------------------------------------- paths

def config_dir() -> str:
    return os.environ.get("OMO_CONFIG_DIR") or os.path.join(
        os.path.expanduser("~"), ".config", "opencode"
    )

def omo_jsonc_path() -> str:
    return os.environ.get("CHAGENT_OMO_JSONC") or os.path.join(
        os.path.expanduser("~"), ".omo", "omo.jsonc"
    )

CONFIG_PATH = lambda: os.path.join(config_dir(), "opencode.json")          # noqa: E731
BACKUP_DIR = lambda: os.path.join(config_dir(), "backups")                 # noqa: E731
PRESET_PATH = lambda: os.path.join(config_dir(), "omo-agent-presets.json")  # noqa: E731
MODELS_CACHE = lambda: os.path.join(config_dir(), ".chagent-models-cache.txt")  # noqa: E731
AGENTS_MD_DIR = lambda: os.path.join(config_dir(), "agents")               # noqa: E731

MAX_BACKUPS = 30
CACHE_TTL = 24 * 3600  # refresh katalog model tiap 24 jam

# Roster agent bawaan OMO — dipakai buat nawarin override yang belum ada.
KNOWN_AGENTS = [
    "build", "plan", "general", "explore", "deep",
    "metis", "momus", "multimodal-looker", "oracle", "librarian",
    "atlas", "hephaestus", "prometheus", "Sisyphus-Junior", "sisyphus",
]

# Category-agent OMO: model-nya HANYA bisa diatur lewat omo.jsonc.categories,
# opencode.json tidak berpengaruh untuk spawn berbasis category.
KNOWN_CATEGORIES = [
    "visual-engineering", "ultrabrain", "deep", "artistry", "quick",
    "unspecified-low", "unspecified-high", "writing",
]

DEFAULT_PRESETS = {
    "omniroute-free":   "omniroute/auto/best-free",
    "omniroute-coding": "omniroute/auto/coding:free",
    "omniroute-stack":  "omniroute/free-stack",
    "opencode-free":    "opencode/x-preview-f-free",
}

QUICK_MODELS = [
    "omniroute/auto/best-free",
    "omniroute/auto/coding:free",
    "omniroute/free-stack",
    "opencode/big-pickle",
    "opencode/grok-code",
    "opencode/x-preview-f-free",
]

# ---------------------------------------------------------------- util tui

C = {"g": "\033[92m", "y": "\033[93m", "r": "\033[91m", "b": "\033[94m",
     "c": "\033[96m", "0": "\033[0m", "bold": "\033[1m", "dim": "\033[2m"}


def colored(text, *codes):
    if not sys.stdout.isatty():
        return text
    return "".join(C[c] for c in codes) + text + C["0"]


def header(title):
    print()
    print(colored(f"═══ {title} ═══", "c", "bold"))


def ok(msg):
    print(colored(f"  ✔ {msg}", "g"))


def warn(msg):
    print(colored(f"  ⚠ {msg}", "y"))


def err(msg):
    print(colored(f"  ✘ {msg}", "r"))


def ask(prompt, default=""):
    suffix = f" {colored('(' + default + ')', 'dim')}" if default else ""
    try:
        val = input(colored(f"  ? {prompt}{suffix}: ", "b")).strip()
    except (KeyboardInterrupt, EOFError):
        print()
        return None
    return val or default


def confirm(prompt, default_yes=True):
    d = "Y/n" if default_yes else "y/N"
    while True:
        v = ask(f"{prompt} [{d}]")
        if v is None:
            return False
        if not v:
            return default_yes
        if v.lower() in ("y", "ya", "yes"):
            return True
        if v.lower() in ("n", "no", "tidak"):
            return False


def pick_numbered(items, title, fmt=str):
    """Tampilkan daftar bernomor, balikan index terpilih atau None."""
    header(title)
    for i, it in enumerate(items, 1):
        print(f"  {colored(str(i).rjust(2), 'y')}. {fmt(it)}")
    print(f"  {colored(' 0', 'y')}. Batal")
    raw = ask("Pilih nomor")
    if raw is None or not raw.isdigit() or not (0 <= int(raw) <= len(items)):
        return None
    i = int(raw)
    return None if i == 0 else i - 1


# ---------------------------------------------------------------- io config

def load_config(strict=False):
    path = CONFIG_PATH()
    if not os.path.exists(path):
        if strict:
            err(f"Config tidak ditemukan: {path}")
            sys.exit(1)
        return {}
    try:
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
        if not isinstance(data, dict):
            raise ValueError("root bukan object JSON")
        return data
    except Exception as e:
        err(f"opencode.json rusak/tidak valid: {e}")
        warn("Tool menolak menyimpan agar config-mu tidak hancur. Perbaiki manual dulu.")
        if strict:
            sys.exit(1)
        return None


def save_config(cfg):
    path = CONFIG_PATH()
    make_backup(reason="auto")
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(cfg, f, indent=2, ensure_ascii=False)
        f.write("\n")
    # validasi hasil tulisan sebelum replace
    with open(tmp, encoding="utf-8") as f:
        json.load(f)
    os.replace(tmp, path)
    ok(f"Tersimpan → {path}")


def make_backup(reason="manual"):
    path = CONFIG_PATH()
    if not os.path.exists(path):
        return None
    os.makedirs(BACKUP_DIR(), exist_ok=True)
    ts = datetime.now().strftime("%Y%m%d-%H%M%S")
    dst = os.path.join(BACKUP_DIR(), f"opencode.json.{ts}.{reason}.bak")
    shutil.copy2(path, dst)
    # prune backup lama
    backups = sorted(f for f in os.listdir(BACKUP_DIR()) if f.startswith("opencode.json."))
    for old in backups[:-MAX_BACKUPS]:
        try:
            os.remove(os.path.join(BACKUP_DIR(), old))
        except OSError:
            pass
    return dst


# ---------------------------------------------------------------- JSONC helpers (omo.jsonc) — string-aware

def strip_jsonc(text: str) -> str:
    """Strip // and /* */ comments tapi JANGAN rusak URL di dalam string."""
    out, i, n, in_str, esc = [], 0, len(text), False, False
    while i < n:
        c = text[i]
        if in_str:
            out.append(c)
            if esc:
                esc = False
            elif c == "\\":
                esc = True
            elif c == '"':
                in_str = False
            i += 1
            continue
        if c == '"':
            in_str = True
            out.append(c)
            i += 1
            continue
        if c == "/" and i + 1 < n and text[i + 1] == "/":
            while i < n and text[i] != "\n":
                i += 1
            continue
        if c == "/" and i + 1 < n and text[i + 1] == "*":
            i += 2
            while i + 1 < n and not (text[i] == "*" and text[i + 1] == "/"):
                i += 1
            i += 2
            continue
        out.append(c)
        i += 1
    return "".join(out)


def load_omo():
    p = omo_jsonc_path()
    if not os.path.exists(p):
        return {}
    try:
        with open(p, encoding="utf-8") as f:
            raw = f.read()
        return json.loads(strip_jsonc(raw))
    except Exception as e:
        err(f"omo.jsonc rusak/tidak valid: {e}")
        warn("Perbaiki manual dulu — backup otomatis tetap dibuat sebelum tulis ulang.")
        return None


def save_omo(omo):
    p = omo_jsonc_path()
    os.makedirs(BACKUP_DIR(), exist_ok=True)
    ts = datetime.now().strftime("%Y%m%d-%H%M%S")
    if os.path.exists(p):
        shutil.copy2(p, os.path.join(BACKUP_DIR(), f"omo.jsonc.{ts}.auto.bak"))
        # prune omo backup lama (keep 30)
        backups = sorted(f for f in os.listdir(BACKUP_DIR()) if f.startswith("omo.jsonc."))
        for old in backups[:-MAX_BACKUPS]:
            try:
                os.remove(os.path.join(BACKUP_DIR(), old))
            except OSError:
                pass
    tmp = p + ".tmp"
    os.makedirs(os.path.dirname(p), exist_ok=True)
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(omo, f, indent=2, ensure_ascii=False)
        f.write("\n")
    with open(tmp, encoding="utf-8") as f:
        json.load(f)
    os.replace(tmp, p)
    ok(f"Tersimpan → {p} " + colored("(komentar JSONC hilang — backup aman)", "dim"))


def set_model_everywhere(name: str, model: str, cfg: dict) -> None:
    """Tulis model ke 3 lapisan: opencode.json + omo.jsonc agents/categories + .md frontmatter."""
    # Lapisan 1: opencode.json
    cfg.setdefault("agent", {})
    entry = cfg["agent"].get(name)
    if isinstance(entry, dict):
        entry["model"] = model
    else:
        cfg["agent"][name] = {"model": model}
    # Lapisan 2: omo.jsonc agents & categories
    omo = load_omo()
    if omo is None:
        # corrupt — jangan timpa, tapi opencode.json tetap tersimpan oleh caller
        warn("omo.jsonc corrupt — skip sinkronisasi OMO untuk kali ini.")
        return
    # omo bisa {} kalau file belum ada — buat struktur minimal
    oc = omo.get("[opencode]")
    if not isinstance(oc, dict):
        # kalau file kosong atau belum ada [opencode], jangan buat dari nol kecuali ada agents/categories yang dikenali
        # tetap buat agar pin konsisten
        oc = omo.setdefault("[opencode]", {})
    for section in ("agents", "categories"):
        sec = oc.setdefault(section, {})
        ent = sec.get(name)
        if isinstance(ent, dict):
            ent["model"] = model
        elif name in sec or name in KNOWN_CATEGORIES or name in KNOWN_AGENTS:
            sec[name] = {"model": model}
        # kalau name tidak ada di section dan bukan known, jangan buat — biar tidak spam
    # hanya save jika ada perubahan (sudah ada oc)
    # simpan omo.jsonc — caller yang akan save_config(cfg) terpisah
    # kita save omo di sini langsung
    # cek apakah omo punya [opencode] yang baru diisi
    if oc:
        save_omo(omo)
    # Lapisan 3: frontmatter .md — dilakukan terpisah di action_change_one agar bisa backup .md.bak
    # (jangan di sini supaya tidak double-IO saat preset loop banyak agent)


def edit_md_frontmatter_model(name: str, model: str) -> bool:
    """Edit baris model: di file agents/<name>.md jika ada. Return True jika diubah."""
    md_path = os.path.join(AGENTS_MD_DIR(), f"{name}.md")
    if not os.path.exists(md_path):
        return False
    try:
        with open(md_path, encoding="utf-8") as f:
            content = f.read()
        # cari frontmatter block --- ... ---
        m = re.match(r"(\s*---\s*\n)(.*?)(\n---)", content, re.S)
        if not m:
            return False
        fm = m.group(2)
        if re.search(r"^model:\s*.+$", fm, re.M):
            new_fm = re.sub(r"^model:\s*.+$", f"model: {model}", fm, count=1, flags=re.M)
        else:
            # belum ada baris model — sisipkan setelah baris pertama frontmatter
            new_fm = f"model: {model}\n" + fm
        if new_fm == fm:
            return False
        new_content = content[:m.start(2)] + new_fm + content[m.end(2):]
        # backup .md
        shutil.copy2(md_path, md_path + ".bak")
        with open(md_path, "w", encoding="utf-8") as f:
            f.write(new_content)
        ok(f"Frontmatter {name}.md → {model}")
        return True
    except Exception as e:
        warn(f"Gagal edit {name}.md: {e}")
        return False


# ---------------------------------------------------------------- presets

def load_presets():
    path = PRESET_PATH()
    if os.path.exists(path):
        try:
            with open(path, encoding="utf-8") as f:
                data = json.load(f)
            if isinstance(data, dict) and data:
                return data
        except Exception:
            pass
    return dict(DEFAULT_PRESETS)


def save_presets(presets):
    with open(PRESET_PATH(), "w", encoding="utf-8") as f:
        json.dump(presets, f, indent=2, ensure_ascii=False)
        f.write("\n")


# ---------------------------------------------------------------- katalog model

def fetch_models_live():
    """Jalankan `opencode models`, cache hasilnya. Return list id model."""
    cache = MODELS_CACHE()
    fresh = False
    if os.path.exists(cache):
        age = datetime.now().timestamp() - os.path.getmtime(cache)
        if age < CACHE_TTL and os.path.getsize(cache) > 0:
            fresh = True
    if not fresh:
        try:
            res = subprocess.run(
                ["opencode", "models"], capture_output=True, text=True, timeout=30
            )
            lines = [l.strip() for l in res.stdout.splitlines()]
            lines = [l for l in lines if "/" in l and " " not in l]
            if lines:
                with open(cache, "w", encoding="utf-8") as f:
                    f.write("\n".join(sorted(set(lines))))
        except (OSError, subprocess.TimeoutExpired):
            pass  # pakai cache lama / seed statis
    models = []
    if os.path.exists(cache):
        with open(cache, encoding="utf-8") as f:
            models = [l.strip() for l in f if l.strip()]
    # fallback seed kalau kosong total
    for m in QUICK_MODELS:
        if m not in models:
            models.append(m)
    return sorted(models)


def is_free(model_id):
    m = model_id.lower()
    return "free" in m


def pick_model(cfg):
    """Picker model: quick picks → gratisan → cari semua → manual."""
    opts = [
        ("Quick pick (yang sering dipakai)", "quick"),
        ("Model GRATIS (filter dari katalog live)", "free"),
        ("Cari di semua model (ketik kata kunci)", "search"),
        ("Ketik manual (misal omniroute/auto/best-free)", "manual"),
    ]
    i = pick_numbered(opts, "PILIH SUMBER MODEL", fmt=lambda o: o[0])
    if i is None:
        return None
    mode = opts[i][1]

    if mode == "quick":
        j = pick_numbered(QUICK_MODELS, "QUICK PICK", fmt=lambda m: m)
        return QUICK_MODELS[j] if j is not None else None

    print(colored("  ...memuat katalog model (opencode models)...", "dim"))
    catalog = fetch_models_live()

    if mode == "free":
        frees = [m for m in catalog if is_free(m)]
        j = pick_numbered(frees, f"MODEL GRATIS ({len(frees)} buah)", fmt=lambda m: m)
        return frees[j] if j is not None else None

    if mode == "search":
        kw = ask("Kata kunci (misal 'claude', 'gemini', 'kimi')")
        if not kw:
            return None
        hits = [m for m in catalog if kw.lower() in m.lower()][:60]
        if not hits:
            warn("Tidak ketemu.")
            return None
        j = pick_numbered(hits, f"HASIL '{kw}' ({len(hits)})", fmt=lambda m: m)
        return hits[j] if j is not None else None

    # manual
    v = ask("Model ID lengkap")
    if v is None:
        return None
    if "/" not in v:
        warn("Format biasanya provider/model (mis. opencode/gpt-5). Tetep dipakai apa adanya.")
    return v


# ---------------------------------------------------------------- tampilan agent

def read_md_agent(path):
    """Ambil (nama, model|None, deskripsi singkat) dari file .md frontmatter."""
    name = os.path.splitext(os.path.basename(path))[0]
    model, desc = None, ""
    try:
        with open(path, encoding="utf-8") as f:
            content = f.read(4096)
        m = re.match(r"\s*---\s*\n(.*?)\n---", content, re.S)
        if m:
            fm = m.group(1)
            mm = re.search(r"^model:\s*(.+)$", fm, re.M)
            if mm:
                model = mm.group(1).strip()
            dm = re.search(r"^description:\s*(.+)$", fm, re.M)
            if dm:
                desc = dm.group(1).strip()[:70]
    except OSError:
        pass
    return name, model, desc


def show_agents(cfg):
    header("DAFTAR AGENT")
    agents = cfg.get("agent", {})
    top_model = cfg.get("model", "(default bawaan)")

    print(f"  {colored('Global', 'bold')}: model={colored(top_model, 'y')}  "
          f"small_model={colored(cfg.get('small_model', '(ikut model)'), 'y')}")
    print()

    if agents:
        width = max(len(k) for k in agents) + 2
        print(colored("  Override di opencode.json:", "bold"))
        for name, ov in agents.items():
            model = (ov or {}).get("model", col := "(tidak diset)")
            mark = "" if isinstance(ov, dict) and ov.get("model") else colored("  ← belum ada model!", "r")
            print(f"   • {name.ljust(width)}{colored(str(model), 'y')}{mark}")
    else:
        warn("Belum ada override agent sama sekali.")
        width = 18

    md_dir = AGENTS_MD_DIR()
    if os.path.isdir(md_dir):
        mds = sorted(f for f in os.listdir(md_dir) if f.endswith(".md"))
        if mds:
            print()
            print(colored("  Agent custom (.md):", "bold"))
            for f in mds:
                name, model, desc = read_md_agent(os.path.join(md_dir, f))
                extra = f"  {colored('# ' + desc, 'dim')}" if desc else ""
                # width already set above
                print(f"   • {name.ljust(width)}{colored(str(model or '(ikut global)'), 'y')}{extra}")

    untouched = [a for a in KNOWN_AGENTS if a not in agents]
    if untouched:
        print()
        print(colored(f"  Belum di-override (ikut global): {', '.join(untouched)}", "dim"))

    # ----- Pin OMO (lapisan 2) -----
    omo = load_omo()
    if omo is None:
        print()
        print(colored("  Pin OMO (~/.omo/omo.jsonc):", "bold") + colored("  ⚠ file rusak — perbaiki manual", "r"))
    elif not omo:
        print()
        print(colored("  Pin OMO (~/.omo/omo.jsonc):", "bold") + colored("  (tidak ada file — akan dibuat saat ganti model)", "dim"))
    else:
        oc = omo.get("[opencode]", {})
        if isinstance(oc, dict) and (oc.get("agents") or oc.get("categories")):
            print()
            print(colored("  Pin OMO (~/.omo/omo.jsonc):", "bold"))
            # agents pin
            omo_agents = oc.get("agents", {}) if isinstance(oc.get("agents"), dict) else {}
            if omo_agents:
                print(colored("    agents:", "dim"))
                for k, v in sorted(omo_agents.items()):
                    m = v.get("model", "?") if isinstance(v, dict) else str(v)
                    # cek konflik vs opencode.json
                    op_m = (agents.get(k) or {}).get("model") if isinstance(agents.get(k), dict) else None
                    flag = ""
                    if op_m and op_m != m:
                        flag = colored(f"  ⚠ beda vs opencode.json ({op_m})", "r")
                    print(f"     • {k.ljust(width)}{colored(str(m), 'y')}{flag}")
            # categories pin
            omo_cats = oc.get("categories", {}) if isinstance(oc.get("categories"), dict) else {}
            if omo_cats:
                print(colored("    categories:", "dim"))
                for k, v in sorted(omo_cats.items()):
                    m = v.get("model", "?") if isinstance(v, dict) else str(v)
                    print(f"     • {k.ljust(width)}{colored(str(m), 'y')}")
        else:
            print()
            print(colored("  Pin OMO (~/.omo/omo.jsonc):", "bold") + colored("  (tidak ada pin agents/categories)", "dim"))
    print()


# ---------------------------------------------------------------- aksi

def action_change_one(cfg):
    agents = cfg.setdefault("agent", {})
    names = sorted(set(list(agents.keys())))
    options = names + [a for a in KNOWN_AGENTS if a not in names]
    # also add categories that are not yet in options so user can pick e.g. artistry/quick
    for cat in KNOWN_CATEGORIES:
        if cat not in options:
            options.append(cat)
    options = sorted(set(options))
    cur = {n: (agents.get(n) or {}).get("model", "(belum di-override)") for n in options}

    i = pick_numbered(options, "GANTI MODEL SATU AGENT",
                      fmt=lambda n: f"{n.ljust(20)}{colored(cur[n], 'y')}")
    if i is None:
        return
    name = options[i]
    model = pick_model(cfg)
    if not model:
        warn("Batal.")
        return
    old = cur[name]
    set_model_everywhere(name, model, cfg)
    # layer 3: .md frontmatter if exists
    md_changed = edit_md_frontmatter_model(name, model)
    save_config(cfg)
    ok(f"{name}: {old} → {colored(model, 'g', 'bold')}" + (colored(" (+ .md)", "dim") if md_changed else ""))
    warn("Restart sesi opencode biar efek.")


def action_preset(cfg):
    presets = load_presets()
    items = sorted(presets.items())
    i = pick_numbered(items, "TERAPKAN PRESET KE SEMUA AGENT",
                      fmt=lambda kv: f"{kv[0].ljust(18)}{colored(kv[1], 'y')}")
    if i is None:
        return
    pname, pmodel = items[i]
    agents = cfg.get("agent", {})
    untouched = [a for a in KNOWN_AGENTS if a not in agents]

    print(f"\n  Preset '{pname}' akan set semua agent ke {colored(pmodel, 'g', 'bold')}")
    scope = 1
    if untouched:
        choice = ask(
            f"  Ada {len(untouched)} agent OMO belum di-override. "
            "[1] Hanya yang di config saja  [2] Sekalian tambahkan semuanya", "1")
        scope = 2 if choice == "2" else 1
    if not confirm(f"  Yakin terapkan '{pname}'?"):
        warn("Batal.")
        return

    targets = list(agents.keys())
    if scope == 2:
        targets += untouched
    # also include categories for full sync
    cat_targets = list(KNOWN_CATEGORIES)
    for name in targets:
        set_model_everywhere(name, pmodel, cfg)
        edit_md_frontmatter_model(name, pmodel)
    # also repin categories that are not in targets (e.g. quick/artistry jika belum di targets)
    omo = load_omo()
    if omo is not None and isinstance(omo.get("[opencode]"), dict):
        oc = omo["[opencode]"]
        for cat in cat_targets:
            sec = oc.setdefault("categories", {})
            ent = sec.get(cat)
            if isinstance(ent, dict):
                ent["model"] = pmodel
            else:
                sec[cat] = {"model": pmodel}
        # also ensure agents section covers all targets already via set_model_everywhere, but categories extra handled
        save_omo(omo)
    # md for categories typically no file, so ignore
    cfg["agent"] = cfg.get("agent", {})
    save_config(cfg)
    ok(f"{len(targets)} agent + {len(cat_targets)} categories sekarang pakai '{pmodel}'")
    warn("Restart sesi opencode biar efek.")


def action_manage_presets():
    presets = load_presets()
    while True:
        items = sorted(presets.items())
        i = pick_numbered(items, "KELOLA PRESET",
                          fmt=lambda kv: f"{kv[0].ljust(18)}{colored(kv[1], 'y')}")
        if i is None:
            return
        name, model = items[i]
        print(f"\n  1. Edit preset ini   2. Hapus   0. Kembali")
        a = ask("Aksi")
        if a == "1":
            new_name = ask("Nama baru", name)
            new_model = pick_model(None)
            if new_model and new_name:
                del presets[name]
                presets[new_name] = new_model
                save_presets(presets)
                ok("Preset diupdate.")
        elif a == "2":
            if confirm(f"  Hapus preset '{name}'?"):
                del presets[name]
                save_presets(presets)
                ok("Terhapus.")
        if not presets:
            presets = dict(DEFAULT_PRESETS)
            save_presets(presets)
            warn("Preset kosong, dikembalikan ke bawaan.")

        if not confirm("  Kelola preset lagi?", default_yes=False):
            # opsi tambah preset baru sebelum keluar
            if confirm("  Tambah preset baru?", default_yes=False):
                nm = ask("Nama preset")
                mdl = pick_model(None)
                if nm and mdl:
                    presets = load_presets()
                    presets[nm] = mdl
                    save_presets(presets)
                    ok(f"Preset '{nm}' ditambahkan.")
            return


def action_add_agent(cfg):
    header("TAMBAH OVERRIDE AGENT BARU")
    existing = cfg.get("agent", {})
    name = ask("Nama agent (mis. oracle, coder-custom)")
    if not name:
        return warn("Batal.")
    if name in existing:
        warn(f"'{name}' sudah ada — lewat menu 'Ganti model satu agent' aja.")
        return
    model = pick_model(cfg)
    if not model:
        return warn("Batal.")
    set_model_everywhere(name, model, cfg)
    edit_md_frontmatter_model(name, model)
    save_config(cfg)
    ok(f"Override '{name}' → {model} ditambahkan (sinkron ke OMO).")


def action_remove_agent(cfg):
    agents = cfg.get("agent", {})
    if not agents:
        return warn("Belum ada override yang bisa dihapus.")
    i = pick_numbered(sorted(agents), "HAPUS OVERRIDE AGENT",
                      fmt=lambda n: f"{n.ljust(20)}{(agents[n] or {}).get('model', '')}")
    if i is None:
        return
    name = sorted(agents)[i]
    if confirm(f"  Hapus override '{name}'? (agent balik ikut setting global)"):
        del cfg["agent"][name]
        save_config(cfg)
        ok(f"'{name}' dihapus dari override.")
        warn("Catatan: pin OMO untuk agent ini TIDAK otomatis dihapus — pakai menu 10 repin jika perlu.")


def action_global_model(cfg):
    header("MODEL GLOBAL (top-level 'model' & 'small_model')")
    print(f"  model       = {colored(str(cfg.get('model', '-')), 'y')}")
    print(f"  small_model = {colored(str(cfg.get('small_model', '-')), 'y')}\n")
    model = pick_model(cfg)
    if not model:
        return warn("Batal.")
    apply_small = confirm("  Set small_model juga sama?", default_yes=False)
    cfg["model"] = model
    if apply_small:
        cfg["small_model"] = model
    save_config(cfg)
    ok(f"model → {model}" + (f", small_model → {model}" if apply_small else ""))
    if confirm("  Repin SEMUA pin OMO (agents+categories) ke model ini juga?", default_yes=False):
        omo = load_omo()
        if omo is None:
            warn("omo.jsonc rusak — skip repin.")
        elif not omo:
            warn("Tidak ada omo.jsonc — skip.")
        else:
            oc = omo.get("[opencode]", {})
            if isinstance(oc, dict):
                for section in ("agents", "categories"):
                    sec = oc.get(section, {})
                    if isinstance(sec, dict):
                        for k, v in sec.items():
                            if isinstance(v, dict):
                                v["model"] = model
                save_omo(omo)
                ok("Semua pin OMO ikut di-repin.")


def action_backup_restore(cfg):
    opts = ["Buat backup sekarang", "Restore dari backup"]
    i = pick_numbered(opts, "BACKUP & RESTORE", fmt=lambda o: o)
    if i is None:
        return
    if i == 0:
        dst = make_backup(reason="manual")
        ok(f"Backup dibuat: {dst}" if dst else warn("Tidak ada config untuk dibackup."))
        return

    bdir = BACKUP_DIR()
    if not os.path.isdir(bdir):
        return warn("Folder backup kosong.")
    backups = sorted(
        (f for f in os.listdir(bdir) if f.startswith("opencode.json.")), reverse=True
    )
    if not backups:
        return warn("Belum ada backup.")
    i = pick_numbered(backups, "PILIH BACKUP UNTUK RESTORE", fmt=lambda f: f)
    if i is None:
        return
    src = os.path.join(bdir, backups[i])
    try:
        with open(src, encoding="utf-8") as f:
            json.load(f)  # pastikan backup valid
    except Exception as e:
        return err(f"Backup rusak, skip: {e}")
    if confirm(f"  Restore '{backups[i]}'? Config sekarang dibackup dulu otomatis."):
        make_backup(reason="pre-restore")
        shutil.copy2(src, CONFIG_PATH())
        ok("Restore selesai.")


def action_refresh_catalog():
    cache = MODELS_CACHE()
    try:
        if os.path.exists(cache):
            os.remove(cache)
    except OSError:
        pass
    print(colored("  ...menarik katalog baru...", "dim"))
    models = fetch_models_live()
    ok(f"Katalog segar: {len(models)} model ter-cache.")


def action_repin_omo(cfg):
    header("SAMAKAN SEMUA PIN OMO")
    omo = load_omo()
    if omo is None:
        err("omo.jsonc rusak — perbaiki manual dulu.")
        return
    if not omo:
        warn("Belum ada omo.jsonc — akan dibuat dengan pin minimal.")
        omo = {"[opencode]": {"agents": {}, "categories": {}}}
    oc = omo.get("[opencode]", {})
    if not isinstance(oc, dict):
        oc = {}
        omo["[opencode]"] = oc
    total = sum(len(oc.get(s, {})) if isinstance(oc.get(s), dict) else 0 for s in ("agents", "categories"))
    print(f"  Pin saat ini: {total} entri (agents+categories)")
    model = pick_model(cfg)
    if not model:
        return warn("Batal.")
    if not confirm(f"  Repin SEMUA {total} pin OMO ke {model}?", default_yes=True):
        return warn("Batal.")
    for section in ("agents", "categories"):
        sec = oc.setdefault(section, {})
        if isinstance(sec, dict):
            for k, v in sec.items():
                if isinstance(v, dict):
                    v["model"] = model
    save_omo(omo)
    ok(f"Semua {total} pin OMO → {model}")
    warn("Restart sesi opencode biar efek.")


# ---------------------------------------------------------------- main

MENU = [
    ("Lihat semua agent & model aktif", lambda c: show_agents(c)),
    ("Ganti model SATU agent",          action_change_one),
    ("Terapkan PRESET ke semua agent",  action_preset),
    ("Kelola preset (edit/hapus/tambah)", lambda c: action_manage_presets()),
    ("Tambah override agent baru",      action_add_agent),
    ("Hapus override agent",            action_remove_agent),
    ("Ganti model GLOBAL (model/small_model)", action_global_model),
    ("Backup & restore config",         action_backup_restore),
    ("Refresh katalog model",           lambda c: action_refresh_catalog()),
    ("Samakan SEMUA pin OMO ke satu model", action_repin_omo),
]


def banner():
    print(colored("""
  ┌─────────────────────────────────────────┐
  │   ⚙  chagent · manajer agent OMO       │
  └─────────────────────────────────────────┘""", "c", "bold"))


def main():
    cfg = load_config(strict=True)
    while True:
        show_agents(cfg)
        banner()
        for i, (label, _) in enumerate(MENU, 1):
            print(f"  {colored(str(i), 'y')}. {label}")
        print(f"  {colored('0', 'y')}. Keluar")
        raw = ask("Pilih menu")
        if raw is None:
            break
        if raw == "0":
            break
        if raw.isdigit() and 1 <= int(raw) <= len(MENU):
            _, fn = MENU[int(raw) - 1]
            fn(cfg)
        else:
            err("Menu ngawur, pilih nomor yang ada.")
        cfg = load_config() or cfg  # reload; kalau rusak jangan overwrite memori baik-baik saja
    print(colored("\n  Dadah 👋\n", "c"))


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print(colored("\n  Dibatalkan.\n", "y"))
