import json
from unittest.mock import patch
import pytest
from app.answers.focused import ambiguous_question, focused_config_answer
from app.answers.policy import structured_config_answer, unavailable_information_message
from app.answers.orchestration import stream_grounded_chat
from app.services.client_config_service import load_client_config
from app.schemas.chat import ChatHistoryTurn

@pytest.fixture
def config():return load_client_config('central-e-commerce-co-ltd')

@pytest.mark.parametrize('question',['How long does it take to create the campaign chatbot?','How long does it take to set up a chatbot?','كم يستغرق إنشاء شات بوت الحملة؟'])
def test_creation_time_uses_approved_conditions(config,question):
    answer=structured_config_answer(question=question,config=config).answer
    assert ('one working day' in answer and 'approval' in answer) or ('يوم عمل' in answer and 'موافقة' in answer)
    assert '150' not in answer and '200' not in answer

@pytest.mark.parametrize('question',['What is the contact email for JorMall?','ما البريد الإلكتروني للتواصل مع جورمول؟'])
def test_email_only(config,question):
    answer=structured_config_answer(question=question,config=config).answer
    assert 'info@jormall.com' in answer and len(answer.split())<10
    assert 'Fax' not in answer and '+962' not in answer

@pytest.mark.parametrize('question',['What is the email for Google?','What is your email and phone?','How long does it take to build a house?','How long does it take to create the campaign chatbot and what does it cost?'])
def test_narrow_rules_do_not_hijack_other_requests(config,question):
    assert focused_config_answer(question,config) is None

@pytest.mark.parametrize('question',['كم سعره؟','How much is it?','Price?'])
def test_ambiguous_without_context_clarifies(config,question):
    assert ambiguous_question(question)
    events=[json.loads(e) for e in stream_grounded_chat(question=question,history=[],db=None,client_slug=config.client_slug)]
    text=''.join(e.get('answer','')+e.get('text','') for e in events)
    assert '؟' in text or '?' in text
    assert '150' not in text

def test_specific_price_is_not_ambiguous():assert not ambiguous_question('كم سعر الشات بوت؟')

def test_saved_old_answer_does_not_override_focused_answer(config):
    q='What is the contact email for JorMall?'
    history=[ChatHistoryTurn(role='user',content=q),ChatHistoryTurn(role='assistant',content='Old full contact block')]
    events=[json.loads(e) for e in stream_grounded_chat(question=q,history=history,db=None,client_slug=config.client_slug)]
    text=''.join(e.get('answer','')+e.get('text','') for e in events)
    assert 'info@jormall.com' in text and 'Old full' not in text

@pytest.mark.parametrize('question',['What is your Mars delivery price?','كم سعر التوصيل إلى المريخ؟'])
def test_missing_information_is_explicit(config,question):
    answer=unavailable_information_message(question=question,company_name=config.company_name,config=config)
    assert 'do not have approved information' in answer or 'لا تتوفر لدي معلومات معتمدة' in answer

@pytest.mark.parametrize('question',['What are the chatbot hosting packages and prices?','ما أسعار باقات استضافة الشات بوت؟'])
def test_hosting_focus(config,question):
    answer=structured_config_answer(question=question,config=config).answer
    assert all(n in answer for n in ['30','75','140','200'])
    assert '150' not in answer and ('tax' in answer or 'ضريبة' in answer)
