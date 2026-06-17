"""スクレイパーモジュール"""

from scrapers.base import BaseScraper
from scrapers.meti import MetiScraper, MetiGeniacScraper
from scrapers.soumu import SoumuScraper
from scrapers.mext import MextScraper
from scrapers.cabinet_office import CabinetOfficeScraper
from scrapers.jimin import JiminScraper
from scrapers.egov_pubcom import EgovPublicCommentScraper

__all__ = [
    "BaseScraper",
    "MetiScraper",
    "MetiGeniacScraper",
    "SoumuScraper",
    "MextScraper",
    "CabinetOfficeScraper",
    "JiminScraper",
    "EgovPublicCommentScraper",
]
