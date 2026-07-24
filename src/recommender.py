"""Small, deterministic content-based recommendation engine."""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity


@dataclass(frozen=True)
class RecommendationModel:
    vectorizer: TfidfVectorizer
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


def fit_recommender(products: pd.DataFrame) -> RecommendationModel:
    """Fit TF-IDF vocabulary and IDF weights on the small product catalog."""
    vectorizer = TfidfVectorizer(
        ngram_range=(1, 2),
        min_df=1,
        sublinear_tf=True,
    )
    matrix = vectorizer.fit_transform(product_text(products))
    return RecommendationModel(vectorizer=vectorizer, product_matrix=matrix)


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
) -> pd.DataFrame:
    """Rank products with explicit taste, recent behavior, and recent trends."""
    behavior_product_weights = behavior_product_weights or {}
    trend_product_scores = trend_product_scores or {}
    purchased_ids = purchased_ids or set()
    favorites = products[products["id"].isin(favorite_ids)]
    interest_text = " ".join(interests * 3)
    favorite_text = " ".join(product_text(favorites).tolist())
    profile_text = f"{interest_text} {favorite_text}".strip()

    if profile_text:
        profile_vector = model.vectorizer.transform([profile_text])
        content_score = cosine_similarity(
            profile_vector,
            model.product_matrix,
        ).ravel()
    else:
        content_score = np.zeros(len(products))

    positive_behavior = {
        product_id: score
        for product_id, score in behavior_product_weights.items()
        if score > 0
    }
    behavior_parts: list[str] = []
    for product_id, weight in positive_behavior.items():
        matched = products[products["id"] == product_id]
        if matched.empty:
            continue
        repetitions = max(1, min(8, int(round(weight))))
        behavior_parts.extend(product_text(matched).tolist() * repetitions)
    if behavior_parts:
        behavior_vector = model.vectorizer.transform([" ".join(behavior_parts)])
        behavior_score = cosine_similarity(
            behavior_vector,
            model.product_matrix,
        ).ravel()
    else:
        behavior_score = np.zeros(len(products))

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

    if not interests and not favorite_ids and not positive_behavior:
        final_score = (
            0.25 * budget_score
            + 0.20 * popularity_score
            + 0.10 * rating_score
            + 0.45 * trend_score
        )
        mode = "cold_start"
    else:
        final_score = (
            0.35 * content_score
            + 0.20 * category_score
            + 0.20 * behavior_score
            + 0.10 * budget_score
            + 0.15 * trend_score
        )
        mode = "personalized"

    ranked = products.copy()
    ranked["content_score"] = content_score
    ranked["text_score"] = content_score
    ranked["category_score"] = category_score
    ranked["behavior_score"] = behavior_score
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
        ),
        axis=1,
    )
    return ranked.reset_index(drop=True)


def build_reason(
    product: pd.Series,
    interests: list[str],
    has_favorites: bool,
    has_behavior: bool = False,
) -> str:
    candidates: list[tuple[float, str]] = []
    priority_reasons: list[str] = []
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
