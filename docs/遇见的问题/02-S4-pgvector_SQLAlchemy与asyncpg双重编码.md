# pgvector SQLAlchemy 与 asyncpg 双重编码

> 日期：2026-08-26  
> 状态：已解决

## 现象

SQLAlchemy ORM 写入 `VECTOR(2048)` 时，asyncpg 报错：

```text
expected list or ndarray
```

错误参数在进入 asyncpg Codec 前已经变成类似 `[1.0,0.0,...]` 的字符串。

## 原因

`pgvector.sqlalchemy.VECTOR` 自带 Bind Processor，会将 Python `list[float]` 转换为 PostgreSQL Vector
Text。与此同时，Engine Connection Hook 又执行了 `pgvector.asyncpg.register_vector`，Binary Codec
期望收到原始 List/Vector，结果收到 Text 后进行第二次编码并失败。

```text
list[float]
→ SQLAlchemy VECTOR Bind Processor
→ string
→ asyncpg Binary Codec（期望 list）
→ DataError
```

## 修正

SQLAlchemy ORM 路径：

```text
只使用 pgvector.sqlalchemy.VECTOR
不注册 asyncpg Binary Codec
```

Direct asyncpg 路径：

```text
不经过 SQLAlchemy VECTOR Bind Processor
使用 pgvector.asyncpg.register_vector
```

两种 Adapter 选择其一，不能叠加。

## 防回归

`test_pgvector_infrastructure.py` 同时验证：

- ORM Insert；
- 2048 维 Round-Trip；
- `vector_dims()`；
- Cosine Distance Parameter Binding；
- Exact Nearest Neighbor Result。
