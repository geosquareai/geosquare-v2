"""In-memory domain registry for the V2 reference core.

Signed manifest loading is intentionally kept outside this small deterministic core. A
production loader must verify a V2 registry manifest before constructing these profiles.
"""

from __future__ import annotations

from collections.abc import Iterable

from .errors import UnknownDomainError, ValidationError
from .model import DomainProfile


class DomainRegistry:
    """A uniqueness-enforcing collection of immutable domain profiles."""

    def __init__(self, profiles: Iterable[DomainProfile] = ()) -> None:
        self._by_code: dict[str, DomainProfile] = {}
        self._by_id: dict[int, DomainProfile] = {}
        for profile in profiles:
            self.register(profile)

    def register(self, profile: DomainProfile) -> None:
        if not isinstance(profile, DomainProfile):
            raise ValidationError("registry entries must be DomainProfile instances")
        existing_code = self._by_code.get(profile.domain_code)
        existing_id = self._by_id.get(profile.domain_id)
        if existing_code is not None:
            raise ValidationError(f"duplicate domain code: {profile.domain_code}")
        if existing_id is not None:
            raise ValidationError(f"duplicate domain id: {profile.domain_id}")
        self._by_code[profile.domain_code] = profile
        self._by_id[profile.domain_id] = profile

    @classmethod
    def from_verified_profiles(cls, profiles: Iterable[DomainProfile]) -> "DomainRegistry":
        """Construct the immutable lookup result after a loader verified all artifacts."""
        return cls(profiles)

    def get(self, domain_code: str) -> DomainProfile:
        try:
            return self._by_code[domain_code]
        except KeyError as exc:
            raise UnknownDomainError(f"unknown domain code: {domain_code!r}") from exc

    def get_by_id(self, domain_id: int) -> DomainProfile:
        try:
            return self._by_id[domain_id]
        except KeyError as exc:
            raise UnknownDomainError(f"unknown domain id: {domain_id!r}") from exc

    def __contains__(self, domain_code: object) -> bool:
        return domain_code in self._by_code

    def __len__(self) -> int:
        return len(self._by_code)

    def profiles(self) -> tuple[DomainProfile, ...]:
        return tuple(self._by_code.values())
