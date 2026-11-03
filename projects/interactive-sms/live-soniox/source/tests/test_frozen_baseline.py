import hashlib,json
from pathlib import Path
from app.core.config import settings

ROOT=Path(__file__).resolve().parents[1]

def test_frozen_retrieval_and_authorized_answer_revision():
    baseline=json.loads((ROOT/'docs/baselines/shared-code-sha256.json').read_text())
    revision=json.loads((ROOT/'docs/baselines/answer-quality-v2.json').read_text())['source_sha256']
    assert set(revision)=={'app/answers/policy.py','app/answers/orchestration.py','app/answers/focused.py'}
    ranking=json.loads((ROOT/'docs/baselines/ranking-v3.json').read_text())['source_sha256']
    assert set(ranking)=={'app/knowledge/retrieval.py'}
    for name,expected in {**baseline,**revision,**ranking}.items():
        assert hashlib.sha256((ROOT/name).read_bytes()).hexdigest()==expected,name

def test_runtime_models_and_retrieval_settings_match_baseline():
    baseline=json.loads((ROOT/'docs/baselines/soniox-v1.json').read_text())['runtime']
    for name,expected in baseline.items():assert getattr(settings,name)==expected,name

def test_installed_dependencies_match_lock():
    from importlib.metadata import version
    for line in (ROOT/'requirements.lock').read_text().splitlines():
        if line.strip() and not line.startswith('#'):
            package,expected=line.split('==',1)
            assert version(package)==expected,package
