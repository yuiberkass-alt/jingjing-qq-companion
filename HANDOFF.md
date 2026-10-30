# HANDOFF.md

## 项目是什么

鲸鲸是一个跑在 QQ 群和 B 站私信的 AI 群友。驱动是 DeepSeek，宿主是 AstrBot 4.29.3。
控制台是本地 Python + Edge 应用窗口。

## 线上组成

- AstrBot 容器 astrbot，NapCat 容器 napcat，都在 docker 里。
- QQ 适配器 aiocqhttp，机器人 QQ <BOT_QQ>。
- 三个插件：xiaozhao_smart_mention（聊天行为）、jingjing_memory_bridge（记忆）、jingjing_bili（B站私信）。
- 记忆库 SQLite：data/plugin_data/jingjing_memory/memory.sqlite3。
- 控制台：D:/Jingjing/client，桌面快捷方式"鲸鲸控制台"。

## 关键路径

- 记忆工具：/home/ubuntu/jingjing/memory
- 插件源码：/home/ubuntu/jingjing/data/plugins
- 发布包：D:/Jingjing/releases/2026xxxx-rNN
- 备份：plugin-backups（插件）、plugin_data/jingjing_memory/backups（数据库，每天一份留 7 天）

## 已知坑

### B 站
1. 发送私信 -400：msg[sender_uid] 必须是账号自身 uid。cookie 文件里没有这个字段，发送前要 whoami 一次。
2. 状态检查要 sudo：cookie 文件权限 600，普通用户读不到。
3. 新号限制：互相关注前只能发 1 条消息。
4. 私信游标必须在发送成功后才前进，否则失败即丢消息。
5. 首次启动不要用内存游标跳过积压，要用 settings 表里的 bili_last_key。
6. 搜视频接口需要 WBI 签名，直接用会返回 -352。
7. 表情只能发账号表情面板里的名字，发送前要校验，否则是乱码。

### AstrBot
8. 插件要有 _conf_schema.json 才会收到 config 参数，否则初始化报 missing argument。
9. 插件初始化在事件循环里，后台任务用 @filter.on_astrbot_loaded 启动。

### 记忆
10. 只有已审核（approved=1）且开启的群，才允许写记忆。
11. 成员记忆需要授权；群级开关 auto_consent=1 时按群授权即可，个人可拒绝。
12. 总结器会写进"关于机器人自身"和"骂人"的内容，提示词和代码各有一层过滤。
13. 群相处指标只统计同一人 60 秒内继续说话，否则测到的是群活跃度。

### 控制台
14. ssh 子进程必须加 CREATE_NO_WINDOW，否则每次操作弹黑框。
15. 空闲退出设 180 秒。30 秒会被浏览器后台节流误杀。
16. Windows 图标缓存按路径缓存，换图标要换文件名。

## 常用操作

- 重启：sudo docker restart -t 30 astrbot。NapCat 不用重启。
- 回滚插件：进入 releases 对应目录，sudo python3 deploy.py rollback。
- 查行为：python3 tools/chat_report.py 读日志出统计。
- 记忆体检：memctl health。整理：memctl consolidate。

## 待办

- 私聊记忆跑起来后验证总结质量。
- 逛 B 站选片逻辑改成按最近聊过的话题。
- 评论能力暂未开放。
- 微信平台暂缓。

