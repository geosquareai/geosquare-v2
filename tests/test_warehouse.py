from __future__ import annotations

from geosquare_v2.warehouse import (
    render_bigquery_projected_encoder,
    render_postgis_projected_encoder,
    render_snowflake_projected_encoder,
)


def test_generated_udfs_are_profile_specific_and_projected_only(profile):
    bigquery = render_bigquery_projected_encoder(profile)
    snowflake = render_snowflake_projected_encoder(profile)
    postgis = render_postgis_projected_encoder(profile)

    for source in (bigquery, snowflake, postgis):
        assert "EPSG:3857" in source
        assert "performs no CRS transform" in source
        assert "lexicographic GID ranges" not in source
        assert "DOMAIN_ID = 7" in source or "7::bigint << 54" in source

    assert "RETURNS STRUCT<gid STRING, x_idx INT64, y_idx INT64, packed_id STRING>" in bigquery
    assert "decimalFromBits" in bigquery
    assert "RETURNS VARIANT" in snowflake
    assert "RETURNS TABLE(gid text, x_idx bigint, y_idx bigint, packed_id bigint)" in postgis
    assert "path := (path <<" in postgis
