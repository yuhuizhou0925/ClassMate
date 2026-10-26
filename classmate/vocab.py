"""Technical vocabulary for speech recognition in computer-science / AI application development courses.

The recogniser accepts at most 100 key terms per session (AssemblyAI; Deepgram and ElevenLabs take 50), and too
many common words cause over-corrections. So the full library is not sent: `pick_keyterms` chooses, for each
recording, your own terms first, then library terms that appear in the course notes or the recent transcript,
then the core terms below.

Exact spelling and capitalisation matter. Plain English words (agent, token, model, prompt, cache...) are left out
or written as longer phrases on purpose.
"""
from __future__ import annotations

import re
from functools import lru_cache

VOCAB = {
    "databases": [
        "Redis", "Memcached", "MongoDB", "MySQL", "MariaDB", "PostgreSQL", "SQLite", "Oracle Database",
        "SQL Server", "TiDB", "OceanBase", "PolarDB", "CockroachDB", "Cassandra", "ScyllaDB", "HBase", "DynamoDB",
        "Cosmos DB", "Firestore", "Firebase", "Supabase", "Neo4j", "ArangoDB", "JanusGraph", "InfluxDB",
        "TimescaleDB", "ClickHouse", "Apache Doris", "StarRocks", "Apache Druid", "Snowflake", "BigQuery",
        "Redshift", "Databricks", "Delta Lake", "Apache Iceberg", "Apache Hudi", "Hive", "Presto", "Trino",
        "Elasticsearch", "OpenSearch", "Solr", "Meilisearch", "Typesense", "MinIO", "Amazon S3", "Ceph", "HDFS",
        "RocksDB", "LevelDB", "etcd", "Consul", "ZooKeeper", "Milvus", "Pinecone", "Weaviate", "Qdrant", "Chroma",
        "FAISS", "pgvector", "Zilliz", "LanceDB", "Vespa", "PostGIS", "B+ tree", "LSM tree", "WAL", "MVCC", "ACID",
        "CAP theorem", "sharding", "binlog", "redo log", "undo log", "ORM", "MyBatis", "MyBatis-Plus", "Hibernate",
        "SQLAlchemy", "Prisma", "Sequelize", "TypeORM", "GORM", "Drizzle ORM", "NoSQL", "NewSQL",
        "主从复制", "分库分表", "读写分离", "联合索引", "覆盖索引", "回表", "事务隔离级别", "乐观锁", "悲观锁", "死锁",
        "慢查询", "连接池", "数据库", "索引", "存储过程", "触发器",
    ],
    "messaging_and_data": [
        "Kafka", "RabbitMQ", "RocketMQ", "Apache Pulsar", "ActiveMQ", "NATS", "ZeroMQ", "Redis Streams",
        "Amazon SQS", "Amazon SNS", "Kinesis", "Pub/Sub", "Celery", "Sidekiq", "BullMQ", "Flink", "Apache Spark",
        "Spark Streaming", "Apache Storm", "Kafka Streams", "Kafka Connect", "Debezium", "CDC", "Airflow",
        "Dagster", "Prefect", "dbt", "Schema Registry", "Avro", "Protobuf", "Protocol Buffers", "Parquet",
        "ORC", "exactly-once", "at-least-once", "at-most-once", "ETL", "ELT", "OLTP", "OLAP", "数据湖", "数据仓库",
        "湖仓一体", "数据中台", "消息队列", "事件驱动", "发布订阅", "死信队列", "延迟队列", "削峰填谷", "最终一致性",
        "实时计算", "离线计算", "批处理", "流处理", "Lambda 架构", "Kappa 架构",
    ],
    "cloud_and_devops": [
        "AWS", "Azure", "Google Cloud", "GCP", "阿里云", "腾讯云", "华为云", "火山引擎", "EC2", "ECS", "EKS", "AKS",
        "GKE", "AWS Lambda", "Fargate", "CloudFront", "Route 53", "IAM", "VPC", "CloudWatch", "CloudFormation",
        "Terraform", "Pulumi", "Ansible", "Docker", "Docker Compose", "Dockerfile", "Podman", "containerd",
        "Kubernetes", "K8s", "kubectl", "Helm", "Kustomize", "Istio", "Linkerd", "Envoy", "Nginx", "OpenResty",
        "HAProxy", "Traefik", "Caddy", "Kong", "APISIX", "Jenkins", "GitLab CI", "GitHub Actions", "Argo CD",
        "Tekton", "CircleCI", "SonarQube", "Harbor", "Artifactory", "Grafana", "Prometheus", "Loki", "Jaeger",
        "Zipkin", "OpenTelemetry", "SkyWalking", "ELK", "Logstash", "Kibana", "Fluentd", "Fluent Bit", "Datadog",
        "Sentry", "HashiCorp Vault", "Nacos", "Sentinel", "Hystrix", "Resilience4j", "Kubernetes Operator", "CRD",
        "StatefulSet", "DaemonSet", "ConfigMap", "Ingress", "Service Mesh", "Sidecar", "Serverless", "FaaS",
        "PaaS", "IaaS", "SaaS", "CI/CD", "DevOps", "GitOps", "SRE", "SLA", "SLO", "SLI", "MTTR", "HPA",
        "Linux", "Ubuntu", "CentOS", "Debian", "systemd", "crontab", "SSH", "Bash", "Zsh", "Vim", "tmux",
        "Git", "GitHub", "GitLab", "Gitee", "pull request", "merge request", "git rebase", "cherry-pick",
        "蓝绿部署", "灰度发布", "金丝雀发布", "滚动更新", "容器编排", "弹性伸缩", "可观测性", "链路追踪", "日志采集",
        "监控告警", "容器化", "云原生", "镜像仓库",
    ],
    "networking_and_security": [
        "TCP", "UDP", "HTTP", "HTTPS", "HTTP/2", "HTTP/3", "QUIC", "TLS", "SSL", "DNS", "CDN", "WebSocket", "gRPC",
        "RESTful", "REST API", "GraphQL", "tRPC", "Thrift", "Dubbo", "RPC", "MQTT", "WebRTC", "SSE", "OAuth 2.0",
        "OpenID Connect", "OIDC", "SAML", "SSO", "JWT", "RBAC", "ABAC", "CORS", "CSRF", "XSS", "SQL 注入", "DDoS",
        "WAF", "Let's Encrypt", "AES", "RSA", "SHA-256", "HMAC", "bcrypt", "OWASP", "IPv6", "NAT", "VPN",
        "零信任", "鉴权", "认证", "授权", "限流", "熔断", "降级", "负载均衡", "反向代理", "正向代理", "长连接",
        "三次握手", "四次挥手", "拥塞控制", "滑动窗口", "防火墙", "API 网关", "服务发现", "服务注册", "加密", "签名",
    ],
    "languages_and_runtimes": [
        "Python", "Java", "JavaScript", "TypeScript", "Golang", "Rust", "C++", "C#", "Kotlin", "Swift",
        "Objective-C", "Dart", "Scala", "Ruby", "PHP", "Lua", "Elixir", "Erlang", "Haskell", "Julia", "MATLAB",
        "PowerShell", "SQL", "WebAssembly", "Wasm", "JVM", "JDK", "GraalVM", "CPython", "PyPy", "Node.js", "Deno",
        "Bun", "V8", ".NET", "ASP.NET", "goroutine", "async/await", "coroutine", "lambda 表达式", "JIT",
        "协程", "线程池", "多线程", "多进程", "垃圾回收", "编译器", "解释器", "泛型", "闭包", "反射", "注解",
        "装饰器", "函数式编程", "面向对象", "设计模式", "单例模式", "工厂模式", "观察者模式", "策略模式", "依赖注入",
        "IoC", "AOP", "内存泄漏", "并发编程", "异步编程",
    ],
    "backend_frameworks": [
        "Spring", "Spring Boot", "Spring Cloud", "Spring MVC", "Spring Security", "Spring AI", "Netty", "Vert.x",
        "Quarkus", "Micronaut", "Django", "Django REST framework", "Flask", "FastAPI", "Tornado", "Starlette",
        "Pydantic", "Uvicorn", "Gunicorn", "Express", "Koa", "NestJS", "Fastify", "Next.js", "Nuxt", "Remix", "Gin",
        "Echo", "Fiber", "Beego", "go-zero", "Kratos", "Kitex", "Hertz", "Actix", "Axum", "Tokio", "Laravel",
        "Symfony", "Ruby on Rails", "Phoenix", "ASP.NET Core", "Swagger", "OpenAPI", "Postman", "Apifox",
    ],
    "frontend_and_mobile": [
        "React", "React Native", "Vue", "Vue.js", "Angular", "Svelte", "SvelteKit", "SolidJS", "Astro", "Vite",
        "Webpack", "Rollup", "esbuild", "Babel", "SWC", "Turbopack", "pnpm", "npm", "Yarn", "ESLint", "Prettier",
        "Tailwind CSS", "Sass", "Less", "CSS Modules", "styled-components", "Ant Design", "Element Plus",
        "Material UI", "shadcn/ui", "Chakra UI", "Redux", "Zustand", "MobX", "Pinia", "Vuex", "React Query",
        "TanStack Query", "SWR", "Axios", "React Router", "Vue Router", "Jest", "Vitest", "Cypress", "Playwright",
        "Puppeteer", "Storybook", "Electron", "Tauri", "Flutter", "SwiftUI", "Jetpack Compose", "UniApp", "Taro",
        "微信小程序", "小程序", "PWA", "SPA", "SSR", "SSG", "CSR", "hydration", "Virtual DOM", "虚拟 DOM",
        "响应式", "组件化", "微前端", "qiankun", "Module Federation", "Three.js", "WebGL", "D3.js", "ECharts",
        "HTML", "CSS", "DOM", "JSX", "Hooks", "useEffect", "useState",
    ],
    "machine_learning": [
        "机器学习", "深度学习", "神经网络", "卷积神经网络", "循环神经网络", "CNN", "RNN", "LSTM", "GRU", "Transformer",
        "注意力机制", "self-attention", "multi-head attention", "encoder-decoder", "BERT", "RoBERTa", "T5", "GPT",
        "ViT", "ResNet", "VGG", "U-Net", "YOLO", "GAN", "VAE", "diffusion model", "扩散模型", "Stable Diffusion",
        "CLIP", "word2vec", "GloVe", "softmax", "ReLU", "GELU", "sigmoid", "tanh", "dropout", "batch normalization",
        "layer normalization", "LayerNorm", "residual connection", "残差连接", "backpropagation", "反向传播",
        "gradient descent", "梯度下降", "SGD", "Adam", "AdamW", "learning rate", "学习率", "过拟合", "欠拟合",
        "正则化", "cross-entropy", "交叉熵", "loss function", "损失函数", "激活函数", "超参数", "epoch", "batch size",
        "训练集", "验证集", "测试集", "数据增强", "迁移学习", "预训练", "微调", "fine-tuning", "few-shot", "zero-shot",
        "监督学习", "无监督学习", "强化学习", "自监督学习", "对比学习", "聚类", "K-means", "KNN", "SVM", "决策树",
        "随机森林", "XGBoost", "LightGBM", "CatBoost", "逻辑回归", "线性回归", "PCA", "t-SNE", "UMAP", "准确率",
        "召回率", "精确率", "F1 score", "AUC", "ROC", "BLEU", "ROUGE", "perplexity", "困惑度", "混淆矩阵",
        "特征工程", "embedding", "嵌入向量", "向量化", "余弦相似度", "cosine similarity", "欧氏距离", "tokenization",
        "tokenizer", "BPE", "SentencePiece", "分词", "计算机视觉", "自然语言处理", "NLP", "目标检测", "图像分割",
        "语义分割", "图像分类", "homography", "RANSAC", "SIFT",
    ],
    "llm_applications": [
        "LLM", "大语言模型", "大模型", "基座模型", "foundation model", "GPT-4", "GPT-4o", "GPT-5", "ChatGPT",
        "Claude", "Gemini", "Llama", "Llama 3", "Mistral", "Mixtral", "Qwen", "通义千问", "DeepSeek", "DeepSeek-R1",
        "DeepSeek-V3", "文心一言", "ERNIE", "豆包", "Doubao", "Kimi", "智谱", "GLM", "ChatGLM", "百川", "MiniMax",
        "混元", "讯飞星火", "Phi-3", "Gemma", "Grok", "OpenAI", "Anthropic", "Hugging Face", "ModelScope", "魔搭",
        "Ollama", "vLLM", "llama.cpp", "LM Studio", "TensorRT-LLM", "SGLang", "Text Generation Inference",
        "Triton Inference Server", "ONNX", "ONNX Runtime", "OpenVINO", "MLX", "GGUF", "量化", "quantization",
        "INT8", "INT4", "FP16", "BF16", "AWQ", "GPTQ", "KV cache", "KV 缓存", "PagedAttention", "FlashAttention",
        "speculative decoding", "投机解码", "continuous batching", "MoE", "Mixture of Experts", "混合专家", "RAG",
        "检索增强生成", "retrieval-augmented generation", "LangChain", "LangGraph", "LangSmith", "LlamaIndex",
        "Haystack", "Semantic Kernel", "AutoGen", "CrewAI", "Dify", "Coze", "扣子", "FastGPT", "MaxKB", "RAGFlow",
        "Flowise", "n8n", "OpenAI API", "Assistants API", "function calling", "函数调用", "tool calling", "工具调用",
        "MCP", "Model Context Protocol", "A2A", "AI agent", "智能体", "multi-agent", "多智能体", "ReAct",
        "chain of thought", "思维链", "tree of thoughts", "self-consistency", "prompt engineering", "提示词工程",
        "提示词", "system prompt", "系统提示词", "few-shot prompting", "in-context learning", "上下文学习",
        "context window", "上下文窗口", "长上下文", "structured output", "JSON mode", "结构化输出", "流式输出",
        "temperature", "top-p", "top-k", "幻觉", "hallucination", "guardrails", "内容安全", "prompt injection",
        "提示词注入", "jailbreak", "越狱", "对齐", "RLHF", "DPO", "PPO", "GRPO", "SFT", "指令微调",
        "instruction tuning", "LoRA", "QLoRA", "PEFT", "P-tuning", "knowledge distillation", "知识蒸馏",
        "reward model", "奖励模型", "reasoning model", "推理模型", "test-time compute", "embedding model",
        "嵌入模型", "BGE", "text-embedding-3", "reranker", "重排序", "chunking", "文本切分", "hybrid search",
        "混合检索", "BM25", "向量检索", "语义检索", "知识库", "knowledge graph", "知识图谱", "GraphRAG", "Agentic RAG",
        "query rewriting", "查询改写", "HyDE", "multimodal", "多模态", "vision language model", "VLM", "视觉语言模型",
        "OCR", "ASR", "语音识别", "TTS", "语音合成", "Whisper", "文生图", "文生视频", "Sora", "Midjourney", "DALL-E",
        "ComfyUI", "ControlNet", "AIGC", "生成式 AI", "generative AI", "GitHub Copilot", "Cursor", "Claude Code",
        "Codex", "AI 编程", "vibe coding", "LLM evaluation", "benchmark", "MMLU", "HumanEval", "GSM8K",
        "LLM-as-a-judge", "RAGAS", "LLMOps", "MLOps", "模型部署", "模型推理", "推理加速", "推理服务", "model serving",
        "Ray", "Ray Serve", "KServe", "BentoML", "MLflow", "Weights & Biases", "wandb", "TensorBoard", "Kubeflow",
        "SageMaker", "Vertex AI", "Amazon Bedrock", "Azure OpenAI", "阿里云百炼", "千帆", "火山方舟", "API key",
        "rate limit", "prompt caching", "提示词缓存", "semantic cache", "语义缓存", "AI 网关", "LiteLLM",
        "OpenRouter", "Gradio", "Streamlit", "Chainlit", "Open WebUI", "LobeChat", "AI 应用开发", "Copilot",
        "向量数据库",
    ],
    "ml_frameworks_and_hardware": [
        "PyTorch", "TensorFlow", "Keras", "JAX", "Flax", "PaddlePaddle", "飞桨", "MindSpore", "昇思",
        "scikit-learn", "NumPy", "Pandas", "Polars", "SciPy", "Matplotlib", "Seaborn", "Plotly", "Jupyter",
        "Jupyter Notebook", "Google Colab", "Kaggle", "OpenCV", "Pillow", "spaCy", "NLTK", "jieba",
        "Hugging Face Transformers", "Accelerate", "DeepSpeed", "Megatron-LM", "FSDP", "Horovod", "CUDA", "cuDNN",
        "NCCL", "ROCm", "GPU", "TPU", "NPU", "A100", "H100", "H800", "RTX 4090", "昇腾", "Ascend", "显存",
        "混合精度", "分布式训练", "数据并行", "模型并行", "张量并行", "流水线并行", "ZeRO", "gradient checkpointing",
        "梯度累积", "算力",
    ],
    "system_design": [
        "微服务", "microservices", "单体架构", "monolith", "分布式系统", "分布式", "高并发", "高可用", "高性能",
        "可扩展性", "scalability", "水平扩展", "垂直扩展", "无状态", "有状态", "缓存穿透", "缓存击穿", "缓存雪崩",
        "布隆过滤器", "Bloom filter", "一致性哈希", "consistent hashing", "分布式锁", "分布式事务", "两阶段提交",
        "2PC", "TCC", "Saga", "Seata", "幂等", "幂等性", "背压", "backpressure", "秒杀", "订单系统", "支付系统",
        "推荐系统", "搜索引擎", "倒排索引", "领域驱动设计", "DDD", "限界上下文", "聚合根", "CQRS", "事件溯源",
        "event sourcing", "六边形架构", "整洁架构", "clean architecture", "分层架构", "MVC", "MVVM", "BFF",
        "Backend for Frontend", "API 设计", "接口幂等", "服务治理", "服务降级", "服务熔断", "服务限流", "注册中心",
        "配置中心", "全链路压测", "压测", "JMeter", "Locust", "QPS", "TPS", "P99", "吞吐量", "单点故障", "容灾",
        "异地多活", "冷备", "热备", "主备切换", "心跳检测", "Raft", "Paxos", "Gossip 协议", "雪花算法",
        "Snowflake ID", "UUID", "短链接", "令牌桶", "漏桶", "时间轮", "系统设计", "架构设计", "技术选型", "缓存",
        "产品架构", "技术架构",
    ],
    "algorithms": [
        "时间复杂度", "空间复杂度", "大 O 表示法", "链表", "哈希表", "哈希冲突", "二叉树", "二叉搜索树", "平衡二叉树",
        "AVL 树", "红黑树", "B 树", "B+ 树", "优先队列", "拓扑排序", "并查集", "前缀树", "Trie", "跳表", "skip list",
        "动态规划", "贪心算法", "回溯", "分治", "二分查找", "双指针", "深度优先搜索", "广度优先搜索", "DFS", "BFS",
        "Dijkstra", "最短路径", "最小生成树", "快速排序", "归并排序", "堆排序", "冒泡排序", "LRU", "LFU", "LeetCode",
        "数据结构", "算法",
    ],
    "engineering_and_product": [
        "单元测试", "集成测试", "端到端测试", "E2E", "回归测试", "压力测试", "TDD", "BDD", "pytest", "JUnit",
        "Mockito", "code review", "代码审查", "重构", "技术债", "敏捷开发", "Scrum", "Kanban", "需求分析", "PRD",
        "产品需求文档", "MVP", "用户故事", "UML", "时序图", "架构图", "ER 图", "原型设计", "Figma", "Axure", "墨刀",
        "埋点", "A/B 测试", "用户画像", "留存率", "转化率", "DAU", "MAU", "GMV", "ROI", "KPI", "OKR", "PMF",
        "ToB", "ToC", "低代码", "无代码", "Jira", "Confluence", "飞书", "钉钉", "Notion", "API", "SDK", "JSON",
        "YAML", "XML", "CSV", "Markdown", "IDE", "VS Code", "IntelliJ IDEA", "PyCharm",
    ],
}

# Sent when nothing more specific is known (no notes, nothing heard yet): the terms most often mis-heard in
# this kind of course.
CORE = [
    "Redis", "MySQL", "MongoDB", "PostgreSQL", "Kafka", "RabbitMQ", "Elasticsearch", "Docker", "Kubernetes",
    "Nginx", "Linux", "Git", "Python", "Java", "Golang", "JavaScript", "TypeScript", "React", "Vue",
    "Spring Boot", "Django", "FastAPI", "Node.js", "PyTorch", "TensorFlow", "Transformer", "LLM", "RAG",
    "LangChain", "LlamaIndex", "AI agent", "MCP", "embedding", "向量数据库", "大模型", "微调", "微服务", "分布式",
    "高并发", "负载均衡", "消息队列", "缓存", "API", "JSON", "SQL", "HTTP", "TCP", "gRPC", "GPU", "CUDA", "OpenAI",
    "DeepSeek", "Claude", "Qwen", "提示词", "智能体", "Milvus", "Flink", "ClickHouse",
]


def library() -> list[str]:
    """Every term once, in category order."""
    seen, out = set(), []
    for terms in VOCAB.values():
        for term in terms:
            if term.lower() not in seen:
                seen.add(term.lower())
                out.append(term)
    return out


_SPLIT = None


def _terms():
    """(Latin-script terms as lower case -> term, Chinese terms)."""
    global _SPLIT
    if _SPLIT is None:
        lib = library()
        chinese = [t for t in lib if re.search(r"[\u4e00-\u9fff]", t)]
        latin = {t.lower(): t for t in lib if t not in chinese}
        _SPLIT = (latin, chinese)
    return _SPLIT


@lru_cache(maxsize=8)
def mentioned(text: str) -> dict[str, int]:
    """Library terms found in text (whole words for Latin script, any case), with how often they occur.
    A plain substring test first keeps this fast on long course notes; cached, as the notes do not change."""
    if not text:
        return {}
    latin, chinese = _terms()
    lower = text.lower()
    counts: dict[str, int] = {}
    for key, term in latin.items():
        if key in lower:
            n = len(re.findall(rf"(?<![a-z0-9]){re.escape(key)}(?![a-z0-9])", lower))
            if n:
                counts[term] = n
    for term in chinese:
        n = text.count(term)
        if n:
            counts[term] = n
    return counts


def pick_keyterms(own=(), notes: str = "", recent: str = "", limit: int = 100) -> list[str]:
    """Your terms, then library terms heard recently, then those in the course notes (most frequent first),
    then the core terms; no duplicates, each at most 50 characters."""
    heard = mentioned(recent)
    in_notes = mentioned(notes)
    ranked = (list(own) + sorted(heard, key=lambda t: -heard[t]) + sorted(in_notes, key=lambda t: -in_notes[t])
              + CORE)
    seen, out = set(), []
    for term in ranked:
        term = str(term).strip()
        if term and len(term) <= 50 and term.lower() not in seen:
            seen.add(term.lower())
            out.append(term)
        if len(out) == limit:
            break
    return out
