"""Generate projected-coordinate warehouse encoders from verified V2 profiles.

These UDFs intentionally do not transform longitude/latitude. Transform data to the
profile's verified grid CRS before calling them, and use ``x_idx``/``y_idx`` rather
than lexicographic GID ranges for spatial windows.
"""

from __future__ import annotations

from .errors import ValidationError
from .release import ReleaseProfile


def _require_profile(profile: ReleaseProfile) -> ReleaseProfile:
    if not isinstance(profile, ReleaseProfile):
        raise ValidationError("warehouse UDF generation requires a verified ReleaseProfile")
    return profile


def _names(profile: ReleaseProfile) -> tuple[str, str]:
    code = profile.domain_code.lower()
    return f"geosquare_v2_{code}_encode_projected", f"GEOSQUARE_V2_{profile.domain_code}_ENCODE_PROJECTED"


def _javascript_body(profile: ReleaseProfile) -> str:
    # Decimal conversion avoids unsafe JavaScript Number use for the signed Int64 value.
    return f"""
var DIVISIONS = [5, 2, 5, 2, 5, 2, 5, 2, 5, 2, 5, 2, 5, 2];
var BASE5 = '23456789CEFGHJLMNPQRTVWXY';
var BASE2 = '2345';
var ORIGIN_X = {profile.origin_x_m!r};
var ORIGIN_Y = {profile.origin_y_m!r};
var ROOT_SIDE = {profile.root_side_m!r};
var DOMAIN_ID = {profile.domain_id};
function bits(value, width) {{
  var output = '';
  for (var bit = width - 1; bit >= 0; bit--) output += ((value / Math.pow(2, bit)) % 2 >= 1) ? '1' : '0';
  return output;
}}
function decimalFromBits(bitString) {{
  var digits = [0];
  for (var p = 0; p < bitString.length; p++) {{
    var carry = bitString.charAt(p) === '1' ? 1 : 0;
    for (var q = digits.length - 1; q >= 0; q--) {{
      var n = digits[q] * 2 + carry; digits[q] = n % 10; carry = Math.floor(n / 10);
    }}
    if (carry) digits.unshift(carry);
  }}
  return digits.join('');
}}
function encode(x, y, level) {{
  if (!Number.isFinite(x) || !Number.isFinite(y) || !Number.isInteger(level) || level < 0 || level > 14) return null;
  if (x < ORIGIN_X || x > ORIGIN_X + ROOT_SIDE || y < ORIGIN_Y || y > ORIGIN_Y + ROOT_SIDE) return null;
  var count = 1;
  for (var i = 0; i < level; i++) count *= DIVISIONS[i];
  var side = ROOT_SIDE / count;
  var xi = level === 0 ? 0 : (x === ORIGIN_X + ROOT_SIDE ? count - 1 : Math.floor((x - ORIGIN_X) / side));
  var yi = level === 0 ? 0 : (y === ORIGIN_Y + ROOT_SIDE ? count - 1 : Math.floor((y - ORIGIN_Y) / side));
  var workX = xi, workY = yi, reverse = [], gidReverse = [];
  for (var j = level - 1; j >= 0; j--) {{
    var step = DIVISIONS[j], column = workX % step, row = workY % step, code = row * step + column;
    reverse.push(bits(code, step === 5 ? 5 : 2));
    gidReverse.push((step === 5 ? BASE5 : BASE2).charAt(code));
    workX = Math.floor(workX / step); workY = Math.floor(workY / step);
  }}
  var pathBits = reverse.reverse().join('');
  var packed = decimalFromBits(bits(DOMAIN_ID, 9) + bits(level, 4) + pathBits + Array(51 - pathBits.length).join('0'));
  return {{gid: gidReverse.reverse().join(''), x_idx: xi, y_idx: yi, packed_id: packed}};
}}
return encode(X, Y, LEVEL);
""".strip()


def render_bigquery_projected_encoder(profile: ReleaseProfile, *, routine: str | None = None) -> str:
    """Render a BigQuery JavaScript UDF for coordinates already in the grid CRS."""
    profile = _require_profile(profile)
    default_name, _ = _names(profile)
    name = routine or default_name
    return f"""-- Generated from verified profile {profile.domain_code} {profile.profile_version}.
-- X/Y are metres in {profile.crs_authority}; this routine performs no CRS transform.
-- packed_id is STRING because JavaScript Number cannot safely represent all V2 Int64 values.
CREATE OR REPLACE FUNCTION `{name}`(X FLOAT64, Y FLOAT64, LEVEL INT64)
RETURNS STRUCT<gid STRING, x_idx INT64, y_idx INT64, packed_id STRING>
LANGUAGE js AS r'''{_javascript_body(profile)}''';
"""


def render_snowflake_projected_encoder(profile: ReleaseProfile, *, routine: str | None = None) -> str:
    """Render a Snowflake JavaScript UDF returning a VARIANT object."""
    profile = _require_profile(profile)
    _, default_name = _names(profile)
    name = routine or default_name
    body = _javascript_body(profile).replace("return encode(X, Y, LEVEL);", "return encode(X, Y, LEVEL);")
    return f"""-- Generated from verified profile {profile.domain_code} {profile.profile_version}.
-- X/Y are metres in {profile.crs_authority}; this routine performs no CRS transform.
CREATE OR REPLACE FUNCTION {name}(X FLOAT, Y FLOAT, LEVEL INTEGER)
RETURNS VARIANT
LANGUAGE JAVASCRIPT
AS $$
{body}
$$;
"""


def render_postgis_projected_encoder(profile: ReleaseProfile, *, routine: str | None = None) -> str:
    """Render a PostGIS/PostgreSQL PL/pgSQL UDF with a native BIGINT packed ID."""
    profile = _require_profile(profile)
    default_name, _ = _names(profile)
    name = routine or default_name
    return f"""-- Generated from verified profile {profile.domain_code} {profile.profile_version}.
-- X/Y are metres in {profile.crs_authority}; this routine performs no CRS transform.
CREATE OR REPLACE FUNCTION {name}(x double precision, y double precision, level integer)
RETURNS TABLE(gid text, x_idx bigint, y_idx bigint, packed_id bigint)
LANGUAGE plpgsql IMMUTABLE STRICT AS $$
DECLARE
  divisions integer[] := ARRAY[5,2,5,2,5,2,5,2,5,2,5,2,5,2];
  base5 text := '23456789CEFGHJLMNPQRTVWXY'; base2 text := '2345';
  count bigint := 1; side double precision; remaining bigint; step integer;
  i integer; column_index bigint; row_index bigint; code bigint; path bigint := 0;
BEGIN
  IF level < 0 OR level > 14 OR x < {profile.origin_x_m} OR x > {profile.origin_x_m + profile.root_side_m} OR y < {profile.origin_y_m} OR y > {profile.origin_y_m + profile.root_side_m} THEN RETURN; END IF;
  FOR i IN 1..level LOOP count := count * divisions[i]; END LOOP;
  side := {profile.root_side_m} / count;
  x_idx := CASE WHEN level = 0 THEN 0 WHEN x = {profile.origin_x_m + profile.root_side_m} THEN count - 1 ELSE floor((x - {profile.origin_x_m}) / side)::bigint END;
  y_idx := CASE WHEN level = 0 THEN 0 WHEN y = {profile.origin_y_m + profile.root_side_m} THEN count - 1 ELSE floor((y - {profile.origin_y_m}) / side)::bigint END;
  remaining := count; gid := '';
  FOR i IN 1..level LOOP
    step := divisions[i]; remaining := remaining / step;
    column_index := (x_idx / remaining) % step; row_index := (y_idx / remaining) % step; code := row_index * step + column_index;
    gid := gid || substr(CASE WHEN step = 5 THEN base5 ELSE base2 END, code + 1, 1);
    path := (path << CASE WHEN step = 5 THEN 5 ELSE 2 END) | code;
  END LOOP;
  packed_id := ({profile.domain_id}::bigint << 54) | (level::bigint << 50) | (path << 1);
  RETURN NEXT;
END;
$$;
"""
