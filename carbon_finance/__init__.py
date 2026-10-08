"""Core engines for the Carbon Transition Intelligence demo."""

__all__ = ["CarbonFinancePipeline"]


def __getattr__(name: str):
    if name == "CarbonFinancePipeline":
        from .pipeline import CarbonFinancePipeline

        return CarbonFinancePipeline
    raise AttributeError(name)
