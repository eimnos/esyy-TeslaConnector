from src.grid_confirmation_session import GridInference, PhaseSummary, infer_grid_sign_mode


def _phase(
    name: str,
    *,
    app_direction: str,
    avg_grid_raw_w: float | None,
) -> PhaseSummary:
    return PhaseSummary(
        phase=name,
        app_direction=app_direction,
        app_grid_power_w=None,
        phase_note="",
        sample_count=12,
        ok_count=12 if avg_grid_raw_w is not None else 0,
        error_count=0 if avg_grid_raw_w is not None else 12,
        avg_pv_power_w=3000.0 if avg_grid_raw_w is not None else None,
        avg_grid_raw_w=avg_grid_raw_w,
        avg_raw_sign="negative" if (avg_grid_raw_w or 0) < 0 else "positive",
    )


def test_infer_import_positive_confirmed() -> None:
    summaries = [
        _phase("baseline", app_direction="export", avg_grid_raw_w=-420.0),
        _phase("load_on", app_direction="import", avg_grid_raw_w=680.0),
    ]

    result = infer_grid_sign_mode(summaries, tolerance_w=120.0)

    assert isinstance(result, GridInference)
    assert result.status == "confirmed"
    assert result.recommended_sign_mode == "import_positive"
    assert result.import_positive_score == 2
    assert result.export_positive_score == 0


def test_infer_export_positive_confirmed() -> None:
    summaries = [
        _phase("baseline", app_direction="export", avg_grid_raw_w=520.0),
        _phase("load_on", app_direction="import", avg_grid_raw_w=-740.0),
    ]

    result = infer_grid_sign_mode(summaries, tolerance_w=120.0)

    assert result.status == "confirmed"
    assert result.recommended_sign_mode == "export_positive"
    assert result.export_positive_score == 2
    assert result.import_positive_score == 0


def test_infer_partial_when_no_evidence() -> None:
    summaries = [
        _phase("baseline", app_direction="unknown", avg_grid_raw_w=-300.0),
        _phase("load_on", app_direction="balanced", avg_grid_raw_w=10.0),
    ]

    result = infer_grid_sign_mode(summaries, tolerance_w=120.0)

    assert result.status == "partial"
    assert result.recommended_sign_mode == "unknown"
    assert result.used_evidence_count == 0


def test_infer_partial_when_scores_conflict() -> None:
    summaries = [
        _phase("baseline", app_direction="export", avg_grid_raw_w=-600.0),
        _phase("load_on", app_direction="export", avg_grid_raw_w=700.0),
    ]

    result = infer_grid_sign_mode(summaries, tolerance_w=120.0)

    assert result.status == "partial"
    assert result.recommended_sign_mode == "unknown"
    assert result.import_positive_score == result.export_positive_score
