from tests.evaluation.memory_quality_trend_eval import load_fixture, run_fixture


def test_memory_quality_trend_fixture_covers_duplicate_expiry_and_shared_separation(
    tmp_path, monkeypatch
) -> None:
    fixture = load_fixture()

    summary = run_fixture(fixture, tmp_path, monkeypatch)

    bucket = summary.buckets[0]
    assert bucket.user_memory_counts == fixture["expected"]["user_memory_counts"]
    assert bucket.shared_memory_counts == fixture["expected"]["shared_memory_counts"]
    assert bucket.expired_context_count == fixture["expected"]["expired_context_count"]
    assert bucket.duplicate_candidate_count == fixture["expected"]["duplicate_candidate_count"]
