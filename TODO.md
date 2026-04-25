# TODO - 待完成工作

> 最后更新: 2026-04-25

## Phase 9 - 产品化 (进行中)

### Task 9-1: Docker 化验证 ⏳

**状态**: 待验证

**说明**: Dockerfile 和 docker-compose.yml 已创建，但需要在有 Docker 的环境中验证。

**验证步骤**:
```bash
# 1. 构建镜像
docker build -t ai-companion .

# 2. 运行测试
docker run -it ai-companion python -m ai_companion start

# 3. 使用 docker-compose
docker-compose up -d
docker-compose logs -f
```

**负责人**: 待指派

**依赖**: 需要 Docker 环境

---

## 已完成的工作

| 日期 | Task | 状态 |
|------|------|------|
| 2026-04-25 | Phase 8-5 接入配置示例 | ✅ 完成 |
| 2026-04-25 | Phase 8-6 真实环境验证 | ✅ 完成 |
| 2026-04-25 | Phase 9-2 完整对话流程压测 | ✅ 完成 |
| 2026-04-25 | Phase 9-3 一键安装脚本 Docker 选项 | ✅ 完成 |
| 2026-04-25 | 代码重构 (gateway 模块) | ✅ 完成 |

---

## 可能的未来工作

### 可选: sentence-transformers 本地向量嵌入

**文件**: `ai_companion/memory/stores/episodic.py`

**说明**: 当前使用 jieba + SQLite tokens 方案作为中文搜索的降级方案。可选的 sentence-transformers 可以提升向量召回准确性。

**依赖**:
```bash
pip install sentence-transformers
```

**验证脚本**:
```python
from ai_companion.memory.stores.episodic import EpisodicStore
store = EpisodicStore("/tmp/test.db", "/tmp/chroma", embedding_mode="local")
encoder = store._get_encoder()
emb = encoder.encode("今天吃了火锅")
print(f"向量维度: {len(emb)}")  # 期望 384
```

---

## 完成标准

- [ ] Task 9-1: Docker 镜像构建成功
- [ ] Task 9-1: Docker 容器运行正常
- [ ] Task 9-1: 配置文件挂载正确
- [ ] Task 9-1: 数据目录持久化正确
