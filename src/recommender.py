"""Personalized TextCNN recommendation engine."""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd

from src.cnn_encoder import TextCnnEncoder


@dataclass(frozen=True)
class RecommendationModel:
    backend: str
    encoder: object | None
    product_matrix: object


def product_text(frame: pd.DataFrame) -> pd.Series:
    text = (
        frame["name"].fillna("")
        + " "
        + frame["category"].fillna("")
        + " "
        + frame["category"].fillna("")
        + " "
        + frame["description"].fillna("")
    )
    if "tags" in frame:
        text = text + " " + frame["tags"].fillna("")
    if "brand" in frame:
        text = text + " " + frame["brand"].fillna("")
    return text


def fit_recommender(
    products: pd.DataFrame,
    backend: str = "cnn",
) -> RecommendationModel:
    """Load the trained TextCNN and encode the current product catalog."""
    if backend != "cnn":
        raise ValueError(f"지원하지 않는 추천 백엔드입니다: {backend}")
    encoder = TextCnnEncoder()
    matrix = encoder.encode(
        product_text(products).tolist(),
        normalize_embeddings=True,
        convert_to_numpy=True,
        show_progress_bar=False,
    )
    return RecommendationModel(
        backend=backend,
        encoder=encoder,
        product_matrix=matrix,
    )


def _normalized_matrix_similarity(
    model: RecommendationModel,
    vector: np.ndarray,
) -> np.ndarray:
    raw_scores = np.asarray(model.product_matrix @ vector).ravel()
    minimum = float(raw_scores.min())
    maximum = float(raw_scores.max())
    if maximum == minimum:
        return np.ones(len(raw_scores))
    return (raw_scores - minimum) / (maximum - minimum)


def _cnn_profile_similarity(
    products: pd.DataFrame,
    model: RecommendationModel,
    interests: list[str],
    favorite_ids: set[str],
    query_text: str,
) -> np.ndarray:
    """Build a user vector from cached CNN product embeddings.

    Category and favorite signals already point at catalog products, so encoding
    their text again on every Streamlit rerun only adds CPU latency. Arbitrary
    search text goes through the same CNN encoder once.
    """
    matrix = np.asarray(model.product_matrix)
    vector_parts: list[np.ndarray] = []
    vector_weights: list[float] = []

    for interest in interests:
        indices = np.flatnonzero(
            products["category"].astype(str).to_numpy() == str(interest)
        )
        if len(indices):
            vector_parts.append(matrix[indices].mean(axis=0))
            vector_weights.append(3.0)

    favorite_indices = np.flatnonzero(
        products["id"].astype(str).isin(favorite_ids).to_numpy()
    )
    for index in favorite_indices:
        vector_parts.append(matrix[index])
        vector_weights.append(1.0)

    known_profile_score = np.zeros(len(products))
    if vector_parts:
        profile_vector = np.average(
            np.stack(vector_parts),
            axis=0,
            weights=np.asarray(vector_weights),
        )
        norm = float(np.linalg.norm(profile_vector))
        if norm:
            profile_vector = profile_vector / norm
        known_profile_score = _normalized_matrix_similarity(
            model,
            profile_vector,
        )

    if not query_text.strip():
        return known_profile_score
    query_probabilities = model.encoder.predict_product_scores(
        [query_text.strip()]
    )[0]
    class_scores = dict(
        zip(model.encoder.product_classes, query_probabilities, strict=True)
    )
    query_score = np.asarray(
        [class_scores.get(str(product_id), 0.0) for product_id in products["id"]]
    )
    minimum = float(query_score.min())
    maximum = float(query_score.max())
    if maximum > minimum:
        query_score = (query_score - minimum) / (maximum - minimum)
    if not vector_parts:
        return query_score
    return 0.35 * known_profile_score + 0.65 * query_score


def _cnn_behavior_similarity(
    products: pd.DataFrame,
    model: RecommendationModel,
    positive_behavior: dict[str, float],
) -> np.ndarray:
    matrix = np.asarray(model.product_matrix)
    product_positions = {
        str(product_id): index
        for index, product_id in enumerate(products["id"].tolist())
    }
    indices: list[int] = []
    weights: list[float] = []
    for product_id, weight in positive_behavior.items():
        if product_id not in product_positions:
            continue
        indices.append(product_positions[product_id])
        weights.append(max(1.0, min(8.0, float(weight))))
    if not indices:
        return np.zeros(len(products))
    behavior_vector = np.average(
        matrix[indices],
        axis=0,
        weights=np.asarray(weights),
    )
    norm = float(np.linalg.norm(behavior_vector))
    if norm:
        behavior_vector = behavior_vector / norm
    return _normalized_matrix_similarity(model, behavior_vector)


def _normalize(values: pd.Series) -> np.ndarray:
    minimum = float(values.min())
    maximum = float(values.max())
    if maximum == minimum:
        return np.ones(len(values))
    return ((values.astype(float) - minimum) / (maximum - minimum)).to_numpy()


def recommend(
    products: pd.DataFrame,
    model: RecommendationModel,
    interests: list[str],
    favorite_ids: set[str],
    budget_min: int,
    budget_max: int,
    top_n: int = 8,
    behavior_product_weights: dict[str, float] | None = None,
    trend_product_scores: dict[str, float] | None = None,
    purchased_ids: set[str] | None = None,
    query_text: str = "",
) -> pd.DataFrame:
    """Retrieve CNN candidates, then rank them with commerce signals."""
    behavior_product_weights = behavior_product_weights or {}
    trend_product_scores = trend_product_scores or {}
    purchased_ids = purchased_ids or set()
    content_score = _cnn_profile_similarity(
        products,
        model,
        interests,
        favorite_ids,
        query_text,
    )

    positive_behavior = {
        product_id: score
        for product_id, score in behavior_product_weights.items()
        if score > 0
    }
    negative_behavior = {
        product_id: score
        for product_id, score in behavior_product_weights.items()
        if score < 0
    }
    behavior_score = _cnn_behavior_similarity(
        products,
        model,
        positive_behavior,
    )
    has_content_signal = bool(
        query_text.strip() or interests or favorite_ids
    )
    has_behavior_signal = bool(positive_behavior)
    if has_content_signal and has_behavior_signal:
        retrieval_score = 0.60 * content_score + 0.40 * behavior_score
    elif has_content_signal:
        retrieval_score = content_score
    elif has_behavior_signal:
        retrieval_score = behavior_score
    else:
        retrieval_score = np.zeros(len(products))
    negative_behavior_score = np.array(
        [
            min(1.0, abs(float(negative_behavior.get(product_id, 0))) / 5.0)
            for product_id in products["id"]
        ]
    )

    category_score = products["category"].isin(interests).astype(float).to_numpy()
    prices = products["price"].astype(float).to_numpy()
    budget_score = np.where(
        (prices >= budget_min) & (prices <= budget_max),
        1.0,
        np.where(
            (prices >= budget_min * 0.9) & (prices <= budget_max * 1.1),
            0.5,
            0.0,
        ),
    )
    popularity_score = _normalize(products["popularity"])
    rating_score = (products["rating"].astype(float) / 5.0).clip(0, 1).to_numpy()
    trend_score = np.array(
        [float(trend_product_scores.get(product_id, 0)) for product_id in products["id"]]
    )
    if not trend_product_scores:
        trend_score = popularity_score
    if not has_content_signal and not has_behavior_signal:
        retrieval_score = 0.55 * trend_score + 0.45 * popularity_score

    if (
        not query_text.strip()
        and not interests
        and not favorite_ids
        and not behavior_product_weights
    ):
        final_score = (
            0.25 * budget_score
            + 0.25 * popularity_score
            + 0.15 * rating_score
            + 0.35 * trend_score
        )
        mode = "cold_start"
    else:
        final_score = (
            0.30 * content_score
            + 0.20 * category_score
            + 0.20 * behavior_score
            + 0.10 * budget_score
            + 0.10 * trend_score
            + 0.10 * rating_score
            - 0.15 * negative_behavior_score
        )
        final_score = np.clip(final_score, 0.0, 1.0)
        mode = "personalized"

    ranked = products.copy()
    ranked["content_score"] = content_score
    ranked["text_score"] = content_score
    ranked["retrieval_score"] = retrieval_score
    ranked["category_score"] = category_score
    ranked["behavior_score"] = behavior_score
    ranked["negative_behavior_score"] = negative_behavior_score
    ranked["budget_score"] = budget_score
    ranked["popularity_score"] = popularity_score
    ranked["trend_score"] = trend_score
    ranked["rating_score"] = rating_score
    ranked["recommendation_score"] = final_score
    ranked["recommendation_mode"] = mode
    excluded = set(favorite_ids) | set(purchased_ids)
    ranked = ranked[~ranked["id"].isin(excluded)]
    if "stock" in ranked:
        ranked = ranked[ranked["stock"] > 0]
    candidate_size = min(len(ranked), max(top_n, 20))
    ranked = ranked.sort_values(
        ["retrieval_score", "popularity"],
        ascending=False,
    ).head(candidate_size)
    ranked = ranked.sort_values(
        ["recommendation_score", "popularity"],
        ascending=False,
    )

    selected_indices: list[int] = []
    category_counts: dict[str, int] = {}
    for index, row in ranked.iterrows():
        category = str(row["category"])
        if category_counts.get(category, 0) >= 4:
            continue
        selected_indices.append(index)
        category_counts[category] = category_counts.get(category, 0) + 1
        if len(selected_indices) >= top_n:
            break
    ranked = ranked.loc[selected_indices]
    ranked["recommendation_reason"] = ranked.apply(
        lambda row: build_reason(
            row,
            interests,
            bool(favorite_ids),
            bool(positive_behavior),
            bool(query_text.strip()),
        ),
        axis=1,
    )
    return ranked.reset_index(drop=True)


def build_reason(
    product: pd.Series,
    interests: list[str],
    has_favorites: bool,
    has_behavior: bool = False,
    has_query: bool = False,
) -> str:
    candidates: list[tuple[float, str]] = []
    priority_reasons: list[str] = []
    if has_query and float(product["content_score"]) > 0:
        priority_reasons.append("입력한 쇼핑 의도와 의미가 유사합니다")
    if product["category"] in interests:
        candidates.append(
            (float(product["category_score"]) * 0.20, f"관심 카테고리인 {product['category']} 상품입니다")
        )
    if has_favorites and float(product["content_score"]) > 0:
        priority_reasons.append("찜한 상품과 이름·설명이 유사합니다")
    if has_behavior and float(product["behavior_score"]) >= 0.05:
        priority_reasons.append("최근 클릭·장바구니 상품과 특징이 유사합니다")
    if float(product["budget_score"]) == 1.0:
        candidates.append((0.10, "설정한 예산 범위에 포함됩니다"))
    if float(product["trend_score"]) >= 0.6:
        candidates.append(
            (float(product["trend_score"]) * 0.15, "최근 사용자들의 관심이 높은 상품입니다")
        )
    candidates.sort(key=lambda item: item[0], reverse=True)
    reasons = priority_reasons[:1]
    reasons.extend(
        reason
        for _, reason in candidates
        if reason not in reasons
    )
    reasons = reasons[:2]
    if not reasons:
        reasons.append("인기도와 평점이 안정적인 탐색 추천 상품입니다")
    return " · ".join(reasons)
