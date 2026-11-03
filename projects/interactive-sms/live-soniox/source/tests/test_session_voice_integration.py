"""Isolated database tests: all fixtures roll back and the provider is mocked."""
import io
from uuid import uuid4
from unittest.mock import patch
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session
from app.main import app
from app.core.database import engine,get_db
from app.models.document import ChatbotLead
from app.conversations.store import conversation_for_session,save_assistant_message
from app.voice.protocol import read_frames
from app.voice import tts


def test_owner_message_and_tenant_binding_with_actual_database():
    prefix='/interactive-sms/api/chat/central-e-commerce-co-ltd'
    with engine.connect() as connection:
        outer=connection.begin();db=Session(bind=connection,join_transaction_mode='create_savepoint')
        app.dependency_overrides[get_db]=lambda:db
        try:
            client=TestClient(app);identities=[]
            for index in range(2):
                ids={'session_id':'contract-chat-'+uuid4().hex,'lead_session_id':'contract-lead-'+uuid4().hex}
                phone='079'+str(uuid4().int%10000000).zfill(7)
                assert db.scalar(select(ChatbotLead.id).where(ChatbotLead.normalized_phone==phone)) is None
                lead={'session_id':ids['lead_session_id'],'chat_session_id':ids['session_id'],'name':'Contract Tester','phone':phone,'cookie_notice_opened':True,'privacy_notice_opened':True}
                assert client.post(prefix+'/lead',json=lead).status_code==200
                identities.append((ids,lead))
            a,lead_a=identities[0];b,lead_b=identities[1]
            conversation=conversation_for_session(db=db,client_slug='central-e-commerce-co-ltd',session_id=a['session_id'])
            message_a=save_assistant_message(db=db,conversation=conversation,message='First immutable answer '+uuid4().hex)
            db.commit()
            message_b=save_assistant_message(db=db,conversation=conversation,message='Second immutable answer '+uuid4().hex);db.commit()
            selected=[]
            def audio(**kwargs):selected.append(kwargs['text']);yield b'\x01\x02\x03\x04'
            with patch.object(tts,'cache',tts.AudioCache()),patch.object(tts.soniox,'_stream_soniox_realtime_speech',side_effect=audio):
                valid={**a,'message_id':str(message_a.id),'language':'en-US'}
                response=client.post(prefix+'/speak',json=valid)
                assert response.status_code==200
                assert b''.join(read_frames(io.BytesIO(response.content)))==b'\x01\x02\x03\x04'
                assert selected==[message_a.content]
                assert response.headers['X-Assistant-Message-ID']==str(message_a.id)
                assert client.post(prefix+'/speak',json={**valid,'lead_session_id':b['lead_session_id']}).status_code==404
                assert client.post(prefix+'/speak',json={**valid,'message_id':str(uuid4())}).status_code==404
                assert client.post(prefix+'/speak',json={**a,'language':'en'}).status_code==422
                assert client.post(prefix+'/speak',json={**valid,'text':'Unapproved arbitrary text'}).status_code==422
                assert client.post(prefix.replace('central-e-commerce-co-ltd','other-tenant')+'/speak',json=valid).status_code==404
                assert client.post(prefix+'/stream',json={'session_id':a['session_id'],'lead_session_id':b['lead_session_id'],'message':'Hello'}).status_code==403
                assert client.post(prefix+'/lead',json={**lead_b,'chat_session_id':a['session_id']}).status_code==403
                assert selected==[message_a.content]
                # Replay A still selects A after B exists and is served from complete-only cache.
                replay=client.post(prefix+'/speak',json=valid);assert replay.status_code==200
                assert replay.headers['X-Voice-Cache']=='hit';assert len(selected)==1
            assert conversation.lead_session_id==a['lead_session_id']
        finally:
            app.dependency_overrides.clear();db.close();outer.rollback()
