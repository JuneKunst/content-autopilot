"""Content deduplication service using URL hash + title similarity."""
from dataclasses import dataclass
from difflib import SequenceMatcher
from urllib.parse import urlparse, urlunparse
import re
from content_autopilot.schemas import RawItem
from content_autopilot.common.logger import get_logger

log = get_logger("processing.dedup")


@dataclass
class DedupResult:
    is_duplicate: bool
    duplicate_of_id: str | None = None
    similarity_score: float = 0.0


class DedupService:
    def __init__(self, title_threshold: float = 0.8):
        self.title_threshold = title_threshold

    def normalize_url(self, url: str) -> str:
        """Normalize URL: lowercase scheme/host, remove www, remove trailing slash, strip common query params."""
        try:
            parsed = urlparse(url.lower().strip())
            host = parsed.netloc.replace("www.", "")
            path = parsed.path.rstrip("/")
            # Keep only meaningful query params (exclude tracking params)
            return urlunparse((parsed.scheme, host, path, "", "", ""))
        except Exception:
            return url.lower().strip()

    def check_url(self, url1: str, url2: str) -> DedupResult:
        """Check if two URLs point to the same content."""
        norm1 = self.normalize_url(url1)
        norm2 = self.normalize_url(url2)
        is_dup = norm1 == norm2
        return DedupResult(is_duplicate=is_dup, similarity_score=1.0 if is_dup else 0.0)

    def normalize_title(self, title: str) -> str:
        """Normalize title for comparison: lowercase, remove punctuation, strip."""
        return re.sub(r'[^\w\s]', '', title.lower()).strip()

    def check_title(self, title1: str, title2: str) -> DedupResult:
        """Check if two titles are similar enough to be duplicates."""
        norm1 = self.normalize_title(title1)
        norm2 = self.normalize_title(title2)
        score = SequenceMatcher(None, norm1, norm2).ratio()
        return DedupResult(
            is_duplicate=score >= self.title_threshold,
            similarity_score=score,
        )

    def find_duplicates(self, items: list[RawItem]) -> list[tuple[int, int, DedupResult]]:
        """Find all duplicate pairs in a list of items.
        Returns list of (idx1, idx2, DedupResult) for duplicates found.
        """
        duplicates = []
        url_map: dict[str, int] = {}  # normalized_url → first_seen_index

        for i, item in enumerate(items):
            norm_url = self.normalize_url(item.url)
            if norm_url in url_map:
                j = url_map[norm_url]
                result = DedupResult(is_duplicate=True, duplicate_of_id=items[j].external_id, similarity_score=1.0)
                duplicates.append((i, j, result))
                continue
            url_map[norm_url] = i

            # Title similarity check against all previous items
            for j in range(i):
                if j in [d[1] for d in duplicates]:
                    continue  # skip already-identified duplicates
                title_result = self.check_title(item.title, items[j].title)
                if title_result.is_duplicate:
                    title_result.duplicate_of_id = items[j].external_id
                    duplicates.append((i, j, title_result))
                    break

        return duplicates

    def deduplicate(self, items: list[RawItem]) -> list[RawItem]:
        """Remove duplicates from a list of items.
        When duplicates found, keep the one with higher engagement.
        """
        if not items:
            return []

        duplicates = self.find_duplicates(items)
        duplicate_indices = set()

        for i, j, result in duplicates:
            # Keep the item with higher total engagement
            eng_i = sum(items[i].engagement.values())
            eng_j = sum(items[j].engagement.values())
            if eng_i <= eng_j:
                duplicate_indices.add(i)
                log.info("dedup_removed", title=items[i].title[:50], kept=items[j].title[:50],
                         score=result.similarity_score)
            else:
                duplicate_indices.add(j)

        return [item for idx, item in enumerate(items) if idx not in duplicate_indices]
