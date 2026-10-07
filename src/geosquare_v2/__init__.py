"""Geosquare V2 profile-driven metric grid core."""

from .boundary import BoundaryPredicate, OperationalBoundary
from .codec import (
    BASE_2_MATRIX,
    BASE_5_MATRIX,
    MAX_LEVEL,
    ROOT_SIDE_M,
    SUBDIVISIONS,
    canonical_to_gid,
    gid_to_canonical,
)
from .aggregation import (
    CategoryRule,
    NumericRule,
    RangeRule,
    ValueSemantics,
    aggregate_categorical,
    aggregate_geometry_contributions,
    aggregate_geometry_table_to_cells,
    aggregate_numeric,
    aggregate_ordinal,
    aggregate_range,
    aggregate_to_cells,
)
from .batch import (
    encode_lonlat_arrow,
    encode_lonlat_numpy,
    encode_lonlat_pandas,
    encode_projected_arrow,
    encode_projected_numpy,
    encode_projected_pandas,
)
from .conversion import (
    GridCellRecord,
    cell_to_geometry,
    cells_to_geometry,
    line_to_cells,
    point_to_cell,
    polygon_to_cell,
    polygon_to_cells,
)
from .db import DbRegistryLoader, RegistryDomainSummary, list_registry_domains
from .errors import (
    CandidateLimitExceededError,
    CellDatasetError,
    CellDatasetManifestError,
    FilesystemDependencyError,
    GeosquareError,
    GeometryDependencyError,
    OutsideOperationalBoundaryError,
    TableDependencyError,
)
from .geometry import projected_cell_geometry, wgs84_cell_geometry
from .polyfill import CoverageMode, polyfill, polyfill_stream
from .grid import GeosquareGrid
from .cell_manifest import CellDatasetManifest
from .dataset import CellDataset, query_cell_dataset, read_cell_dataset, write_cell_dataset
from .manifest import RegistryLoader
from .migration import LegacyV1Cell, LegacyV1Decoder, MigrationRecord, V1MigrationAdapter
from .model import CanonicalCell, DomainProfile, ProjectedBounds
from .packing import pack_int64, unpack_int64
from .registry import DomainRegistry
from .release import ReleaseProfile
from .storage import (
    FilesystemDatasetStore,
    query_cell_dataset_filesystem,
    read_cell_dataset_filesystem,
    write_cell_dataset_filesystem,
)
from .facade import GeosquareService, IndexedCell, parse_uri
from .table import geometry_table_to_cells, read_table, table_to_cells, table_to_cells_chunks, write_table

__all__ = [
    "BoundaryPredicate",
    "OperationalBoundary",
    "BASE_2_MATRIX",
    "CategoryRule",
    "NumericRule",
    "RangeRule",
    "ValueSemantics",
    "aggregate_categorical",
    "aggregate_geometry_contributions",
    "aggregate_geometry_table_to_cells",
    "aggregate_numeric",
    "aggregate_ordinal",
    "aggregate_range",
    "aggregate_to_cells",
    "BASE_5_MATRIX",
    "CoverageMode",
    "GridCellRecord",
    "cell_to_geometry",
    "cells_to_geometry",
    "line_to_cells",
    "point_to_cell",
    "polygon_to_cell",
    "polygon_to_cells",
    "MAX_LEVEL",
    "ROOT_SIDE_M",
    "SUBDIVISIONS",
    "CanonicalCell",
    "CandidateLimitExceededError",
    "CellDataset",
    "CellDatasetError",
    "CellDatasetManifest",
    "CellDatasetManifestError",
    "DbRegistryLoader",
    "DomainProfile",
    "DomainRegistry",
    "FilesystemDatasetStore",
    "FilesystemDependencyError",
    "GeosquareError",
    "GeometryDependencyError",
    "OutsideOperationalBoundaryError",
    "TableDependencyError",
    "GeosquareService",
    "IndexedCell",
    "GeosquareGrid",
    "LegacyV1Cell",
    "LegacyV1Decoder",
    "MigrationRecord",
    "V1MigrationAdapter",
    "ProjectedBounds",
    "RegistryDomainSummary",
    "RegistryLoader",
    "ReleaseProfile",
    "list_registry_domains",
    "canonical_to_gid",
    "encode_lonlat_arrow",
    "encode_lonlat_numpy",
    "encode_lonlat_pandas",
    "encode_projected_arrow",
    "encode_projected_numpy",
    "encode_projected_pandas",
    "geometry_table_to_cells",
    "gid_to_canonical",
    "pack_int64",
    "polyfill",
    "polyfill_stream",
    "query_cell_dataset",
    "query_cell_dataset_filesystem",
    "parse_uri",
    "projected_cell_geometry",
    "read_cell_dataset",
    "read_cell_dataset_filesystem",
    "read_table",
    "table_to_cells",
    "table_to_cells_chunks",
    "unpack_int64",
    "wgs84_cell_geometry",
    "write_cell_dataset",
    "write_cell_dataset_filesystem",
    "write_table",
]

__version__ = "0.1.0rc1"
