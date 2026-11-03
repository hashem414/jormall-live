import re
from uuid import UUID
from pydantic import BaseModel,ConfigDict,Field,field_validator


def normalize_language(value, *, allow_auto=False):
    if allow_auto and isinstance(value,str) and value.strip().lower()=='auto':
        return 'auto'
    if not isinstance(value,str) or not re.fullmatch(r'(en|ar)(?:-[a-z0-9]{2,8})*',value,re.I):
        suffix=' or auto' if allow_auto else ''
        raise ValueError(f'Voice language must be en/en-* or ar/ar-*{suffix}.')
    return value.split('-')[0].lower()


class SpeechRequest(BaseModel):
    model_config=ConfigDict(extra='forbid')
    session_id: str=Field(min_length=1,max_length=120)
    lead_session_id: str=Field(min_length=1,max_length=120)
    message_id: UUID
    language: str='auto'

    @field_validator('language')
    @classmethod
    def language_value(cls,value):return normalize_language(value,allow_auto=True)

    @field_validator('session_id','lead_session_id')
    @classmethod
    def session_value(cls,value):
        if not value.strip():raise ValueError('Session ID is required.')
        return value.strip()
