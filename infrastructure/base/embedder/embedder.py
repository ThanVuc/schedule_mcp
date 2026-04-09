
from application.settings import EmbedderSettings
from infrastructure.base.const.infra_const import EmbedderModel

from sentence_transformers import SentenceTransformer
from huggingface_hub import configure_http_backend
import requests


class _TimeoutSession(requests.Session):
    def __init__(self, timeout_seconds: float):
        super().__init__()
        self._timeout_seconds = timeout_seconds

    def request(self, method, url, **kwargs):
        kwargs.setdefault("timeout", self._timeout_seconds)
        return super().request(method, url, **kwargs)


class Embedder:
    def __init__(self, embedder_settings: EmbedderSettings):
        timeout_seconds = float(embedder_settings.download_timeout_seconds)
        configure_http_backend(
            backend_factory=lambda: _TimeoutSession(timeout_seconds=timeout_seconds)
        )
        self.model_name = EmbedderModel(embedder_settings.model_name)
        self._model = SentenceTransformer(self.model_name.value)

    def embed(self, text: str) -> list[float]:
        embedding = self._model.encode(text, convert_to_numpy=True)
        return embedding.tolist()

    def embed_batch(self, texts: list[str]) -> list[list[float]]:
        embeddings = self._model.encode(texts, convert_to_numpy=True)
        return embeddings.tolist()
    
    def cosine_similarity(self, embedding1: list[float], embedding2: list[float]) -> float:
        import numpy as np
        vec1 = np.array(embedding1)
        vec2 = np.array(embedding2)
        if np.linalg.norm(vec1) == 0 or np.linalg.norm(vec2) == 0:
            return 0.0
        return float(np.dot(vec1, vec2) / (np.linalg.norm(vec1) * np.linalg.norm(vec2)))
