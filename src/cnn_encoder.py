"""Small NumPy TextCNN encoder used by the production recommender."""

from __future__ import annotations

from pathlib import Path
import re

import numpy as np


DEFAULT_MODEL_PATH = (
    Path(__file__).resolve().parents[1] / "data" / "textcnn_model.npz"
)


def normalize_text(text: str) -> str:
    return re.sub(r"\s+", " ", str(text).casefold()).strip()


class TextCnnEncoder:
    """Run a trained character TextCNN without a heavyweight ML runtime."""

    def __init__(self, model_path: str | Path = DEFAULT_MODEL_PATH) -> None:
        artifact = np.load(Path(model_path), allow_pickle=False)
        self.vocabulary = {
            token: index
            for index, token in enumerate(artifact["vocabulary"].tolist())
        }
        self.unknown_index = int(artifact["unknown_index"][0])
        self.max_length = int(artifact["max_length"][0])
        self.embedding = artifact["embedding"].astype(np.float32)
        self.kernel_sizes = tuple(
            int(value) for value in artifact["kernel_sizes"].tolist()
        )
        self.conv_weights = {
            size: artifact[f"conv_weight_{size}"].astype(np.float32)
            for size in self.kernel_sizes
        }
        self.conv_biases = {
            size: artifact[f"conv_bias_{size}"].astype(np.float32)
            for size in self.kernel_sizes
        }

    def _token_ids(self, text: str) -> np.ndarray:
        normalized = normalize_text(text)
        tokens = list(normalized[: self.max_length])
        minimum_length = max(self.kernel_sizes)
        if len(tokens) < minimum_length:
            tokens.extend([" "] * (minimum_length - len(tokens)))
        return np.asarray(
            [
                self.vocabulary.get(token, self.unknown_index)
                for token in tokens
            ],
            dtype=np.int64,
        )

    def _encode_one(self, text: str) -> np.ndarray:
        embedded = self.embedding[self._token_ids(text)]
        pooled_parts: list[np.ndarray] = []
        for size in self.kernel_sizes:
            windows = np.lib.stride_tricks.sliding_window_view(
                embedded,
                (size, embedded.shape[1]),
            )[:, 0]
            activations = np.einsum(
                "pkd,fkd->pf",
                windows,
                self.conv_weights[size],
                optimize=True,
            )
            activations += self.conv_biases[size]
            pooled_parts.append(np.maximum(activations, 0.0).max(axis=0))
        vector = np.concatenate(pooled_parts).astype(np.float32)
        norm = float(np.linalg.norm(vector))
        return vector / norm if norm else vector

    def encode(
        self,
        texts: list[str],
        normalize_embeddings: bool = True,
        convert_to_numpy: bool = True,
        show_progress_bar: bool = False,
    ) -> np.ndarray:
        del normalize_embeddings, convert_to_numpy, show_progress_bar
        return np.stack([self._encode_one(text) for text in texts])
