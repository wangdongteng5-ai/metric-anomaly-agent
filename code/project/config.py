# config.py —— 所有模块共用的配置：模型、key、代理（只写这一处）
import os
from dotenv import load_dotenv
from openai import OpenAI

load_dotenv()                                     # 自动向上查找并读取 D:\ai-agent-learning\.env
os.environ["NO_PROXY"] = "localhost,127.0.0.1"    # 本地 Ollama 不走 Clash 代理

llm = OpenAI(base_url="https://openrouter.ai/api/v1", api_key=os.getenv("OPENROUTER_API_KEY"))  # 对话模型（云端）
emb = OpenAI(base_url="http://localhost:11434/v1", api_key="ollama")                            # 向量模型（本地）
CHAT_MODEL = "deepseek/deepseek-chat"
EMB_MODEL = "bge-m3"
