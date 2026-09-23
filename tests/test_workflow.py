"""GitHub Actions の定時起動が誤って無効化されないための回帰テスト。"""

from pathlib import Path


WORKFLOW = Path(__file__).parents[1] / ".github" / "workflows" / "daily.yml"


def test_daily_workflow_has_fallback_schedule():
    text = WORKFLOW.read_text(encoding="utf-8")

    assert 'cron: "30 21 * * *"' in text
    assert 'cron: "30 8 * * *"' in text


def test_scheduled_fallback_deduplicates_external_trigger():
    text = WORKFLOW.read_text(encoding="utf-8")

    assert "listWorkflowRuns" in text
    assert "event: 'repository_dispatch'" in text
    assert "needs.preflight.outputs.should_run == 'true'" in text
