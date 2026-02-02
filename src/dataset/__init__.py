"""
Dataset module for loading and managing vulnerability datasets.

核心功能:
1. DatasetLoader - 加载用户已有的漏洞数据集
2. VulnerabilityCase - 漏洞案例数据结构
3. 支持导出为训练格式 (OpenAI/Alpaca)
"""

from .schemas import TrainingExample, TrainingDataset, VulnerabilityLabel, TaskType, VulnerabilityType
from .loader import DatasetLoader, VulnerabilityCase, create_sample_dataset

__all__ = [
    "TrainingExample",
    "TrainingDataset", 
    "VulnerabilityLabel",
    "TaskType",
    "VulnerabilityType",
    "DatasetLoader",
    "VulnerabilityCase",
    "create_sample_dataset"
]
