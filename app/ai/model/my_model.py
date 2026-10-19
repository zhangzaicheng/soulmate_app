from dotenv import load_dotenv
import os

from langchain_openai import ChatOpenAI

# 加载环境变量（大模型的api_key在系统环境变量 DASHSCOPE_API_KEY 中，.env不存敏感key）
load_dotenv()


class MyModel:
    """
    模型单例工厂：统一管理在线大模型 / 本地大模型 / 本地向量与重排模型
    在线模型：DashScope qwen（OpenAI兼容模式），api_key 读系统环境变量
    本地模型：Ollama（可选，用于意图识别、摘要等低敏感任务的降级）
    向量模型：本地 bge-base-zh-v1.5（长期记忆embedding）
    重排模型：本地 bge-reranker-large_v1（长期记忆检索重排）
    """
    # 在线模型
    _model = None
    # 本地模型
    _local_model = None
    # 向量模型
    _embedding = None
    # 重排模型
    _reranker = None

    # 在线大模型
    @staticmethod
    def get_model():
        if MyModel._model is None:
            api_key = os.getenv("DASHSCOPE_API_KEY")
            if not api_key:
                raise RuntimeError("未检测到系统环境变量 DASHSCOPE_API_KEY，请先在系统配置中添加")
            MyModel._model = ChatOpenAI(
                model=os.getenv("MODEL_LIME_NAME"),
                api_key=api_key,
                streaming=True,  # 开启流式输出
                extra_body={
                    "enable_thinking": False  # 关闭qwen3思考模式，陪伴对话需要即时响应
                },
            )
        return MyModel._model

    # 本地大模型（Ollama）
    @staticmethod
    def get_local_model():
        if MyModel._local_model is None:
            MyModel._local_model = ChatOpenAI(
                model=os.getenv("MODEL_LOCAL_NAME"),
                api_key="123",  # 本地Ollama需要非空key，任意值即可
                base_url=os.getenv("LOCAL_URL"),
                streaming=True,
                extra_body={
                    "enable_thinking": False
                },
            )
        return MyModel._local_model

    # 本地向量模型（bge-base-zh-v1.5，GPU加载）
    @staticmethod
    def get_embedding():
        if MyModel._embedding is None:
            from sentence_transformers import SentenceTransformer

            MyModel._embedding = SentenceTransformer(
                os.getenv("EMBEDDING_PATH", r"F:/models/bge-base-zh-v1.5"),
                device="cuda" if _cuda_available() else "cpu",
            )
        return MyModel._embedding

    # 本地重排模型（bge-reranker-large_v1，GPU加载）
    @staticmethod
    def get_reranker():
        if MyModel._reranker is None:
            from sentence_transformers import CrossEncoder

            MyModel._reranker = CrossEncoder(
                os.getenv("RERANKER_PATH", r"F:/models/bge-reranker-large_v1"),
                device="cuda" if _cuda_available() else "cpu",
            )
        return MyModel._reranker


def _cuda_available() -> bool:
    try:
        import torch

        return torch.cuda.is_available()
    except Exception:
        return False


if __name__ == "__main__":
    model = MyModel.get_model()
    rs = model.invoke("你好")
    print(rs.content)
