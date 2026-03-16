from abc import ABC, abstractmethod
from dataclasses import dataclass


@dataclass
class VerificationResult:
    row_index: int
    match: bool
    confidence: float
    reason: str
    suggested_domain: str | None


class BaseLLMProvider(ABC):
    @abstractmethod
    async def verify_domains(self, batch: list[dict]) -> list[VerificationResult]:
        """Each item: {row_index, company_name, location, candidate_domain, search_snippet}"""
        ...

    @property
    @abstractmethod
    def max_batch_size(self) -> int:
        ...
