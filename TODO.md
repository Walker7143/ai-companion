# TODO

> 最后更新: 2026-04-29

## 当前未解决/待确认

### Gateway Admin API 启动时序偶发波动

**状态**: 待稳定化

**现象**: `tests/system_test_suite.py` 的 `T12 Gateway lifecycle + admin API` 偶尔出现 `connection refused` 或 `connection reset by peer`。Gateway 进程能启动和停止，但测试探测 Admin API 的等待/重试窗口可能不够稳。

**建议处理**:

- 增加 Admin API ready check 或健康检查端点。
- 在测试中等待明确 ready 信号，而不是只按固定时间探测端口。
- 复测 Gateway 日志，确认不是端口占用或旧进程残留。

### Docker 化验证

**状态**: 待验证

**说明**: 如需交付 Docker 部署，需要在有 Docker 的环境中重新验证镜像构建、配置挂载和数据持久化。

```bash
docker build -t ai-companion .
docker run -it ai-companion ai-companion start
docker-compose up -d
docker-compose logs -f
```

## 可选未来工作

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

