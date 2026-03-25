from __future__ import annotations

from pathlib import Path

import yaml

from db_mcp.benchmark.loader import load_case_pack
from db_mcp.importer.benchmark_semantics import bootstrap_semantics_from_benchmark


def _write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text)


def test_bootstrap_semantics_clusters_windowed_cases_and_grouped_dimension(tmp_path):
    connection_path = tmp_path / "connections" / "bench"
    _write_text(
        connection_path / "benchmark" / "cases.yaml",
        """
cases:
  - id: revenue_jan
    category: revenue
    prompt: >-
      What was the total invoice revenue on the Helium network during the
      31-day period ending on 2026-01-31 (USD)?
    gold_sql: |
      SELECT ROUND(SUM(total), 2) AS answer
      FROM dwh.public.invoice
      WHERE invoice_date BETWEEN DATE '2026-01-01' AND DATE '2026-01-31'
    comparison: scalar_numeric_tolerance
    tolerance: 0.01
  - id: revenue_feb
    category: revenue
    prompt: >-
      What was the total invoice revenue on the Helium network during the
      28-day period ending on 2026-02-28 (USD)?
    gold_sql: |
      SELECT ROUND(SUM(total), 2) AS answer
      FROM dwh.public.invoice
      WHERE invoice_date BETWEEN DATE '2026-02-01' AND DATE '2026-02-28'
    comparison: scalar_numeric_tolerance
    tolerance: 0.01
  - id: revenue_by_country_jan
    category: revenue
    prompt: >-
      What was the total invoice revenue by billing country on the Helium
      network during the 31-day period ending on 2026-01-31 (USD)?
    gold_sql: |
      SELECT billing_country AS billing_country, ROUND(SUM(total), 2) AS answer
      FROM dwh.public.invoice
      WHERE invoice_date BETWEEN DATE '2026-01-01' AND DATE '2026-01-31'
      GROUP BY billing_country
    comparison: rowset_unordered
""",
    )
    _write_text(
        connection_path / "instructions" / "business_rules.yaml",
        """
- rule: "Period ending on X is inclusive."
  severity: critical
- rule: "Use invoice table for revenue."
  severity: high
""",
    )
    _write_text(
        connection_path / "domain" / "model.md",
        """
# Bench Domain

- Invoice revenue is measured from invoice.total.
- Billing country is a supported grouping.
""",
    )
    _write_text(
        connection_path / "examples" / "invoice-revenue.yaml",
        """
intent: "Invoice revenue by billing country"
keywords: [invoice, revenue, billing country]
sql: |
  SELECT billing_country, SUM(total)
  FROM dwh.public.invoice
  GROUP BY billing_country
validated: true
""",
    )
    _write_text(
        connection_path / "schema" / "descriptions.yaml",
        """
version: 1.0.0
provider_id: bench
tables:
  - full_name: dwh.public.invoice
    columns:
      - name: invoice_date
        type: date
      - name: total
        type: double
      - name: billing_country
        type: varchar
""",
    )

    output_connection_path = tmp_path / "overlay" / "bench"
    report = bootstrap_semantics_from_benchmark(
        connection_path=connection_path,
        output_connection_path=output_connection_path,
        emit_mode="temp_overlay",
    )

    assert report["cases_seen"] == 3
    assert report["metrics_created"] == 1
    assert report["dimensions_created"] == 1
    assert report["unsupported_cases"] == []
    assert next(iter(report["cases_grouped"].values())) == [
        "revenue_by_country_jan",
        "revenue_feb",
        "revenue_jan",
    ]

    catalog = yaml.safe_load((output_connection_path / "metrics" / "catalog.yaml").read_text())
    assert len(catalog["metrics"]) == 1
    metric = catalog["metrics"][0]
    assert metric["status"] == "approved"
    assert metric["dimensions"] == ["billing_country"]
    assert {param["name"] for param in metric["parameters"]} == {"start_date", "end_date"}

    dimensions = yaml.safe_load(
        (output_connection_path / "metrics" / "dimensions.yaml").read_text()
    )
    assert dimensions["dimensions"][0]["name"] == "billing_country"
    assert dimensions["dimensions"][0]["column"] == "billing_country"

    bindings = yaml.safe_load((output_connection_path / "metrics" / "bindings.yaml").read_text())
    binding = next(iter(bindings["bindings"].values()))
    assert "{start_date}" in binding["sql"]
    assert "{end_date}" in binding["sql"]
    assert binding["dimensions"]["billing_country"]["projection_sql"] == "billing_country"

    semantic_cases = load_case_pack(output_connection_path, case_pack="cases_semantic.yaml")
    jan_case = next(case for case in semantic_cases if case.id == "revenue_jan")
    feb_case = next(case for case in semantic_cases if case.id == "revenue_feb")
    grouped_case = next(case for case in semantic_cases if case.id == "revenue_by_country_jan")
    assert jan_case.answer_intent_options == {
        "time_context": {"start": "2026-01-01", "end": "2026-02-01"}
    }
    assert feb_case.answer_intent_options == {
        "time_context": {"start": "2026-02-01", "end": "2026-03-01"}
    }
    assert grouped_case.answer_intent_options == {
        "time_context": {"start": "2026-01-01", "end": "2026-02-01"}
    }


def test_bootstrap_semantics_uses_commented_reference_query_for_import(tmp_path):
    connection_path = tmp_path / "connections" / "bench"
    _write_text(
        connection_path / "benchmark" / "cases.yaml",
        """
cases:
  - id: dau_peak
    category: usage
    prompt: >-
      What was the highest daily DAU ever recorded on the Helium network
      before or on 2026-03-01?
    gold_sql: |
      -- Reference query from source material:
      -- SELECT
      --   MAX(day_dau) AS answer
      -- FROM (
      --   SELECT
      --     date,
      --     SUM(wifi_sub_count) AS day_dau
      --   FROM dwh.public.daily_stats_cdrs
      --   WHERE date <= DATE '2026-03-01'
      --   GROUP BY date
      -- ) t
      SELECT CAST(3374132 AS BIGINT) AS answer
    comparison: scalar_exact
""",
    )
    _write_text(connection_path / "instructions" / "business_rules.yaml", "[]\n")
    _write_text(connection_path / "domain" / "model.md", "# Bench Domain\n")
    _write_text(connection_path / "schema" / "descriptions.yaml", "version: 1.0.0\n")

    output_connection_path = tmp_path / "overlay" / "bench"
    report = bootstrap_semantics_from_benchmark(
        connection_path=connection_path,
        output_connection_path=output_connection_path,
        emit_mode="temp_overlay",
    )

    assert report["metrics_created"] == 1
    bindings = yaml.safe_load((output_connection_path / "metrics" / "bindings.yaml").read_text())
    binding = next(iter(bindings["bindings"].values()))
    assert "MAX(day_dau)" in binding["sql"]
    assert "{end_date}" in binding["sql"]

    semantic_cases = load_case_pack(output_connection_path, case_pack="cases_semantic.yaml")
    assert semantic_cases[0].answer_intent_options == {"time_context": {"end": "2026-03-02"}}
