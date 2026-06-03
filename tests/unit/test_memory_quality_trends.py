from fleetent.intelligence import memory


def test_memory_quality_trend_public_api_is_importable() -> None:
    from fleetent.intelligence.memory import (
        MemoryQualityTrendBucket,
        MemoryQualityTrendQuery,
        MemoryQualityTrendSummary,
        get_memory_quality_trend_summary,
    )

    assert MemoryQualityTrendQuery
    assert MemoryQualityTrendBucket
    assert MemoryQualityTrendSummary
    assert callable(get_memory_quality_trend_summary)
    assert memory.MemoryQualityTrendQuery is MemoryQualityTrendQuery
