# 文学内容锁定清单

使用 JSON，便于脚本和模型共同审计。

```json
{
  "schema_version": "1.0",
  "title": "原稿标题；无标题时为空字符串",
  "protected_names": ["人物名、地名、机构名"],
  "relationships": ["甲与乙的关系及不可改变事实"],
  "narrative": {
    "person": "第一/第二/第三人称",
    "tense": "主要时态",
    "distance": "贴近/中距/远距",
    "knowledge_limits": ["视角人物不知道或不能知道的内容"]
  },
  "timeline": ["按顺序列出时间节点"],
  "scenes": ["按顺序列出场景"],
  "plot_beats": ["事件 + 原因 + 结果"],
  "dialogue_intents": ["关键对白 + 说话人 + 潜台词"],
  "core_images": ["核心物件、意象、伏笔及功能"],
  "emotion_curve": ["起点 → 变化 → 高潮 → 结尾落点"],
  "ending_outcome": "结局事实与余味",
  "creative_stance": "作品对人物和事件的基本态度",
  "required_phrases": ["用户要求原样保留的短句"],
  "user_constraints": ["其他不可修改项"]
}
```

锁定清单只记录原文能够支持的内容。不要把分析者的解释当成作者设定。

