# 鲸鲸 · JingJing

> 会记事的 QQ 群 AI 群友 / An AI companion for QQ groups and Bilibili DMs

一个跑在 AstrBot 上的 AI 群友。会聊天、会记事、会交朋友，也会在该安静的时候安静。

## 它是什么

鲸鲸不是客服机器人。她是群里的一个人：温柔、有点软、偶尔犯迷糊，被叫到会应，没人叫就不打扰。

- **QQ 群**：只在被叫到时说话，叫完能接着聊几轮，然后自己收尾
- **B 站私信**：真的能收发消息，能发表情，你分享视频她会去看
- **记忆**：分核心、群、成员三层，按群隔离，私聊单独一块
- **关系**：和每个人的熟悉度会慢慢长，但一晚上聊再多也不会变成老熟人

## 结构

```
plugins/
  astrbot_plugin_xiaozhao_smart_mention/   聊天行为：判定、续聊、收尾、表情包
  astrbot_plugin_jingjing_memory_bridge/   记忆：召回、总结、提炼、整理
  astrbot_plugin_jingjing_bili/            B 站：私信、看视频、逛 B 站
memory/                                    记忆库管理工具（命令行）
tools/                                     运维脚本：行为报告、延迟分析
client/                                    桌面控制台（本地 Web UI）
docs/                                      设计与交接文档
```

## 依赖

- [AstrBot](https://github.com/AstrBotDevs/AstrBot) 4.29+
- NapCat（QQ 协议端）或任意 OneBot v11 实现
- 一个支持函数调用的模型（开发时用 DeepSeek）

## 快速开始

1. 把 `plugins/` 下三个目录放进 AstrBot 的 `data/plugins/`
2. 初始化记忆库：`python3 memory/memctl.py init`
3. 在 AstrBot 配置里填好机器人 QQ、群号、模型
4. 重启 AstrBot

控制台：

```
python client/app.py
```

## 记忆怎么工作

1. **收集**：每 12 条消息把这段对话读一遍，只留长期有用的事实
2. **过滤**：关于机器人自身的话、对人的评价、抱怨、敏感信息，一律不进
3. **提炼**：同一个人的记忆会重写成一段不超过 120 字的笔记，不是越攒越多
4. **纠错**：新事实会作废旧事实（归档，不删除）
5. **遗忘**：120 天没被强化、只出现一次的自动归档
6. **召回**：按 BM25 相关性 + 时间新鲜度排序，同义词会扩展

## 设计原则

- 宁可少说，不要多话
- 宁可少记，不要乱记
- 核心人格全局唯一，群里的差异只体现在节奏和话题上
- 任何自动化都能被一句话关掉

## 许可

MIT
