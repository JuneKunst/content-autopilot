from datetime import datetime, timedelta, timezone

from content_autopilot.processing.scorer import ScoringEngine
from content_autopilot.schemas import RawItem


def make_item(
    *,
    source: str = "hn",
    upvotes: int = 100,
    comments: int = 20,
    age_hours: float = 1.0,
    url: str = "https://example.com/post",
    external_id: str = "id-1",
) -> RawItem:
    return RawItem(
        source=source,
        title=f"Item {external_id}",
        url=url,
        engagement={"upvotes": upvotes, "comments": comments},
        collected_at=datetime.now(timezone.utc) - timedelta(hours=age_hours),
        external_id=external_id,
    )


def test_score_item_is_deterministic_for_same_signals():
    engine = ScoringEngine()
    item = make_item(age_hours=2.0)

    first = engine.score_item(item)
    second = engine.score_item(item)

    assert first.score == second.score
    assert first.breakdown == second.breakdown


def test_time_decay_penalizes_older_item():
    engine = ScoringEngine()
    recent = make_item(age_hours=1, external_id="recent")
    old = make_item(age_hours=48, external_id="old")

    recent_scored = engine.score_item(recent)
    old_scored = engine.score_item(old)

    assert recent_scored.score > old_scored.score


def test_volume_signal_rewards_higher_upvotes():
    engine = ScoringEngine()
    low = make_item(upvotes=10, comments=5, external_id="low")
    high = make_item(upvotes=500, comments=5, external_id="high")

    low_scored = engine.score_item(low)
    high_scored = engine.score_item(high)

    assert high_scored.breakdown["volume"] > low_scored.breakdown["volume"]
    assert high_scored.score > low_scored.score


def test_cross_platform_bonus_increases_score():
    engine = ScoringEngine()
    item = make_item(external_id="shared-id")

    no_bonus = engine.score_item(item, cross_platform_ids=set())
    with_bonus = engine.score_item(item, cross_platform_ids={"shared-id"})

    assert with_bonus.breakdown["cross_platform"] == 1.0
    assert no_bonus.breakdown["cross_platform"] == 0.0
    assert with_bonus.score > no_bonus.score


def test_select_top_n_returns_n_items_in_score_order():
    engine = ScoringEngine()
    items = [
        make_item(upvotes=20, comments=2, age_hours=5, external_id="a"),
        make_item(upvotes=800, comments=100, age_hours=1, external_id="b"),
        make_item(upvotes=120, comments=20, age_hours=2, external_id="c"),
        make_item(upvotes=60, comments=4, age_hours=12, external_id="d"),
    ]

    scored = engine.score_batch(items)
    top_two = engine.select_top_n(scored, n=2)

    assert len(top_two) == 2
    assert top_two[0].score >= top_two[1].score
    assert top_two[0].score >= max(item.score for item in scored[1:])


def test_ordering_recent_high_engagement_then_old_high_then_recent_low():
    engine = ScoringEngine()
    high_recent = make_item(upvotes=500, comments=80, age_hours=1, external_id="high-recent")
    high_old = make_item(upvotes=500, comments=80, age_hours=48, external_id="high-old")
    low_recent = make_item(upvotes=10, comments=1, age_hours=1, external_id="low-recent")

    scored = engine.score_batch([high_old, low_recent, high_recent])
    ordered = engine.select_top_n(scored, n=3)

    assert ordered[0].raw_item.external_id == "high-recent"
    assert ordered[1].raw_item.external_id == "high-old"
    assert ordered[2].raw_item.external_id == "low-recent"
