# 古诗推送（云端版）

把这套推送搬到 GitHub Actions 上：**电脑关机、睡眠、断网都不影响**，到点由 GitHub 的服务器发邮件。

- **周一至周五 08:00**（北京时间）：推 2 首新诗，含注释、译文、讲解、拓展、背诵提示
- **周六 08:00**（北京时间）：本周 10 首做成复习卡片 + 串讲 + 自测题
- **周日**：不推送
- **75 首推完即自动结束**，之后不再发信

75 首讲解内容已全部预生成在 `data/poems.json`，云端**不调用任何大模型**，输出稳定、零成本。

## 目录

```
poem-push-cloud/
├── data/poems.json          # 75 首：原文 + 注释/译文/讲解/拓展/背诵
├── push.py                  # 挑诗、拼正文、发邮件、记进度（只用标准库）
├── state.json               # 进度：推到第几首、本周推过哪些、是否已结束
├── requirements.txt         # 空的，不需要第三方依赖
└── .github/workflows/push.yml
```

## 部署（5 步，约 5 分钟）

1. 在 GitHub 新建一个**私有仓库**（比如 `poem-push`），不要勾选自动生成 README。
2. 在本目录执行：

   ```bash
   git init -b main
   git add .
   git commit -m "古诗每日推送"
   git remote add origin https://github.com/<你的用户名>/<仓库名>.git
   git push -u origin main
   ```

3. 打开仓库 → Settings → Secrets and variables → Actions → New repository secret，依次添加三个：

   | Name | Value |
   |---|---|
   | `MAIL_USER` | 发件邮箱，如 `you@example.com` |
   | `MAIL_PASS` | 该邮箱的 SMTP 授权码（不是登录密码） |
   | `MAIL_TO` | 收件邮箱，多个用英文逗号隔开 |

4. 打开仓库的 **Actions** 标签，如果提示工作流被禁用，点 “I understand my workflows, go ahead and enable them”。
5. 手动跑一次验证：Actions → 古诗推送 → Run workflow → mode 填 `daily` → Run。
   几十秒后应该收到邮件；再跑一次 `summary` 可以看周总结的样子。

> 想用细粒度 token 推送代码，权限里必须有 **Contents: Read and write**，另外因为仓库含 workflow 文件，还要有 **Workflows: Read and write**。

## 时间

GitHub 的 cron 用 **UTC**，脚本里已按北京时间换算好：

| 北京时间 | UTC | cron |
|---|---|---|
| 周一至周五 08:00 | 00:00 | `0 0 * * 1-5` |
| 周六 08:00 | 00:00 | `0 0 * * 6` |

注意：

- GitHub 的定时任务**不保证准点**，高峰期可能延迟 5–20 分钟，偶尔会跳过一次。
- 公开仓库连续 60 天没有任何提交，GitHub 会自动停用定时任务；私有仓库不受此限，但建议偶尔手动跑一次。

## 推完之后

第 75 首一般是某个工作日的单首（75 是奇数，最后一天只推 1 首）。推完当天会在邮件末尾提示“75 首全部推完”，之后：

- 工作日的定时任务照常触发，但脚本会立刻退出，**不发信、不改进度**
- 收尾那一周的周六还会正常发一次本周总结，作为收束
- 从下一周起彻底静默

想再背一轮，把 `state.json` 改回初始值并提交：

```json
{"next_index": 0, "pushed_total": 0, "history": {}}
```

`finished` 和 `finished_on` 两个字段不用手动删，脚本会重新写入。

## 进度怎么记

`state.json` 里存 `next_index`（下一首从第几首开始）、`pushed_total`（已推首数）、`history`（哪天推了哪几首）。
每次跑完 workflow 会自动 `git commit` 这个文件，所以进度不会丢，也不会重复推同一首。

## 常见问题

**邮件没收到？** 先看 Actions 的运行日志，里面会打印发送结果；再看收件箱的垃圾邮件文件夹，把发件人加入白名单。

**想改时间？** 改 `.github/workflows/push.yml` 里的两行 cron，记得把北京时间换成 UTC（减 8 小时）。

**想改收件人？** 改仓库 Secrets 里的 `MAIL_TO`，不用动代码。

**能不能也推到微信？** PushPlus 需要实名认证，通过后可以在这个仓库里加一步 HTTP 请求；本仓库暂未包含。

## 本地测试

```bash
python3 push.py --date 2026-11-12 --dry-run                 # 看某天的正文
python3 push.py --mode summary --date 2026-11-14 --dry-run  # 看周总结
```

不带 `--dry-run` 且配置了 `MAIL_USER`/`MAIL_PASS`/`MAIL_TO` 环境变量时，会真的发信。
