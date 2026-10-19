import math
import os
import uuid as uuid_lib
from datetime import datetime

import chromadb
from chromadb import EmbeddingFunction, Documents
from dotenv import load_dotenv

from app.ai.model.my_model import MyModel

load_dotenv()

_collection = None

"""
记忆分层与遗忘曲线：
- 层级：1核心(永不遗忘) / 2重要(慢忘) / 3常规(正常遗忘)，按重要性自动分配
- 艾宾浩斯保留率：retention = e^(-天数/S)，S为层级的记忆稳定性
- 检索时：最终得分 = 重排得分 × 保留率（老的记忆自然沉底）
- 记忆命中：access_count+1并刷新last_accessed（回想巩固记忆），
  回想5次以上自动升一层（记忆巩固）
- 清理：常规层记忆保留率<5%时由定时任务清理（Chroma向量+MySQL元数据同步删除）
"""
LAYER_STABILITY = {1: 3650, 2: 60, 3: 14}  # 记忆稳定性（天）
PROMOTE_ACCESS = 5  # 回想次数达到该值自动升一层


def _assign_layer(importance: float) -> int:
    if importance >= 0.85:
        return 1
    if importance >= 0.6:
        return 2
    return 3


class BGEEmbeddingFunction(EmbeddingFunction):
    """Chroma自定义embedding函数：包装MyModel的bge向量单例"""

    def __call__(self, input: Documents):
        model = MyModel.get_embedding()
        vectors = model.encode(list(input), normalize_embeddings=True)
        return [v.tolist() for v in vectors]


def _get_collection():
    """获取Chroma长期记忆集合（单例，余弦相似度）"""
    global _collection
    if _collection is None:
        client = chromadb.PersistentClient(path=os.getenv("CHROMA_PATH", "F:/work_space/soulmate_app/chroma_db"))
        _collection = client.get_or_create_collection(
            name="long_memory",
            embedding_function=BGEEmbeddingFunction(),
            metadata={"hnsw:space": "cosine"},
        )
    return _collection


class LongMemory:
    """长期记忆：向量本体存Chroma（bge-base-zh-v1.5编码），元数据存MySQL long_term_memories表"""

    # 写入一批记忆（自动分层 + 去重 + MySQL元数据同步落库）
    def add(self, memory_items: list[dict], user_id: int):
        if not memory_items:
            return
        collection = _get_collection()

        from app.common.mysql_db import mysql_db

        ids, documents, metadatas = [], [], []
        for item in memory_items:
            content = item["content"].strip()
            if not content:
                continue
            # 去重：与该用户已有记忆比对余弦距离，几乎相同的跳过
            if collection.count() > 0:
                rs = collection.query(
                    query_texts=[content], n_results=1, where={"user_id": user_id}
                )
                if rs["documents"] and rs["documents"][0] and rs["distances"][0][0] < 0.15:
                    print(f"长期记忆去重跳过: {content}")
                    continue
            mid = uuid_lib.uuid4().hex
            layer = _assign_layer(item.get("importance", 0.5))
            ids.append(mid)
            documents.append(content)
            metadatas.append({"user_id": user_id, "category": item.get("category", "fact")})
            # MySQL元数据同步落库
            with mysql_db() as db:
                db["cursor"].execute(
                    "INSERT INTO long_term_memories(memory_id, user_id, content, category, importance, layer) "
                    "VALUES(%s,%s,%s,%s,%s,%s)",
                    (mid, user_id, content, item.get("category", "fact"), item.get("importance", 0.5), layer),
                )
        if ids:
            collection.add(ids=ids, documents=documents, metadatas=metadatas)
            print(f"长期记忆写入{len(ids)}条")

    # 检索：bge向量召回n条（按用户隔离），返回(内容, 距离, memory_id)
    def query(self, user_id: int, question: str, n_results: int = 10) -> list[tuple[str, float, str]]:
        collection = _get_collection()
        if collection.count() == 0:
            return []
        rs = collection.query(
            query_texts=[question],
            n_results=min(n_results, collection.count()),
            where={"user_id": user_id},
        )
        if not rs["documents"] or not rs["documents"][0]:
            return []
        return list(zip(rs["documents"][0], rs["distances"][0], rs["ids"][0]))

    # 重排：bge-reranker对召回结果打分排序（sigmoid后0-1分）
    def rerank(self, question: str, items: list[tuple[str, float, str]]) -> list[tuple[str, float, str]]:
        if not items:
            return []
        reranker = MyModel.get_reranker()
        pairs = [(question, m) for m, _, _ in items]
        scores = reranker.predict(pairs)
        scored = sorted(zip(items, scores), key=lambda x: x[1], reverse=True)
        # 记忆检索是模糊联想场景（如"你还记得我叫什么吗"这类元问题rerank分很低），
        # reranker只用于排序，阈值仅过滤极端无关内容
        return [(it[0], s, it[2]) for it, s in scored if s > 0.02]

    # ---------- 遗忘曲线 ----------
    def _retention(self, meta: dict) -> float:
        """艾宾浩斯保留率：retention = e^(-天数/S)"""
        stability = LAYER_STABILITY.get(meta["layer"], 14)
        days = max((datetime.now() - meta["last_accessed"]).total_seconds() / 86400, 0)
        return math.exp(-days / stability)

    def _get_metas(self, memory_ids: list[str]) -> dict:
        if not memory_ids:
            return {}
        from app.common.mysql_db import mysql_db

        placeholders = ",".join(["%s"] * len(memory_ids))
        with mysql_db() as db:
            db["cursor"].execute(
                f"SELECT memory_id, layer, last_accessed FROM long_term_memories WHERE memory_id IN ({placeholders})",
                tuple(memory_ids),
            )
            return {r["memory_id"]: r for r in db["cursor"].fetchall()}

    def _touch(self, memory_ids: list[str]):
        """记忆被回想：access_count+1并刷新时间（回想巩固），回想5次以上升一层"""
        if not memory_ids:
            return
        from app.common.mysql_db import mysql_db

        placeholders = ",".join(["%s"] * len(memory_ids))
        with mysql_db() as db:
            db["cursor"].execute(
                f"UPDATE long_term_memories SET access_count=access_count+1, last_accessed=NOW() "
                f"WHERE memory_id IN ({placeholders})",
                tuple(memory_ids),
            )
            db["cursor"].execute(
                f"UPDATE long_term_memories SET layer=layer-1 "
                f"WHERE memory_id IN ({placeholders}) AND access_count >= {PROMOTE_ACCESS} AND layer > 1",
                tuple(memory_ids),
            )

    # 检索+重排+遗忘衰减（返回内容列表）
    def query_with_rerank(self, user_id: int, question: str, recall_n: int = 10, top_k: int = 4) -> list[str]:
        recalled = self.query(user_id, question, recall_n)
        ranked = self.rerank(question, recalled)
        if not ranked:
            return []
        # 最终得分 = 重排得分 × 记忆保留率（老记忆自然沉底，核心层几乎不衰减）
        metas = self._get_metas([mid for _, _, mid in ranked])
        effective = []
        for content, score, mid in ranked:
            meta = metas.get(mid)
            retention = self._retention(meta) if meta else 1.0
            effective.append((content, score * retention, mid))
        effective.sort(key=lambda x: x[1], reverse=True)
        # 命中的记忆回想巩固
        self._touch([mid for _, _, mid in effective[:top_k]])
        return [content for content, _, _ in effective[:top_k]]

    # 删除记忆（Chroma向量 + 由路由层删MySQL元数据）
    def delete(self, memory_id: str):
        collection = _get_collection()
        collection.delete(ids=[memory_id])

    # 清理遗忘殆尽的常规层记忆（定时任务每日调用）
    def cleanup_expired(self, min_retention: float = 0.05) -> int:
        from app.common.mysql_db import mysql_db

        with mysql_db() as db:
            db["cursor"].execute(
                "SELECT memory_id FROM long_term_memories WHERE layer=3"
            )
            rows = db["cursor"].fetchall()
        if not rows:
            return 0
        metas = self._get_metas([r["memory_id"] for r in rows])
        expired = [
            mid for mid, meta in metas.items()
            if self._retention(meta) < min_retention
        ]
        if not expired:
            return 0
        placeholders = ",".join(["%s"] * len(expired))
        collection = _get_collection()
        collection.delete(ids=expired)
        with mysql_db() as db:
            db["cursor"].execute(
                f"DELETE FROM long_term_memories WHERE memory_id IN ({placeholders})",
                tuple(expired),
            )
        return len(expired)
