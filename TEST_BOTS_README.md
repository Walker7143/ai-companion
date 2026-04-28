# 测试人物使用说明

## test_proactive（主动唤醒测试）

### 角色设定
- **姓名**: 测试酱
- **年龄**: 22岁
- **职业**: 大学生
- **关系**: 恋人
- **性格**: 活泼开朗、话多、黏人、撒娇

### 测试目标
1. 情绪触发器 - 检测用户说"不开心""累"等关键词
2. 恋人模式 - 更频繁主动联系，撒娇
3. 短间隔测试 - idle_threshold=2小时，min_interval=30分钟

### 启动命令
```bash
ai-companion start --bot test_proactive
```

### 测试方法

#### 1. 测试情绪触发
在对话中说：
- "今天好累啊"
- "心情不好"
- "有点烦"

**预期**: Bot 会温柔地回应，表达关心

#### 2. 测试主动联系
- 发送消息后等待 30 分钟（Bot 时间）
- 观察 Bot 是否主动发消息

#### 3. 测试黄金时段
当前设置为 08:00-23:00，在这个时间段外 Bot 不会主动联系

## 通用调试

### 查看 Bot 状态
```
/memory
```

### 查看日志
```bash
# 主动唤醒日志
tail -f ~/.ai-companion/logs/proactive.log

# 人生轨迹日志
tail -f ~/.ai-companion/logs/life.log
```

### 重置状态
```bash
# 删除 Bot 状态文件，重新开始
rm ~/.ai-companion/data/bots/test_proactive/proactive_state.json
rm ~/.ai-companion/data/bots/test_proactive/life_state.json
```

### 查看配置文件位置
```
~/.ai-companion/
├── config/
│   └── bots.yaml
└── data/bots/
    ├── test_proactive/
    │   ├── proactive_state.json
    │   ├── life_state.json
    │   └── persona/ (配置文件)
```
