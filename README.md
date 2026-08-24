<div align="center">

# ⚙️ chagent

**Stop hand-editing `opencode.json` like a caveman.**

A zero-dependency, interactive TUI to manage your [OpenCode](https://opencode.ai) /
Oh-My-OpenCode agents — switch models, apply presets, never fear breaking your config again.

[![python](https://img.shields.io/badge/python-3.8%2B-blue?logo=python&logoColor=white)](https://www.python.org)
[![dependencies](https://img.shields.io/badge/dependencies-0-brightgreen)](#why)
[![license](https://img.shields.io/badge/license-MIT-black)](LICENSE)
[![size](https://img.shields.io/badge/size-~20KB-orange)](chagent.py)
[![vibes](https://img.shields.io/badge/vibes-immaculate-purple)](README.md)

</div>

---

You use [Oh-My-OpenCode](https://github.com/) (OMO). It ships a dozen agents — `oracle`,
`librarian`, `explore`, `sisyphus`, `metis`… and every time you want to point one at a
different model, you have to:

1. Open `~/.config/opencode/opencode.json`
2. Find the `"agent"` block among your MCP servers and plugins
3. Hand-type JSON. Pray you didn't leave a trailing comma
4. Break it anyway. Cry.

**chagent fixes that.** One command. Numbered menus. Auto-backup before every write.
It literally refuses to save a broken config.

```
$ chagent

  ┌─────────────────────────────────────────┐
  │   ⚙  chagent · manajer agent OMO       │
  └─────────────────────────────────────────┘
  1. Lihat semua agent & model aktif
  2. Ganti model SATU agent
  3. Terapkan PRESET ke semua agent
  4. Kelola preset (edit/hapus/tambah)
  5. Tambah override agent baru
  6. Hapus override agent
  7. Ganti model GLOBAL (model/small_model)
  8. Backup & restore config
  9. Refresh katalog model
  0. Keluar
```

## ✨ Features

| | |
|---|---|
| 🎯 **Per-agent model swap** | Pick an agent, pick a model, done. Live catalog pulled straight from `opencode models` |
| 🆓 **Free-model radar** | Automatically filters the ~30 free models from hundreds of options |
| ⚡ **Presets** | Save model bundles (`omniroute-free`, `opencode-free`, your own…) and nuke *every* agent in one keystroke |
| 💾 **Auto-backup** | Timestamped snapshot before **every** write. Keep 30. Restore anytime |
| 🛡️ **Corrupt-proof** | Invalid JSON in? Tool refuses to touch it. Broken write attempt? Validated before it replaces the real file |
| 📦 **Zero dependencies** | Pure Python stdlib. If you have `python3`, you have chagent |

## 🚀 Quick start

```bash
git clone https://github.com/keinan21/chagent.git
mkdir -p ~/.local/bin
ln -sf "$(pwd)/chagent/chagent.py" ~/.local/bin/chagent   # adjust if you cloned elsewhere
chagent
```

Or the no-clone one-liner:

```bash
curl -fsSL https://raw.githubusercontent.com/keinan21/chagent/main/chagent.py \
  -o ~/.config/opencode/chagent.py \
&& mkdir -p ~/.local/bin \
&& ln -sf ~/.config/opencode/chagent.py ~/.local/bin/chagent \
&& chagent
```

> Requires: `python3` and `opencode` on your `$PATH` (for the live model catalog).
> No `opencode`? Still works — falls back to a built-in seed list.

## 🧠 How it works

OpenCode merges agent config from three layers:

```
plugin defaults  →  opencode.json "agent" overrides  →  custom agents/*.md
```

chagent manages the middle layer — the override block — which is what 95% of people
actually want to touch. It also reads your custom `.md` agents (frontmatter parsing)
so you see the full picture in one screen.

Changing `oracle`'s model is just:

```
menu 2 → oracle → quick pick → ✅ saved (+ backup created automatically)
```

## 🛟 Safety net

Every write follows the same ritual:

1. Snapshot current config → `~/.config/opencode/backups/opencode.json.<timestamp>.bak`
2. Write to a temp file
3. Re-parse the temp file to prove it's valid JSON
4. Only then atomically replace the real config

Config already corrupted by past sins? chagent detects it, tells you exactly where,
and refuses to make things worse.

## ❓ FAQ

**Is "viral" realistic for a config manager?**
No. But here we are. Star it and prove the algorithm wrong. ⭐

**Does it work with plain OpenCode (no OMO plugin)?**
Yes — same `"agent"` override block, same rules.

**Windows?**
It's Python, so mostly yes, but the symlink install is Unix-flavored. WSL recommended.

**Why is the UI half Indonesian?**
Because the author is. `_/\_` Merdeka!

**Can I edit prompts/descriptions too?**
Not yet — v1 focuses on models. Custom `.md` agent wizard is on the roadmap.

## 🗺️ Roadmap

- [ ] Wizard for creating `.md` agents (frontmatter without tears)
- [ ] Edit agent descriptions & system prompts from the menu
- [ ] Per-project config support (`.opencode/`)
- [ ] `--model` non-interactive flags for script junkies

## 🤝 Contributing

PRs welcome. Keep it stdlib-only — the whole point is zero dependencies.
If your PR adds a build step, we're legally required to laugh at it.

## 📜 License

[MIT](LICENSE) — do whatever, just don't blame us when your agents unionize.

---

<div align="center">
<sub>Built with 😮‍💨 and far too many broken <code>opencode.json</code> files.</sub>
</div>
