#!/usr/bin/env python3
"""
chagent — Manajer agent OhMyOpenCode / OpenCode
Ganti model agent, preset cepat, backup otomatis. Menu interaktif, zero dependency.

Config yang dikelola : ~/.config/opencode/opencode.json  (bagian "agent" + "model")
Backup otomatis      : ~/.config/opencode/backups/
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

CONFIG_PATH = lambda: os.path.join(config_dir(), "opencode.json")          # noqa: E731
BACKUP_DIR = lambda: os.path.join(config_dir(), "backups")                 # noqa: E731
PRESET_PATH = lambda: os.path.join(config_dir(), "omo-agent-presets.json")  # noqa: E731
MODELS_CACHE = lambda: os.path.join(config_dir(), ".omo-models-cache.txt")  # noqa: E731
AGENTS_MD_DIR = lambda: os.path.join(config_dir(), "agents")               # noqa: E731

MAX_BACKUPS = 30
CACHE_TTL = 24 * 3600  # refresh katalog model tiap 24 jam

# Roster agent bawaan OMO — dipakai buat nawarin override yang belum ada.
KNOWN_AGENTS = [
    "build", "plan", "general", "explore", "deep",
    "metis", "momus", "multimodal-looker", "oracle", "librarian",
    "atlas", "hephaestus", "prometheus", "Sisyphus-Junior", "sisyphus",
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

    md_dir = AGENTS_MD_DIR()
    if os.path.isdir(md_dir):
        mds = sorted(f for f in os.listdir(md_dir) if f.endswith(".md"))
        if mds:
            print()
            print(colored("  Agent custom (.md):", "bold"))
            for f in mds:
                name, model, desc = read_md_agent(os.path.join(md_dir, f))
                extra = f"  {colored('# ' + desc, 'dim')}" if desc else ""
                print(f"   • {name.ljust(width)}{colored(str(model or '(ikut global)'), 'y')}{extra}")

    untouched = [a for a in KNOWN_AGENTS if a not in agents]
    if untouched:
        print()
        print(colored(f"  Belum di-override (ikut global): {', '.join(untouched)}", "dim"))
    print()


# ---------------------------------------------------------------- aksi

def action_change_one(cfg):
    agents = cfg.setdefault("agent", {})
    names = sorted(set(list(agents.keys())))
    options = names + [a for a in KNOWN_AGENTS if a not in names]
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
    entry = agents.get(name)
    if isinstance(entry, dict):
        entry["model"] = model
    else:
        agents[name] = {"model": model}
    save_config(cfg)
    ok(f"{name}: {old} → {colored(model, 'g', 'bold')}")
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
            "[1] Hapus yang di config saja  [2] Sekalian tambahkan semuanya", "1")
        scope = 2 if choice == "2" else 1
    if not confirm(f"  Yakin terapkan '{pname}'?"):
        warn("Batal.")
        return

    targets = list(agents.keys())
    if scope == 2:
        targets += untouched
    for name in targets:
        entry = agents.get(name)
        if isinstance(entry, dict):
            entry["model"] = pmodel
        else:
            agents[name] = {"model": pmodel}
    cfg["agent"] = agents
    save_config(cfg)
    ok(f"{len(targets)} agent sekarang pakai '{pmodel}'")
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
    cfg.setdefault("agent", {})[name] = {"model": model}
    save_config(cfg)
    ok(f"Override '{name}' → {model} ditambahkan.")


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
