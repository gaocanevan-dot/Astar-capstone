"""
Configuration - 配置管理

支持 RAG 和评估功能的配置
"""

from functools import lru_cache
from pathlib import Path
from pydantic_settings import BaseSettings
from pydantic import Field


class Settings(BaseSettings):
    """配置设置"""
    
    # OpenAI
    openai_api_key: str = Field(default="", env="OPENAI_API_KEY")
    openai_model: str = Field(default="gpt-4-turbo-preview", env="OPENAI_MODEL")
    openai_temperature: float = Field(default=0.1, env="OPENAI_TEMPERATURE")
    
    # Agent
    max_retries: int = Field(default=3, env="MAX_RETRIES")
    
    # Paths
    data_dir: str = Field(default="data", env="DATA_DIR")
    dataset_path: str = Field(default="data/dataset/vulnerabilities.json", env="DATASET_PATH")
    vectorstore_path: str = Field(default="data/vectorstore", env="VECTORSTORE_PATH")
    evaluation_output_dir: str = Field(default="data/evaluation", env="EVALUATION_OUTPUT_DIR")
    foundry_path: str = Field(default="", env="FOUNDRY_PATH")
    
    # RAG 设置
    use_rag: bool = Field(default=True, env="USE_RAG")
    rag_top_k: int = Field(default=5, env="RAG_TOP_K")
    use_local_embeddings: bool = Field(default=False, env="USE_LOCAL_EMBEDDINGS")
    
    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"
        extra = "ignore"


@lru_cache()
def get_settings() -> Settings:
    """获取配置"""
    return Settings()


def validate_config() -> bool:
    """验证配置"""
    settings = get_settings()
    
    if not settings.openai_api_key:
        print("Warning: OPENAI_API_KEY not set in .env")
        print("RAG retrieval with local embeddings may still work.")
        return False
    
    return True


def get_default_forge_path() -> Path:
    """Return the default per-user forge path used by Foundry installers."""
    return Path.home() / ".foundry" / "bin" / ("forge.exe" if Path.home().drive else "forge")
