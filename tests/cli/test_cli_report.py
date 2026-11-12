from scraper_cli.cli import _format_duration, _report
from scraper_cli.runner import RunResult


def test_duration_format_is_readable_for_short_and_long_runs():
    assert _format_duration(8.125) == "8.12s"
    assert _format_duration(65.25) == "1m 05.25s"
    assert _format_duration(3_723.5) == "1h 02m 03.50s"


def test_report_includes_total_elapsed_time(capsys):
    result = RunResult(rows=[{"id": 1}], attempted=1, succeeded=1)

    _report(result, ["reviews.csv"], verbose=False, elapsed_seconds=65.25)

    assert capsys.readouterr().err == (
        "Resumen: intentadas=1 exitosas=1 fallidas=0 registros=1 "
        "salidas=reviews.csv duración=1m 05.25s código=0\n"
    )
