def test_reflection_trend_summary_public_api_is_importable():
    from fleetent.intelligence.reflection import (
        ReflectionTrendBucket,
        ReflectionTrendQuery,
        ReflectionTrendSummary,
        get_reflection_trend_summary,
    )

    assert ReflectionTrendQuery is not None
    assert ReflectionTrendBucket is not None
    assert ReflectionTrendSummary is not None
    assert callable(get_reflection_trend_summary)
