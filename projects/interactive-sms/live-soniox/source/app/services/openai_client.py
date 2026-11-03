from functools import lru_cache
import time

from openai import OpenAI

from app.core.config import settings
from app.openai_usage import complete_openai_request, fail_openai_request
from app.voice.usage import begin_voice_request


class _MeteredResponseStream:
    def __init__(self, inner, handle, started):
        self._inner = inner
        self._handle = handle
        self._started = started
        self._recorded = False

    def __iter__(self):
        return iter(self._inner)

    def get_final_response(self):
        response = self._inner.get_final_response()
        if not self._recorded:
            complete_openai_request(self._handle, response, operation="chat", started=self._started)
            self._recorded = True
        return response

    def __getattr__(self, name):
        return getattr(self._inner, name)


class _MeteredStreamManager:
    def __init__(self, inner, *, model: str, input_characters: int):
        self._inner = inner
        self._model = model
        self._input_characters = input_characters
        self._stream = None

    def __enter__(self):
        started = time.perf_counter()
        handle = begin_voice_request(
            client_slug="central-e-commerce-co-ltd", provider="openai", operation="chat",
            model=self._model, language="", input_text_characters=self._input_characters,
        )
        try:
            inner_stream = self._inner.__enter__()
        except BaseException as error:
            fail_openai_request(handle, error, started=started)
            raise
        self._stream = _MeteredResponseStream(inner_stream, handle, started)
        return self._stream

    def __exit__(self, error_type, error, traceback):
        if error is not None and self._stream is not None and not self._stream._recorded:
            fail_openai_request(self._stream._handle, error, started=self._stream._started)
            self._stream._recorded = True
        return self._inner.__exit__(error_type, error, traceback)


class _MeteredResponses:
    def __init__(self, inner):
        self._inner = inner

    def stream(self, *args, **kwargs):
        model = str(kwargs.get("model") or "unknown")
        input_characters = len(str(kwargs.get("input") or "")) + len(str(kwargs.get("instructions") or ""))
        return _MeteredStreamManager(self._inner.stream(*args, **kwargs), model=model, input_characters=input_characters)

    def parse(self, *args, **kwargs):
        started = time.perf_counter()
        handle = begin_voice_request(
            client_slug="central-e-commerce-co-ltd", provider="openai", operation="chat",
            model=str(kwargs.get("model") or "unknown"), language="",
            input_text_characters=len(str(kwargs.get("input") or "")) + len(str(kwargs.get("instructions") or "")),
        )
        try:
            response = self._inner.parse(*args, **kwargs)
        except BaseException as error:
            fail_openai_request(handle, error, started=started)
            raise
        complete_openai_request(handle, response, operation="chat", started=started)
        return response

    def __getattr__(self, name):
        return getattr(self._inner, name)


class _MeteredEmbeddings:
    def __init__(self, inner):
        self._inner = inner

    def create(self, *args, **kwargs):
        started = time.perf_counter()
        inputs = kwargs.get("input") or []
        if isinstance(inputs, str):
            inputs = [inputs]
        handle = begin_voice_request(
            client_slug="central-e-commerce-co-ltd", provider="openai", operation="embedding",
            model=str(kwargs.get("model") or "unknown"), language="",
            input_text_characters=sum(len(str(item)) for item in inputs),
        )
        try:
            response = self._inner.create(*args, **kwargs)
        except BaseException as error:
            fail_openai_request(handle, error, started=started)
            raise
        complete_openai_request(handle, response, operation="embedding", started=started)
        return response

    def __getattr__(self, name):
        return getattr(self._inner, name)


class _MeteredOpenAI:
    def __init__(self, inner):
        self._inner = inner
        self.responses = _MeteredResponses(inner.responses)
        self.embeddings = _MeteredEmbeddings(inner.embeddings)

    def __getattr__(self, name):
        return getattr(self._inner, name)


@lru_cache
def get_openai_client():
    if settings.openai_api_key is None:
        raise RuntimeError(
            "OPENAI_API_KEY is missing. Add it to your local .env file."
        )

    api_key = settings.openai_api_key.get_secret_value().strip()

    if not api_key:
        raise RuntimeError(
            "OPENAI_API_KEY is empty. Add a valid key to your local .env file."
        )

    return _MeteredOpenAI(OpenAI(api_key=api_key))


def model_response_controls(*, model: str, verbosity: str) -> dict:
    """Return only request controls supported by the configured model family."""
    normalized_model = model.strip().lower()
    if normalized_model.startswith("gpt-5"):
        return {
            "reasoning": {"effort": settings.chat_reasoning_effort},
            "text": {"verbosity": verbosity},
        }
    return {}
