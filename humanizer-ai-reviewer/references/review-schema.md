# 四角度复核 JSON 规范

每个角色单独输出一个 JSON 对象：

```json
{
  "schema_version": "1.0",
  "role": "style_fidelity | ai_language | narrative_integrity | cold_reader | arbitrator",
  "ai_risk": 0,
  "confidence": 0,
  "evidence": [
    {
      "location": "段落或句子位置",
      "excerpt": "不超过40字的短证据",
      "signal": "具体信号",
      "severity": "low | medium | high",
      "suggestion": "只说明方向，不重写全文"
    }
  ],
  "integrity_pass": true,
  "integrity_issues": [],
  "summary": "简短判断"
}
```

除 `narrative_integrity` 外，其他角色的 `integrity_pass` 固定为 `true`，`integrity_issues` 为空。

建议分段：

- 0–10：没有明显 AI 痕迹。
- 11–20：存在少量可解释信号，不妨碍自然阅读。
- 21–40：多处可识别模板，需要局部返修。
- 41–70：结构和语言明显机械。
- 71–100：大面积模板化，且缺少作者证据。

禁止根据“写得太好”“语法正确”“没有错别字”直接加分。

