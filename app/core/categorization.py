from typing import List, Optional
from sqlalchemy.ext.asyncio import AsyncSession
from app.db.database import AsyncSessionLocal
from app.db.models import DownloadLink
from app.services.parser_service import parser_service
from app.services.enrichment_service import enrichment_service
from app.services.maintenance_service import maintenance_service

class Categorizer:
    @staticmethod
    def _clean_network_name(name: str) -> str:
        """[DEPRECATED] Use ParserService.clean_network_name"""
        return parser_service.clean_network_name(name)

    @staticmethod
    def _extract_v_quality(filename: str) -> Optional[str]:
        """[DEPRECATED] Use ParserService.extract_v_quality"""
        return parser_service.extract_v_quality(filename)

    @staticmethod
    def _clean_search_title(title: str) -> str:
        """[DEPRECATED] Use ParserService.clean_search_title"""
        return parser_service.clean_search_title(title)

    @staticmethod
    async def enrich_links(session: AsyncSession, links: List[DownloadLink] = None, force_year: int = None, force_type: str = None, force_imdb_id: str = None):
        """
        Orchestrates filename parsing and TMDb enrichment.
        """
        if links is None:
            from sqlalchemy import select
            stmt = select(DownloadLink).where(DownloadLink.title == None, DownloadLink.filename != None)
            q = await session.execute(stmt)
            processed_links = q.scalars().all()
        else:
            processed_links = links
            
        if not processed_links:
            return

        await enrichment_service.process_batch(session, processed_links, force_year, force_type, force_imdb_id)

    @staticmethod
    async def repair_metadata(session: AsyncSession):
        """[DEPRECATED] Use maintenance_service.repair_media_metadata"""
        await maintenance_service.repair_media_metadata()

    @staticmethod
    async def repair_links_metadata(session: AsyncSession):
        """[DEPRECATED] Use maintenance_service.repair_links_tech_metadata"""
        await maintenance_service.repair_links_tech_metadata()

    @staticmethod
    async def repair_links_metadata_v2():
        """New method for global repair without passing session (uses AsyncSessionLocal)"""
        await maintenance_service.repair_links_tech_metadata()
