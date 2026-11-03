from __future__ import annotations

import os
import re
from pathlib import Path


BASE_DIR = Path(__file__).resolve().parent


def _load_dotenv(path: Path) -> bool:
    """Load simple KEY=VALUE entries without overriding process configuration."""
    if not path.is_file():
        return False
    try:
        lines = path.read_text(encoding="utf-8-sig").splitlines()
    except OSError:
        return False
    for raw_line in lines:
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        if line.startswith("export "):
            line = line[7:].lstrip()
        key, value = line.split("=", 1)
        key = key.strip()
        if not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", key):
            continue
        value = value.strip()
        if len(value) >= 2 and value[0] == value[-1] and value[0] in {"'", '"'}:
            value = value[1:-1]
        os.environ.setdefault(key, value)
    return True


def _env_bool(name: str, default: bool = False) -> bool:
    fallback = "true" if default else "false"
    return os.getenv(name, fallback).strip().lower() in {"1", "true", "yes", "on"}


DOTENV_LOADED = _load_dotenv(BASE_DIR / ".env")
CONFIG_DATA_DIR = BASE_DIR / "config_data"
DATA_DIR = BASE_DIR / "data"
RAW_CATALOGUE_PATH = DATA_DIR / "raw" / "authoritative_catalogue.tsv"
PROFILES_JSONL_PATH = DATA_DIR / "processed" / "list_profiles.jsonl"
PROFILES_CSV_PATH = DATA_DIR / "processed" / "list_profiles.csv"
DOCUMENTS_JSONL_PATH = DATA_DIR / "processed" / "retrieval_documents.jsonl"
LEXICAL_INDEX_PATH = DATA_DIR / "indexes" / "lexical.sqlite3"
SEMANTIC_INDEX_PATH = DATA_DIR / "indexes" / "local_lsa.npz"
SEMANTIC_METADATA_PATH = DATA_DIR / "indexes" / "local_lsa_metadata.json"
CATALOGUE_MANIFEST_PATH = DATA_DIR / "manifests" / "catalogue_manifest.json"
PRODUCT_TAXONOMY_PATH = CONFIG_DATA_DIR / "product_taxonomy.json"
RELATIONSHIP_RULES_PATH = CONFIG_DATA_DIR / "relationship_rules.json"
INTEREST_RULES_PATH = CONFIG_DATA_DIR / "interest_rules.json"
AUDIENCE_ROLE_RULES_PATH = CONFIG_DATA_DIR / "audience_role_rules.json"
FINANCE_RULES_PATH = CONFIG_DATA_DIR / "finance_rules.json"
PROFESSION_RULES_PATH = CONFIG_DATA_DIR / "profession_rules.json"
EXCLUSION_RULES_PATH = CONFIG_DATA_DIR / "exclusion_rules.json"
GEOGRAPHY_PATH = CONFIG_DATA_DIR / "geography.json"
RANKING_WEIGHTS_PATH = CONFIG_DATA_DIR / "ranking_weights.json"
INTENT_RULES_PATH = CONFIG_DATA_DIR / "intent_rules.json"
AI_RELEVANCE_POLICY_PATH = CONFIG_DATA_DIR / "ai_relevance_policy.json"
CLASS_AFFINITY_POLICY_PATH = CONFIG_DATA_DIR / "class_affinity_policy.json"
EMBEDDING_CACHE_DIR = DATA_DIR / "indexes" / "openai_embeddings"

HOST = os.getenv("HOST", "0.0.0.0").strip() or "0.0.0.0"
PORT = int(os.getenv("PORT", "5002"))
RECOMMENDATION_ENGINE = os.getenv("RECOMMENDATION_ENGINE", "hybrid").strip().lower()
STRICT_EXPLICIT_GEOGRAPHY = _env_bool("STRICT_EXPLICIT_GEOGRAPHY", True)

AI_REQUIRED = _env_bool("AI_REQUIRED", True)
ALLOW_PAID_API_CALLS = _env_bool("ALLOW_PAID_API_CALLS", AI_REQUIRED)
ALLOW_PAID_EMBEDDINGS = _env_bool("ALLOW_PAID_EMBEDDINGS", AI_REQUIRED)
ALLOW_WEB_RESEARCH = _env_bool("ALLOW_WEB_RESEARCH")
ALLOW_NETWORK_PACKAGE_INSTALL = _env_bool("ALLOW_NETWORK_PACKAGE_INSTALL")

LEXICAL_TOP_K = int(os.getenv("LEXICAL_TOP_K", "300"))
SEMANTIC_TOP_K = int(os.getenv("SEMANTIC_TOP_K", "300"))
MAX_FUSED_CANDIDATES = int(os.getenv("MAX_FUSED_CANDIDATES", "500"))
SEMANTIC_HASH_DIM = int(os.getenv("SEMANTIC_HASH_DIM", "768"))
SEMANTIC_VECTOR_DIM = int(os.getenv("SEMANTIC_VECTOR_DIM", "64"))
SEMANTIC_PROVIDER = os.getenv("SEMANTIC_PROVIDER", "openai_embeddings" if AI_REQUIRED else "lsa_local").strip().lower()
SENTENCE_TRANSFORMER_MODEL = os.getenv("SENTENCE_TRANSFORMER_MODEL", "").strip()
OPENAI_EMBEDDING_MODEL = os.getenv("OPENAI_EMBEDDING_MODEL", "text-embedding-3-small").strip()
INTENT_PARSER_PROVIDER = os.getenv("INTENT_PARSER_PROVIDER", "openai" if AI_REQUIRED else "deterministic").strip().lower()
OPENAI_CHAT_MODEL = os.getenv("OPENAI_CHAT_MODEL", os.getenv("OPENAI_INTENT_MODEL", "gpt-4.1-mini")).strip()
OPENAI_INTENT_MODEL = OPENAI_CHAT_MODEL
OPENAI_INTENT_TIMEOUT_SECONDS = float(os.getenv("OPENAI_INTENT_TIMEOUT_SECONDS", "45"))
OPENAI_EMBEDDING_TIMEOUT_SECONDS = float(os.getenv("OPENAI_EMBEDDING_TIMEOUT_SECONDS", "30"))
OPENAI_EMBEDDING_BATCH_SIZE = max(1, int(os.getenv("OPENAI_EMBEDDING_BATCH_SIZE", "128")))
OPENAI_INTENT_TRANSIENT_RETRIES = min(1, max(0, int(os.getenv("OPENAI_INTENT_TRANSIENT_RETRIES", "0"))))
AI_REVIEW_TOP_RESULTS = _env_bool("AI_REVIEW_TOP_RESULTS", True)
AI_REVIEW_CANDIDATE_LIMIT = min(50, max(1, int(os.getenv("AI_REVIEW_CANDIDATE_LIMIT", "40"))))
OPENAI_REVIEW_TIMEOUT_SECONDS = float(os.getenv("OPENAI_REVIEW_TIMEOUT_SECONDS", "45"))
OPENAI_CONFIGURED = bool(os.getenv("OPENAI_API_KEY", "").strip())
LLM_INTENT_ENABLED = ALLOW_PAID_API_CALLS and INTENT_PARSER_PROVIDER == "openai"
OPENAI_EMBEDDINGS_ENABLED = ALLOW_PAID_EMBEDDINGS and SEMANTIC_PROVIDER == "openai_embeddings"

PROFILE_SCHEMA_VERSION = "2.0"
CLASSIFICATION_VERSION = "list-profile-v2"
INTENT_SCHEMA_VERSION = "campaign-intent-v2"
RELATIONSHIP_RULES_VERSION = "relationship-v2"
