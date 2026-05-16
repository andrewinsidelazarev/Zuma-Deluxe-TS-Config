#!/usr/bin/env python3
"""Synchronize workshop (c:/z80/zuma) → Zuma-Deluxe-TS-Config git repo.

Цель: чтобы при «обнови гитхаб» не забывать INCBIN/spgbld зависимости и docs.

Workshop:  c:/z80/zuma/
Repo:      C:/Users/Администратор/Desktop/Zuma Deluxe/
GitHub:    https://github.com/andrewinsidelazarev/Zuma-Deluxe-TS-Config

Логика:
  1. EXPLICIT_MAPPINGS — список (workshop_rel, repo_rel) для .asm/.ini/.py/.md
     (всё, что не auto-discoverable).
  2. Auto-discover .bin ассеты для src/ASM/:
     - INCBIN refs в zuma_new_spg.asm + level_select.asm
     - Block refs в spgbld.ini
     - Минус build outputs (main0/1.bin, frog_p?.bin, page_?.bin).
  3. Для каждого item: если в workshop файл новее или content отличается
     от repo — копируем. Если в repo новее — WARNING (требует manual review).
  4. По умолчанию dry-run; --apply для реального copy + git add; --commit "msg"
     для коммита; --push для push.

Usage:
    py -3 sync_to_github.py                       # dry-run, перечисляет diff
    py -3 sync_to_github.py --apply               # копирует + git add
    py -3 sync_to_github.py --apply --commit MSG  # + commit
    py -3 sync_to_github.py --apply --commit MSG --push  # + push origin main

Maintaining:
  - При добавлении новых .py/.md файлов — добавить в EXPLICIT_MAPPINGS ниже.
  - Новые .bin ассеты подтянутся автоматически если они INCBIN'нуты в .asm
    или присутствуют в Block= строках spgbld.ini.
  - Если build outputs изменились — обнови BUILD_OUTPUTS set.
"""
from __future__ import annotations

import argparse
import hashlib
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Iterable

WORKSHOP = Path(r"C:\z80\zuma")
REPO = Path(r"C:\Users\Администратор\Desktop\Zuma Deluxe")

# Файлы, которые мы НЕ синхронизируем (sjasmplus/spgbld outputs).
BUILD_OUTPUTS = {
    "main0.bin", "main1.bin",
    "frog_p0.bin", "frog_p1.bin", "frog_p2.bin", "frog_p3.bin",
    "page_a.bin", "page_b.bin", "page_d.bin",
}

# Явный список (workshop_rel, repo_rel). Все пути относительные.
EXPLICIT_MAPPINGS: list[tuple[str, str]] = [
    # === ASM sources ===
    ("zuma_new_spg.asm", "src/ASM/zuma_new_spg.asm"),
    ("level_select.asm", "src/ASM/level_select.asm"),
    ("spgbld.ini",       "src/ASM/spgbld.ini"),

    # === Python: tests ===
    ("test_session_fixes_2026-05-16.py", "src/Python/test_session_fixes_2026-05-16.py"),
    ("test_level2_gameover_trigger.py",  "src/Python/test_level2_gameover_trigger.py"),
    ("test_chain_advance.py",            "src/Python/test_chain_advance.py"),
    ("test_repro_false_match3.py",       "src/Python/test_repro_false_match3.py"),
    ("test_gameover.py",                 "src/Python/test_gameover.py"),
    ("test_game_frames.py",              "src/Python/test_game_frames.py"),
    ("test_gameframe_diff.py",           "src/Python/test_gameframe_diff.py"),

    # === Python: harness + simulators ===
    ("zuma_ts_emulator.py",      "src/Python/zuma_ts_emulator.py"),
    ("vdc_visual_emulator.py",   "src/Python/vdc_visual_emulator.py"),
    ("vdc_test_runner.py",       "src/Python/vdc_test_runner.py"),
    ("full_vdc_simulation.py",   "src/Python/full_vdc_simulation.py"),
    ("chain_sim.py",             "src/Python/chain_sim.py"),

    # === Python: importers / asset builders ===
    ("import_zumahd_level.py",        "src/Python/import_zumahd_level.py"),
    ("import_real_level1.py",         "src/Python/import_real_level1.py"),
    ("make_level1_text_assets.py",    "src/Python/make_level1_text_assets.py"),
    ("make_level2_text_assets.py",    "src/Python/make_level2_text_assets.py"),
    ("make_level02_canvas_from_scaled.py", "src/Python/make_level02_canvas_from_scaled.py"),

    # === Docs (MD) ===
    ("_docs/uchebnik_full.md", "docs/Программирование для tsconfig.md"),

    # === Sync script itself (в репо для прозрачности) ===
    ("sync_to_github.py", "tools/sync_to_github.py"),

    # === Level graphics (canonical sources) ===
    ("level_01.bin", "graphics/levels-ts-config/01/level_01.bin"),
    ("level_02.bin", "graphics/levels-ts-config/02/level_02.bin"),
]


def md5_of(path: Path) -> str:
    h = hashlib.md5()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def discover_asm_assets() -> list[tuple[str, str]]:
    """Просканировать .asm и spgbld.ini для INCBIN/Block .bin зависимостей."""
    deps: set[str] = set()

    incbin_rx = re.compile(r'INCBIN\s+"([^"]+)"')
    for asm_name in ("zuma_new_spg.asm", "level_select.asm"):
        text = (WORKSHOP / asm_name).read_text(encoding="utf-8", errors="replace")
        for m in incbin_rx.finditer(text):
            deps.add(m.group(1).replace("/", os.sep).replace("\\", os.sep))

    block_rx = re.compile(r"^\s*Block\s*=\s*[^,]+,\s*[^,]+,\s*(.+?)\s*$", re.I | re.M)
    spgbld_text = (WORKSHOP / "spgbld.ini").read_text(encoding="utf-8", errors="replace")
    for m in block_rx.finditer(spgbld_text):
        deps.add(m.group(1).strip().replace("/", os.sep).replace("\\", os.sep))

    result: list[tuple[str, str]] = []
    for dep in sorted(deps):
        base = Path(dep).name
        if base in BUILD_OUTPUTS:
            continue
        # Workshop path может быть subdir (например levels/dispnames.bin).
        result.append((dep, f"src/ASM/{dep.replace(os.sep, '/')}"))
    return result


def sync_one(ws_rel: str, repo_rel: str, apply: bool) -> str | None:
    """Return action description if change needed, None если up-to-date."""
    ws = WORKSHOP / ws_rel
    rp = REPO / repo_rel
    if not ws.exists():
        return f"MISSING_WORKSHOP: {ws_rel}"

    if not rp.exists():
        if apply:
            rp.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(ws, rp)
        return f"NEW {repo_rel} (size {ws.stat().st_size})"

    if md5_of(ws) == md5_of(rp):
        return None

    ws_mt = ws.stat().st_mtime
    rp_mt = rp.stat().st_mtime

    if ws_mt < rp_mt:
        return f"WARNING repo NEWER than workshop: {repo_rel} (ws={ws_mt:.0f}, repo={rp_mt:.0f}) — review manually"

    if apply:
        shutil.copy2(ws, rp)
    return f"UPDATE {repo_rel}"


def run_git(args: list[str], check: bool = True) -> subprocess.CompletedProcess:
    return subprocess.run(["git"] + args, cwd=REPO, check=check, text=True,
                          capture_output=True)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("--apply", action="store_true", help="actually copy files + git add")
    parser.add_argument("--commit", metavar="MSG", help="commit with message (requires --apply)")
    parser.add_argument("--push", action="store_true", help="push origin main (requires --commit)")
    args = parser.parse_args()

    if args.commit and not args.apply:
        parser.error("--commit requires --apply")
    if args.push and not args.commit:
        parser.error("--push requires --commit")

    items = list(EXPLICIT_MAPPINGS) + discover_asm_assets()

    actions: list[str] = []
    warnings: list[str] = []
    missing: list[str] = []
    changed_paths: list[str] = []     # repo-relative paths, для git add
    for ws_rel, repo_rel in items:
        action = sync_one(ws_rel, repo_rel, args.apply)
        if action is None:
            continue
        if action.startswith("WARNING"):
            warnings.append(action)
        elif action.startswith("MISSING_WORKSHOP"):
            missing.append(action)
        else:
            actions.append(action)
            changed_paths.append(repo_rel)

    mode = "[apply]" if args.apply else "[dry-run]"
    print(f"{mode} {len(items)} mappings scanned")
    print(f"  changes:  {len(actions)}")
    print(f"  warnings: {len(warnings)}")
    print(f"  missing:  {len(missing)}")
    print()
    for a in actions:
        print(f"  {a}")
    for w in warnings:
        print(f"  {w}")
    for m in missing:
        print(f"  {m}")

    if not args.apply:
        if actions:
            print()
            print(f"Run with --apply to copy and stage.")
        return 0

    if not actions:
        print("\nNothing to commit.")
        return 0

    print("\n--- git add (only synced paths) ---")
    # Add по конкретным путям, чтобы не загребать untracked мусор.
    run_git(["add", "--"] + changed_paths)
    status = run_git(["status", "--short"])
    print(status.stdout)

    if args.commit:
        print("--- git commit ---")
        result = run_git(["commit", "-m", args.commit], check=False)
        print(result.stdout or result.stderr)

        if args.push:
            print("--- git push ---")
            result = run_git(["push", "origin", "main"], check=False)
            print(result.stdout or result.stderr)

    return 0


if __name__ == "__main__":
    sys.exit(main())
