from application.settings import EmbedderSettings
from infrastructure.base.const.infra_const import EmbedderModel

import numpy as np
from fastembed import TextEmbedding


class Embedder:
    def __init__(self, embedder_settings: EmbedderSettings):
        self.model_name = EmbedderModel(embedder_settings.model_name)
        model_map = {
            EmbedderModel.MINILM_L12_V2: "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2",
        }
        self._model = TextEmbedding(model_name=model_map.get(self.model_name, self.model_name.value))

    def embed(self, text: str) -> list[float]:
        embedding = list(self._model.embed([f"query: {text}"]))[0]
        return embedding.tolist()
    
    def embed_passage(self, text: str) -> list[float]:
        embedding = list(self._model.embed([f"passage: {text}"]))[0]
        return embedding.tolist()

    def embed_batch(self, texts: list[str]) -> list[list[float]]:
        inputs = [f"passage: {text}" for text in texts]
        embeddings = list(self._model.embed(inputs))
        return [vector.tolist() for vector in embeddings]

    def cosine_similarity(self, embedding1: list[float], embedding2: list[float]) -> float:
        vec1 = np.array(embedding1)
        vec2 = np.array(embedding2)
        if np.linalg.norm(vec1) == 0 or np.linalg.norm(vec2) == 0:
            return 0.0
        return float(np.dot(vec1, vec2) / (np.linalg.norm(vec1) * np.linalg.norm(vec2)))

    def cosine_distance(self, embedding1: list[float], embedding2: list[float]) -> float:
        cosine_sim = self.cosine_similarity(embedding1, embedding2)
        return self.cosine_similarity_to_distance(cosine_sim)

    def cosine_to_nearest_similarity(self, item_embedding: list[float], cluster_embeddings: list[list[float]]) -> float:
        # Return nearest-cluster cosine similarity: max(sim(item, cluster_i)).
        if not cluster_embeddings:
            return 0.0

        return max(self.cosine_similarity(item_embedding, cluster_embedding) for cluster_embedding in cluster_embeddings)

    def cosine_similarity_to_distance(self, cosine_sim: float) -> float:
        # Convert cosine similarity score to distance.
        return max(0.0, min(2.0, 1.0 - float(cosine_sim)))
    