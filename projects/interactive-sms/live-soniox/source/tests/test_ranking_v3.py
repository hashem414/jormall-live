import json
from pathlib import Path
import pytest
from app.knowledge.retrieval import has_pipe_table_rows,RetrievedChunk,final_ranked_chunks

FIXTURE=json.loads((Path(__file__).parent/'fixtures/ranking-v3-candidates.json').read_text())

@pytest.mark.parametrize('text',[
 'Period | Price\n1 month | 30\n3 months | 75',
 '| Item | Price |\n| :--- | ---: |\n| A | 10 |\n| B | 20 |',
 'المدة | السعر\nشهر | 30\nسنة | 200',
 'Stage | Detail\nPrepare | Gather materials\nApprove | Confirm content',
])
def test_extracted_tables(text):assert has_pipe_table_rows(text)

@pytest.mark.parametrize('text',[
 'Call us | anytime', 'A | B\nC | D',
 'A | B\nordinary prose\nC | D\nE | F',
 'A | B\nC | D | E\nF | G',
 'A || B\nC || D\nE || F',
 '| --- | --- |\n| --- | --- |\n| --- | --- |',
])
def test_prose_and_malformed_rows_do_not_get_table_bonus(text):assert not has_pipe_table_rows(text)

@pytest.mark.parametrize('case',FIXTURE['cases'],ids=lambda x:x['name'])
def test_frozen_pricing_table_candidates(case):
    chunks=[RetrievedChunk(**FIXTURE['chunks'][x['id']],similarity=x['similarity']) for x in case['candidates']]
    before={c.chunk_id:c.similarity for c in chunks}
    ranked=final_ranked_chunks(chunks=chunks,question=case['question'],top_k=5,include_metadata_only=False)
    ids=[str(c.chunk_id) for c in ranked]
    assert set(case['expected'])&set(ids),{'case':case['name'],'actual':ids}
    assert len(ids)==len(set(ids))==5
    assert all(c.similarity==before[c.chunk_id] for c in ranked)
    assert all(c.client_slug=='central-e-commerce-co-ltd' for c in ranked)
    if case['name'].endswith('control'):
        assert ids==case['baseline_ids']
