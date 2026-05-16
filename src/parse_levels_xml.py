#!/usr/bin/env python3
"""Парсер content/levels/levels.xml из Zuma-Deluxe-HD.

Источник: Desktop/Zuma Deluxe/graphics/levels-HD/levels.xml
  (скачан из github.com/GalaxyShad/Zuma-Deluxe-HD)

Выход: Desktop/Zuma Deluxe/src/levels_meta.json — все таблицы в одном JSON.

Структура levels.xml:
  <Graphics id="..." curve="..." image="..." dispname="..." gx="..." gy="...">
    <Cutout image="..." x="..." y="..." pri="..." />
    <TreasurePoint x="..." y="..." dist1="..." />
    <BackgroundAlpha image="..." x="..." y="..." />
  </Graphics>
  <Settings id="..." speed="..." start="..." score="..." ... />
  <LevelProgression id="standard|dual" settings="csv" difficulty="csv" />
  <Level graphics="<gid>" progression="standard|dual" />
  <StageProgression stage1="csv" diffi1="csv" ... stage13 diffi13 />

XML невалидный (нет корня) — обернём в <root>.
"""
import json
import re
from pathlib import Path
import xml.etree.ElementTree as ET

XML_PATH  = Path(r"C:/Users/Администратор/Desktop/Zuma Deluxe/graphics/levels-HD/levels.xml")
OUT_PATH  = Path(r"C:/Users/Администратор/Desktop/Zuma Deluxe/src/levels_meta.json")


def csv_list(s):
    """'a, b, c' → ['a', 'b', 'c']"""
    if not s:
        return []
    return [t.strip() for t in s.split(',') if t.strip()]


def f_or_i(v):
    """'0.5' → 0.5; '35' → 35; None → None."""
    if v is None:
        return None
    try:
        if '.' in v:
            return float(v)
        return int(v)
    except ValueError:
        return v


def parse():
    # XML валидный: <?xml?> + <Levels>...</Levels>.
    root = ET.parse(XML_PATH).getroot()

    graphics = {}
    settings = {}
    progressions = {}
    levels = []
    stage_progression = None

    for el in root:
        tag = el.tag

        if tag == 'Graphics':
            gid = el.attrib['id']
            g = {
                'id':            gid,
                'curve':         el.attrib.get('curve'),
                'curve2':        el.attrib.get('curve2'),
                'image':         el.attrib.get('image'),
                'image_top':     el.attrib.get('image-top'),
                'dispname':      el.attrib.get('dispname'),
                'gx':            f_or_i(el.attrib.get('gx')),
                'gy':            f_or_i(el.attrib.get('gy')),
                'skullrot':      f_or_i(el.attrib.get('skullrot')),
                'space':         el.attrib.get('space') == 'true',
                'drawcurve':     el.attrib.get('drawcurve') == 'true',
                'cutouts':       [],
                'treasure':      [],
                'bg_alphas':     [],
            }
            for child in el:
                if child.tag == 'Cutout':
                    g['cutouts'].append({
                        'image': child.attrib.get('image'),
                        'x':     f_or_i(child.attrib.get('x')),
                        'y':     f_or_i(child.attrib.get('y')),
                        'pri':   f_or_i(child.attrib.get('pri')),
                    })
                elif child.tag == 'TreasurePoint':
                    g['treasure'].append({
                        'x':     f_or_i(child.attrib.get('x')),
                        'y':     f_or_i(child.attrib.get('y')),
                        'dist1': f_or_i(child.attrib.get('dist1')),
                        'dist2': f_or_i(child.attrib.get('dist2')),
                    })
                elif child.tag == 'BackgroundAlpha':
                    g['bg_alphas'].append({
                        'image': child.attrib.get('image'),
                        'x':     f_or_i(child.attrib.get('x')),
                        'y':     f_or_i(child.attrib.get('y')),
                    })
            graphics[gid] = g

        elif tag == 'Settings':
            sid = el.attrib['id']
            settings[sid] = {k: f_or_i(v) for k, v in el.attrib.items() if k != 'id'}
            settings[sid]['id'] = sid

        elif tag == 'LevelProgression':
            pid = el.attrib['id']
            progressions[pid] = {
                'id':         pid,
                'settings':   csv_list(el.attrib.get('settings')),
                'difficulty': csv_list(el.attrib.get('difficulty')),
            }

        elif tag == 'Level':
            levels.append({
                'graphics':    el.attrib.get('graphics'),
                'progression': el.attrib.get('progression'),
            })

        elif tag == 'StageProgression':
            sp = {}
            for i in range(1, 14):
                stage_key = f'stage{i}'
                diffi_key = f'diffi{i}'
                if stage_key in el.attrib:
                    sp[f'stage{i}'] = {
                        'graphics':   csv_list(el.attrib[stage_key]),
                        'difficulty': csv_list(el.attrib[diffi_key]),
                    }
            stage_progression = sp

    return {
        'graphics':          graphics,
        'settings':          settings,
        'progressions':      progressions,
        'levels':            levels,
        'stage_progression': stage_progression,
    }


def summarize(meta):
    """Печать краткой статистики для проверки."""
    g  = meta['graphics']
    s  = meta['settings']
    p  = meta['progressions']
    ls = meta['levels']
    sp = meta['stage_progression']

    print(f'=== levels.xml summary ===')
    print(f'Graphics:           {len(g):3d}   ', list(g.keys()))
    print(f'Settings:           {len(s):3d}   '
          f'standard={sum(1 for k in s if k.startswith("level"))}, '
          f'stage-diffi={sum(1 for k in s if k.startswith("lvl"))}, '
          f'dual={sum(1 for k in s if k.startswith("dual"))}')
    print(f'LevelProgressions:  {len(p):3d}   {list(p.keys())}')
    print(f'Levels:             {len(ls):3d}')
    print(f'StageProgression:   {len(sp):3d} stages')
    print()
    print('=== Stages overview ===')
    for sk, sv in sp.items():
        gxs = sv['graphics']
        dfs = sv['difficulty']
        print(f'  {sk:>7s}: {len(gxs)} levels')
        for gid, did in zip(gxs, dfs):
            dispname = g.get(gid, {}).get('dispname') or '?'
            speed    = s.get(did, {}).get('speed')
            start    = s.get(did, {}).get('start')
            colors   = s.get(did, {}).get('colors', 6)
            partime  = s.get(did, {}).get('partime')
            print(f'    {did:>7s}  {gid:<15s}  "{dispname}"  '
                  f'speed={speed} start={start} colors={colors} partime={partime}')


if __name__ == '__main__':
    meta = parse()
    OUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    OUT_PATH.write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding='utf-8')
    print(f'Wrote {OUT_PATH} ({OUT_PATH.stat().st_size} bytes)\n')
    summarize(meta)
