"""测试公共配置：把 backend 加进导入路径，测试只测纯逻辑，不连数据库、Redis 和模型。"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))