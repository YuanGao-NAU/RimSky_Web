#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
RimSky Craft 玩家统计导出脚本
================================
把原版世界自带的统计数据(world/stats/*.json)、成就(world/advancements/*.json)
和 usercache.json 汇总成一个静态 JS 数据文件,供网站 stats.html 纯前端渲染。

零依赖(只用 python3 标准库),只读游戏文件、只写一个输出文件,不碰服务器进程。

用法:
    python3 export_stats.py <世界目录> <网站目录>
例:
    python3 export_stats.py /home/mc/server/world /home/mc/rimsky-web

cron 每小时一次(crontab -e 加一行):
    0 * * * * python3 /home/mc/export_stats.py /home/mc/server/world /home/mc/rimsky-web
"""
import json
import os
import sys
import time


def load_usercache(world_dir):
    """uuid -> name, 来自服务器根目录的 usercache.json(在世界目录上一级)。"""
    mapping = {}
    for candidate in (os.path.join(world_dir, "..", "usercache.json"),
                      os.path.join(world_dir, "usercache.json")):
        try:
            with open(candidate, encoding="utf-8") as f:
                for e in json.load(f):
                    mapping[e.get("uuid", "").lower()] = e.get("name", "")
            break
        except (OSError, ValueError):
            continue
    return mapping


def pretty_key(k):
    """minecraft:deepslate -> deepslate"""
    return k.split(":", 1)[-1]


def summarize_player(uuid, stats_path, adv_path, name):
    with open(stats_path, encoding="utf-8") as f:
        stats = json.load(f).get("stats", {})
    custom = stats.get("minecraft:custom", {})
    mined = stats.get("minecraft:mined", {})
    used = stats.get("minecraft:used", {})

    play_ticks = custom.get("minecraft:play_time", custom.get("minecraft:play_one_minute", 0))
    walk_cm = (custom.get("minecraft:walk_one_cm", 0)
               + custom.get("minecraft:sprint_one_cm", 0))

    mined_total = sum(mined.values())
    mined_top = sorted(((pretty_key(k), v) for k, v in mined.items()),
                       key=lambda kv: -kv[1])[:12]
    # "放置"没有独立分类,方块使用次数是最接近的原版口径
    placed_total = sum(v for k, v in used.items())

    adv_done, adv_recent = 0, []
    try:
        with open(adv_path, encoding="utf-8") as f:
            adv = json.load(f)
        finished = []
        for key, val in adv.items():
            if not isinstance(val, dict) or not val.get("done"):
                continue
            if key.startswith("minecraft:recipes/"):
                continue  # 配方解锁不算成就
            crit = val.get("criteria", {})
            latest = max((str(t) for t in crit.values()), default="")
            finished.append((latest, pretty_key(key)))
        adv_done = len(finished)
        adv_recent = [k for _, k in sorted(finished, reverse=True)[:12]]
    except (OSError, ValueError):
        pass

    return {
        "name": name or uuid[:8],
        "uuid": uuid,
        "playtime_hours": round(play_ticks / 20 / 3600, 1),
        "last_seen": time.strftime("%Y-%m-%d", time.localtime(os.path.getmtime(stats_path))),
        "deaths": custom.get("minecraft:deaths", 0),
        "player_kills": custom.get("minecraft:player_kills", 0),
        "mob_kills": custom.get("minecraft:mob_kills", 0),
        "walk_km": round(walk_cm / 100000, 1),
        "mined_total": mined_total,
        "placed_total": placed_total,
        "advancements_done": adv_done,
        "mined_top": mined_top,
        "adv_recent": adv_recent,
    }


def main():
    if len(sys.argv) != 3:
        print(__doc__)
        sys.exit(1)
    world_dir, site_dir = sys.argv[1], sys.argv[2]
    stats_dir = os.path.join(world_dir, "stats")
    adv_dir = os.path.join(world_dir, "advancements")
    names = load_usercache(world_dir)

    players = []
    for fn in os.listdir(stats_dir):
        if not fn.endswith(".json"):
            continue
        uuid = fn[:-5].lower()
        try:
            players.append(summarize_player(
                uuid,
                os.path.join(stats_dir, fn),
                os.path.join(adv_dir, fn),
                names.get(uuid)))
        except (OSError, ValueError) as e:
            print("skip", fn, e)

    players.sort(key=lambda p: -p["playtime_hours"])
    out = {
        "generated": time.strftime("%Y-%m-%d %H:%M"),
        "demo": False,
        "players": players,
    }
    data_dir = os.path.join(site_dir, "data")
    os.makedirs(data_dir, exist_ok=True)
    target = os.path.join(data_dir, "stats_data.js")
    tmp = target + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        f.write("window.RIMSTATS = ")
        json.dump(out, f, ensure_ascii=False, separators=(",", ":"))
        f.write(";\n")
    os.replace(tmp, target)  # 原子替换,访客永远读不到半个文件
    print("exported", len(players), "players ->", target)


if __name__ == "__main__":
    main()
