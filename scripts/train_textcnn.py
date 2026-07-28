"""Train the compact TextCNN artifact used by the storefront.

The model learns product semantics from the catalog's category labels. Runtime
inference only needs NumPy; no PyTorch/TensorFlow server dependency is needed.
"""

from __future__ import annotations

import argparse
from collections import Counter
import json
from pathlib import Path
import sys

import numpy as np


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src.catalog import load_products  # noqa: E402
from src.cnn_encoder import normalize_text  # noqa: E402
from src.recommender import product_text  # noqa: E402


def build_vocabulary(texts: list[str]) -> list[str]:
    counts = Counter(character for text in texts for character in text)
    characters = sorted(counts, key=lambda item: (-counts[item], item))
    return ["<unk>"] + characters


def train(
    texts: list[str],
    labels: np.ndarray,
    category_count: int,
    epochs: int = 350,
    seed: int = 42,
) -> tuple[list[str], dict[str, np.ndarray], list[float]]:
    rng = np.random.default_rng(seed)
    vocabulary = build_vocabulary(texts)
    token_to_id = {token: index for index, token in enumerate(vocabulary)}
    max_length = min(220, max(len(text) for text in texts))
    kernel_sizes = (2, 3, 4)
    embedding_size = 24
    filters = 16

    def token_ids(text: str) -> np.ndarray:
        tokens = list(text[:max_length])
        if len(tokens) < max(kernel_sizes):
            tokens.extend([" "] * (max(kernel_sizes) - len(tokens)))
        return np.asarray(
            [token_to_id.get(token, 0) for token in tokens],
            dtype=np.int64,
        )

    sequences = [token_ids(text) for text in texts]
    parameters: dict[str, np.ndarray] = {
        "embedding": rng.normal(
            0,
            0.12,
            (len(vocabulary), embedding_size),
        ).astype(np.float32),
        "output_weight": rng.normal(
            0,
            0.10,
            (filters * len(kernel_sizes), category_count),
        ).astype(np.float32),
        "output_bias": np.zeros(category_count, dtype=np.float32),
    }
    for size in kernel_sizes:
        parameters[f"conv_weight_{size}"] = rng.normal(
            0,
            0.10,
            (filters, size, embedding_size),
        ).astype(np.float32)
        parameters[f"conv_bias_{size}"] = np.zeros(
            filters,
            dtype=np.float32,
        )

    first_moment = {
        name: np.zeros_like(value) for name, value in parameters.items()
    }
    second_moment = {
        name: np.zeros_like(value) for name, value in parameters.items()
    }
    losses: list[float] = []
    step = 0

    for epoch in range(epochs):
        gradients = {
            name: np.zeros_like(value) for name, value in parameters.items()
        }
        epoch_loss = 0.0
        correct = 0
        for sequence, label in zip(sequences, labels, strict=True):
            embedded = parameters["embedding"][sequence]
            pooled_parts: list[np.ndarray] = []
            caches: dict[int, tuple[np.ndarray, np.ndarray, np.ndarray]] = {}
            for size in kernel_sizes:
                windows = np.lib.stride_tricks.sliding_window_view(
                    embedded,
                    (size, embedding_size),
                )[:, 0]
                activations = np.einsum(
                    "pkd,fkd->pf",
                    windows,
                    parameters[f"conv_weight_{size}"],
                    optimize=True,
                )
                activations += parameters[f"conv_bias_{size}"]
                positive = np.maximum(activations, 0.0)
                maxima = positive.argmax(axis=0)
                pooled_parts.append(positive[maxima, np.arange(filters)])
                caches[size] = (windows, activations, maxima)

            pooled = np.concatenate(pooled_parts)
            logits = pooled @ parameters["output_weight"]
            logits += parameters["output_bias"]
            shifted = logits - logits.max()
            probabilities = np.exp(shifted)
            probabilities /= probabilities.sum()
            epoch_loss -= float(np.log(probabilities[label] + 1e-9))
            correct += int(probabilities.argmax() == label)

            grad_logits = probabilities
            grad_logits[label] -= 1.0
            gradients["output_weight"] += np.outer(pooled, grad_logits)
            gradients["output_bias"] += grad_logits
            grad_pooled = parameters["output_weight"] @ grad_logits
            grad_embedded = np.zeros_like(embedded)

            offset = 0
            for size in kernel_sizes:
                windows, activations, maxima = caches[size]
                grad_part = grad_pooled[offset:offset + filters]
                offset += filters
                for filter_index, position in enumerate(maxima):
                    if activations[position, filter_index] <= 0:
                        continue
                    gradient = grad_part[filter_index]
                    gradients[f"conv_weight_{size}"][filter_index] += (
                        gradient * windows[position]
                    )
                    gradients[f"conv_bias_{size}"][filter_index] += gradient
                    grad_embedded[position:position + size] += (
                        gradient
                        * parameters[f"conv_weight_{size}"][filter_index]
                    )
            np.add.at(gradients["embedding"], sequence, grad_embedded)

        batch_size = float(len(sequences))
        learning_rate = 0.012 * (0.35 + 0.65 * (1 - epoch / epochs))
        step += 1
        for name, parameter in parameters.items():
            gradient = gradients[name] / batch_size
            if "bias" not in name:
                gradient += 0.0002 * parameter
            first_moment[name] = (
                0.9 * first_moment[name] + 0.1 * gradient
            )
            second_moment[name] = (
                0.999 * second_moment[name] + 0.001 * gradient * gradient
            )
            corrected_first = first_moment[name] / (1 - 0.9**step)
            corrected_second = second_moment[name] / (1 - 0.999**step)
            parameter -= (
                learning_rate
                * corrected_first
                / (np.sqrt(corrected_second) + 1e-8)
            )
        losses.append(epoch_loss / batch_size)
        if epoch % 50 == 0 or epoch == epochs - 1:
            print(
                f"epoch={epoch + 1:03d} "
                f"loss={losses[-1]:.4f} accuracy={correct / batch_size:.3f}"
            )

    parameters["kernel_sizes"] = np.asarray(kernel_sizes, dtype=np.int16)
    parameters["max_length"] = np.asarray([max_length], dtype=np.int16)
    parameters["unknown_index"] = np.asarray([0], dtype=np.int16)
    return vocabulary, parameters, losses


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--epochs", type=int, default=120)
    parser.add_argument(
        "--output",
        type=Path,
        default=ROOT / "data" / "textcnn_model.npz",
    )
    args = parser.parse_args()

    products = load_products(ROOT / "data" / "products.csv")
    product_texts = [
        normalize_text(text) for text in product_text(products).tolist()
    ]
    product_ids = products["id"].astype(str).tolist()
    product_to_class = {
        product_id: index for index, product_id in enumerate(product_ids)
    }
    product_labels = list(range(len(product_ids)))
    intent_seeds = json.loads(
        (ROOT / "data" / "recommendation_intent_seeds.json").read_text(
            encoding="utf-8"
        )
    )
    intent_texts: list[str] = []
    intent_labels: list[int] = []
    for product_id, queries in intent_seeds.items():
        class_index = product_to_class.get(product_id)
        if class_index is None:
            continue
        for query in queries:
            intent_texts.append(normalize_text(query))
            intent_labels.append(class_index)
    texts = product_texts * 2 + intent_texts
    labels = np.asarray(product_labels * 2 + intent_labels, dtype=np.int64)
    print(
        f"training_samples={len(texts)} "
        f"catalog={len(product_texts) * 2} intents={len(intent_texts)}"
    )
    vocabulary, parameters, _ = train(
        texts,
        labels,
        len(product_ids),
        epochs=args.epochs,
    )
    artifact = {
        "vocabulary": np.asarray(vocabulary),
        "product_classes": np.asarray(product_ids),
        **parameters,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    np.savez_compressed(args.output, **artifact)
    print(f"saved={args.output} size={args.output.stat().st_size:,} bytes")


if __name__ == "__main__":
    main()
