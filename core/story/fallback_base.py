"""
core/story/fallback_base.py

Core owns the RESILIENCE MECHANISM (try generation, validate, fall
back). Core never owns fallback CONTENT -- that's entirely the
brand's responsibility, supplied through this interface. Matches the
same shape as StoryParser: core defines the contract, brand implements
it however makes sense for that brand (a hardcoded Story, a JSON file
on disk, a random pick from several pre-written stories -- core
doesn't care).
"""
from abc import ABC, abstractmethod
from .schema import Story


class FallbackProvider(ABC):
    @abstractmethod
    def get_fallback_story(self) -> Story:
        """Return a complete, valid Story to use when live generation
        fails or returns incomplete content. Must always succeed --
        this is the last line of defense, so it should not depend on
        any network call."""
        raise NotImplementedError
