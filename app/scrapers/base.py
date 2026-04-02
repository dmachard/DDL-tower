from abc import ABC, abstractmethod
from typing import List, AsyncGenerator

class BaseScraper(ABC):
    @property
    @abstractmethod
    def name(self) -> str:
        pass

    @abstractmethod
    async def run(self, session = None) -> AsyncGenerator[List[str], None]:
        """
        Run the scraper and YIELD batches of RAW download links (URLs) as they are found.
        Processing (AllDebrid, DB, Parsing) is handled by the Scheduler in real-time.
        """
        yield []
