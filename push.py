# -*- coding: utf-8 -*-
"""古诗推送（云端版）。

不依赖任何大模型：所有讲解内容已预先生成在 data/poems.json 里，
这里只负责「按日期挑诗 → 拼成正文 → 发邮件 → 记进度」。

用法：
    python3 push.py                 # 日常：周一至周五推 2 首
    python3 push.py --mode summary  # 周总结：本周学过的做成卡片
    python3 push.py --date 2026-11-12 --dry-run

环境变量（GitHub Actions 里用 Secrets 注入）：
    MAIL_USER  发件邮箱
    MAIL_PASS  SMTP 授权码
    MAIL_TO    收件邮箱，多个用逗号或分号隔开
    MAIL_HOST  可选，默认按邮箱后缀猜
    MAIL_PORT  可选，默认 465
"""

import argparse
import json
import os
import smtplib
import sys
from datetime import date, datetime, timedelta, timezone
from email.header import Header
from email.mime.text import MIMEText
from email.utils import formataddr

BASE = os.path.dirname(os.path.abspath(__file__))
DATA_FILE = os.path.join(BASE, "data", "poems.json")
STATE_FILE = os.path.join(BASE, "state.json")
CST = timezone(timedelta(hours=8))
WEEKDAY_CN = ["周一", "周二", "周三", "周四", "周五", "周六", "周日"]

PRESETS = {
    "qq.com": "smtp.qq.com", "foxmail.com": "smtp.qq.com",
    "163.com": "smtp.163.com", "126.com": "smtp.126.com",
    "sina.com": "smtp.sina.com", "aliyun.com": "smtp.aliyun.com",
    "gmail.com": "smtp.gmail.com", "outlook.com": "smtp.office365.com",
    "hotmail.com": "smtp.office365.com", "yeah.net": "smtp.yeah.net",
}


def load_json(path, default):
    if not os.path.exists(path):
        return default
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def save_state(state):
    with open(STATE_FILE, "w", encoding="utf-8") as f:
        json.dump(state, f, ensure_ascii=False, indent=2)


def poem_block(p, mark=""):
    head = f"{mark}《{p['title']}》　{p['author']}·{p['dynasty']}"
    body = "\n".join("　　" + line for line in p["text"].split("\n"))
    notes = "；".join(f"{k}：{v}" for k, v in p["notes"])
    extend = "\n".join(f"· {x}" for x in p["extend"])
    return (
        f"{head}\n{body}\n\n"
        f"【注释】{notes}\n"
        f"【译文】{p['translation']}\n"
        f"【讲解】{p['explain']}\n"
        f"【拓展】\n{extend}\n"
        f"【背诵】{p['recite']}"
    )


def daily_body(today, picks, by_no, state, total):
    cn = WEEKDAY_CN[today.weekday()]
    parts = [f"今日古诗 · {today.month}月{today.day}日 {cn}", ""]
    for mark, no in zip(("① ", "② "), picks):
        parts.append(poem_block(by_no[no], mark))
        parts.append("")
    parts.append(f"—— 已学 {state['pushed_total']}/{total} 首 · 下一个工作日 10:00 继续 ——")
    parts.append("背法：先听读正音 3 遍 → 逐句说意思 → 合上书连背 3 遍；第二天先默写名句，再学新的。")
    return "\n".join(parts)


def summary_body(today, week_nos, by_no, state, total):
    if not week_nos:
        return "本周没有推送记录。"
    lines = [f"本周总结 · {today.month}月{today.day}日 周五（本周 {len(week_nos)} 首）", ""]
    for i, no in enumerate(week_nos, 1):
        p = by_no[no]
        wrong = p["recite"].split("；")[0].rstrip("。")
        if len(wrong) > 22:
            wrong = wrong[:22] + "…"
        lines.append(f"{i}. 《{p['title']}》　{p['author']}　名句：{p['famous']}　易错：{wrong}")
    lines += ["", "【本周串讲】"]
    themes = {}
    for no in week_nos:
        t = by_no[no].get("theme", "")
        themes[t] = themes.get(t, 0) + 1
    stat = "、".join(f"{k}{v}首" for k, v in themes.items() if k)
    if stat:
        lines.append(f"本周共 {len(week_nos)} 首：{stat}。")
    pair = None
    for t, c in themes.items():
        if t and c >= 2:
            pair = [no for no in week_nos if by_no[no].get("theme") == t][:2]
            pair_theme = t
            break
    if pair:
        a, b = (by_no[no] for no in pair)
        lines.append(f"本周有两首同属{pair_theme}：《{a['title']}》和《{b['title']}》。"
                     f"可以让孩子说说，同样写这类内容，两首最大的不同在哪一句上。")
    else:
        lines.append("把同题材的几首放在一起比一比：写景诗看哪个字把景写活了，送别诗看结尾落在“情”还是“景”上。")
    lines += ["", "【周末自测】", "1. 挑一首本周的诗，说出它的名句。",
              "2. 从本周的【背诵】提示里找出 3 个易错字，默写一遍。",
              "3. 选两首同题材的诗，说说它们写同一件事的角度有什么不同。",
              "", f"—— 本周进度 {state['pushed_total']}/{total} · 周六周日休息，下周一 10:00 继续 ——"]
    return "\n".join(lines)


def send_mail(subject, body):
    user = os.environ.get("MAIL_USER", "").strip()
    pwd = os.environ.get("MAIL_PASS", "").strip()
    to = os.environ.get("MAIL_TO", "").strip()
    if not (user and pwd and to):
        print("[跳过发信] 未配置 MAIL_USER / MAIL_PASS / MAIL_TO")
        return False
    host = os.environ.get("MAIL_HOST") or PRESETS.get(user.split("@")[-1].lower(), "smtp.qq.com")
    default_port = 587 if ("gmail" in host or "office365" in host) else 465
    port = int(os.environ.get("MAIL_PORT") or default_port)
    to_list = [x.strip() for x in to.replace("；", ";").replace(",", ";").split(";") if x.strip()]

    msg = MIMEText(body, "plain", "utf-8")
    msg["Subject"] = Header(subject, "utf-8")
    msg["From"] = formataddr(("每日古诗", user))
    msg["To"] = ", ".join(to_list)

    if port == 465:
        server = smtplib.SMTP_SSL(host, port, timeout=30)
    else:
        server = smtplib.SMTP(host, port, timeout=30)
        server.starttls()
    try:
        server.login(user, pwd)
        server.sendmail(user, to_list, msg.as_string())
    finally:
        server.quit()
    print(f"邮件已发送至 {', '.join(to_list)}，正文 {len(body)} 字。")
    return True


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--mode", choices=["daily", "summary"], default="daily")
    ap.add_argument("--date", help="YYYY-MM-DD，默认北京时间今天")
    ap.add_argument("--dry-run", action="store_true", help="只打印，不发信、不写状态")
    args = ap.parse_args()

    data = load_json(DATA_FILE, {"poems": [], "total": 0})
    by_no = {p["no"]: p for p in data["poems"]}
    total = data.get("total") or len(data["poems"])
    state = load_json(STATE_FILE, {"next_index": 0, "pushed_total": 0, "history": {}})
    state.setdefault("next_index", 0)
    state.setdefault("pushed_total", 0)
    state.setdefault("history", {})

    today = date.fromisoformat(args.date) if args.date else datetime.now(CST).date()
    key = today.isoformat()
    iso = today.isocalendar()[:2]

    if args.mode == "summary":
        week = []
        for d, nos in sorted(state["history"].items()):
            dd = date.fromisoformat(d)
            if dd.isocalendar()[:2] == iso and dd.weekday() < 5:
                week.extend(nos)
        body = summary_body(today, week, by_no, state, total)
        subject = f"【本周总结】古诗 · {today.month}月{today.day}日 周五 · 本周 {len(week)} 首"
    else:
        if today.weekday() >= 5:
            print(f"今天是{WEEKDAY_CN[today.weekday()]}，按设置不推送。")
            return
        if key in state["history"]:
            picks = state["history"][key]
        else:
            start = state["next_index"] % total
            picks = [((start + i) % total) + 1 for i in range(2)]
            state["next_index"] = (start + 2) % total
            state["pushed_total"] += 2
            state["history"][key] = picks
            for d in sorted(state["history"])[:-90]:
                state["history"].pop(d, None)
        titles = "".join(f"《{by_no[n]['title']}》" for n in picks)
        body = daily_body(today, picks, by_no, state, total)
        subject = f"今日古诗 · {today.month}月{today.day}日 {WEEKDAY_CN[today.weekday()]} · {titles}"

    if args.dry_run:
        print(body)
        return

    sent = send_mail(subject, body)
    if not sent and os.environ.get("CI"):
        print("未配置邮件参数，仅输出内容。")
    save_state(state)
    print(body)


if __name__ == "__main__":
    main()
