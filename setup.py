from setuptools import setup, find_packages

with open("README.md", "r", encoding="utf-8") as f:
    long_description = f.read()

setup(
    name="ai-companion",
    version="0.1.0",
    description="开源 AI 陪伴产品，多机器人并行，每个机器人有独立人格和记忆体系",
    long_description=long_description,
    long_description_content_type="text/markdown",
    author="AI Companion Team",
    url="https://gitee.com/wang_xiao_wei_7143/ai-girl-friend",
    packages=find_packages(),
    python_requires=">=3.11",
    install_requires=[
        "aiohttp>=3.9.0",
        "pyyaml>=6.0",
        "pydantic>=2.0",
        "chroma-hnswlib>=0.1.0",
        "aiosqlite>=0.19.0",
        "rich>=13.0",
    ],
    extras_require={
        "feishu": ["feishu-sdk"],
        "dev": ["pytest>=7.0", "pytest-asyncio>=0.21"],
    },
    entry_points={
        "console_scripts": [
            "ai-companion=ai_companion.__main__:main",
        ],
    },
    package_data={
        "ai_companion": ["config/*.yaml.example"],
    },
    classifiers=[
        "Programming Language :: Python :: 3.11",
        "Programming Language :: Python :: 3.12",
        "Operating System :: OS Independent",
    ],
)
