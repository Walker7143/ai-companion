# 测试人物使用说明

## 人物 1: test_proactive（主动唤醒测试）

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

---

## 人物 2: test_life（人生轨迹测试）

### 角色设定
- **姓名**: 时光君
- **年龄**: 18岁
- **职业**: 高三学生
- **关系**: 挚友
- **性格**: 内向敏感、成熟稳重

### 测试目标
1. **time_ratio=60** - 1分钟=1天，快速观察日期推进
2. **节假日检测** - 检查节假日是否正确触发
3. **生日事件** - 出生日期 4月27日，检查每年是否触发
4. **年龄里程碑** - 18/20/25/30岁各有人生大事
5. **人生阶段** - 从少年→高中→大学→职场→中年

### 启动命令
```bash
ai-companion start --bot test_life
```

### 测试方法

#### 1. 查看初始状态
启动后发送 `/memory` 查看 Bot 状态

#### 2. 等待日期推进
- time_ratio=60，每分钟 Bot 时间推进 1 天
- 观察 Bot 是否提到季节变化、日期变化

#### 3. 测试节假日（4月测试）
将 Bot 日期调整到节假日附近，观察是否触发

#### 4. 查看 life_state.json
```bash
cat ~/.ai-companion/data/bots/test_life/life_state.json
```

### 关键时间点

| Bot 时间 | 现实时间 | 事件 |
|----------|----------|------|
| 2006-04-27 | 启动后 | 生日（18岁） |
| 2006-06-07 | 启动后约1小时 | 高考（里程碑） |
| 1年 = 365分钟 ≈ 6小时 | - | 1 Bot 年 |

---

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
rm ~/.ai-companion/data/bots/test_life/proactive_state.json
rm ~/.ai-companion/data/bots/test_life/life_state.json
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
    └── test_life/
        ├── proactive_state.json
        ├── life_state.json
        └── persona/ (配置文件)
```
