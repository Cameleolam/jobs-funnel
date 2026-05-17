from ui.services.calibration_presenter import proposal_summary_lines


def test_summary_explains_false_positive_evidence():
    proposal = {
        "metrics": {
            "proposal": {
                "evidence": {"false_positives": 8, "false_negatives": 0},
                "guards": {"projected_review_jobs": 12, "projected_review_cap": 20.0},
            }
        },
        "rationale": {"weights": "increased dismissal weights based on false positive evidence"},
    }

    lines = proposal_summary_lines(proposal)

    assert "You dismissed 8 high-scored jobs." in lines
    assert "Projected review volume stays at 12 of 20.0 allowed jobs." in lines


def test_summary_explains_false_negative_evidence():
    proposal = {
        "metrics": {
            "proposal": {
                "evidence": {"false_positives": 0, "false_negatives": 4},
                "guards": {"projected_review_jobs": 9, "projected_review_cap": 15.0},
            }
        },
        "rationale": {"review_band": "lowered review_low by 1 because false negatives reached threshold"},
    }

    lines = proposal_summary_lines(proposal)

    assert "You pursued 4 low-scored jobs." in lines
    assert "The proposal widens review toward lower scores." in lines


def test_summary_handles_missing_metrics():
    assert proposal_summary_lines({"metrics": {}}) == ["Not enough stored proposal metrics to explain this row."]
