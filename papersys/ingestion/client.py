"""arXiv OAI-PMH client for fetching metadata."""

from __future__ import annotations

import time
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Iterator
from xml.etree import ElementTree as ET

import requests
from loguru import logger


@dataclass(frozen=True)
class ArxivRecord:
    """Parsed arXiv paper metadata from OAI-PMH response."""

    paper_id: str
    title: str
    abstract: str
    categories: list[str]
    primary_category: str
    authors: list[str]
    published_at: str
    updated_at: str
    doi: str | None = None
    comment: str | None = None
    journal_ref: str | None = None
    license: str | None = None


class ArxivOAIClient:
    """Client for interacting with arXiv OAI-PMH API."""

    NAMESPACES = {
        "oai": "http://www.openarchives.org/OAI/2.0/",
        "arxiv": "http://arxiv.org/OAI/arXiv/",
    }

    def __init__(
        self,
        base_url: str = "http://export.arxiv.org/oai2",
        metadata_prefix: str = "arXiv",
        max_retries: int = 3,
        retry_delay: float = 5.0,
    ):
        self.base_url = base_url
        self.metadata_prefix = metadata_prefix
        self.max_retries = max_retries
        self.retry_delay = retry_delay
        self.session = requests.Session()
        self.session.headers.update({"User-Agent": "PaperDigestMono/0.1"})

    def list_records(
        self,
        from_date: str | None = None,
        until_date: str | None = None,
        set_spec: str | None = None,
    ) -> Iterator[ArxivRecord]:
        """
        Fetch records from arXiv OAI-PMH endpoint with resumption token support.

        Args:
            from_date: Start date in YYYY-MM-DD format (optional)
            until_date: End date in YYYY-MM-DD format (optional)
            set_spec: OAI set specification (optional)

        Yields:
            ArxivRecord objects parsed from OAI responses
        """
        params: dict[str, str] = {
            "verb": "ListRecords",
            "metadataPrefix": self.metadata_prefix,
        }
        if from_date:
            params["from"] = from_date
        if until_date:
            params["until"] = until_date
        if set_spec:
            params["set"] = set_spec

        resumption_token: str | None = None
        total_records = 0

        while True:
            if resumption_token:
                params = {"verb": "ListRecords", "resumptionToken": resumption_token}

            response = self._make_request(params)
            if response is None:
                logger.error("Failed to fetch records after retries; stopping iteration")
                break

            try:
                root = ET.fromstring(response.text)
            except ET.ParseError as exc:
                logger.error("Failed to parse OAI-PMH XML response: {}", exc)
                break

            # Extract records
            records = root.findall(".//oai:record", self.NAMESPACES)
            for record_elem in records:
                try:
                    parsed = self._parse_record(record_elem)
                    if parsed:
                        yield parsed
                        total_records += 1
                except Exception as exc:
                    logger.warning("Failed to parse record: {}", exc)
                    continue

            # Check for resumption token
            token_elem = root.find(".//oai:resumptionToken", self.NAMESPACES)
            if token_elem is not None and token_elem.text:
                resumption_token = token_elem.text.strip()
                logger.debug(
                    "Resumption token found; fetched {} records so far",
                    total_records,
                )
            else:
                logger.info("No more resumption tokens; fetched {} records total", total_records)
                break

    def _make_request(self, params: dict[str, str]) -> requests.Response | None:
        """Make HTTP request with retries."""
        for attempt in range(1, self.max_retries + 1):
            try:
                response = self.session.get(self.base_url, params=params, timeout=30)
                response.raise_for_status()
                return response
            except requests.RequestException as exc:
                logger.warning(
                    "Request failed (attempt {}/{}): {}",
                    attempt,
                    self.max_retries,
                    exc,
                )
                if attempt < self.max_retries:
                    time.sleep(self.retry_delay)
                else:
                    logger.error("Max retries reached; request failed")
                    return None
        return None

    def _parse_record(self, record_elem: ET.Element) -> ArxivRecord | None:
        """Parse a single OAI record element into ArxivRecord."""
        # Check if record is deleted
        header = record_elem.find("oai:header", self.NAMESPACES)
        if header is not None and header.get("status") == "deleted":
            return None

        metadata = record_elem.find(".//arxiv:arXiv", self.NAMESPACES)
        if metadata is None:
            return None

        # Extract identifier
        identifier = metadata.findtext("arxiv:id", namespaces=self.NAMESPACES)
        if not identifier:
            return None

        # Extract fields
        title = metadata.findtext("arxiv:title", namespaces=self.NAMESPACES, default="").strip()
        abstract = metadata.findtext("arxiv:abstract", namespaces=self.NAMESPACES, default="").strip()

        # Parse categories
        categories_elem = metadata.find("arxiv:categories", self.NAMESPACES)
        categories = categories_elem.text.split() if categories_elem is not None and categories_elem.text else []

        primary_category = categories[0] if categories else ""

        # Parse authors
        authors_elems = metadata.findall("arxiv:authors/arxiv:author", self.NAMESPACES)
        authors = []
        for author_elem in authors_elems:
            keyname = author_elem.findtext("arxiv:keyname", namespaces=self.NAMESPACES, default="")
            forenames = author_elem.findtext("arxiv:forenames", namespaces=self.NAMESPACES, default="")
            full_name = f"{forenames} {keyname}".strip()
            if full_name:
                authors.append(full_name)

        # Parse dates
        created = metadata.findtext("arxiv:created", namespaces=self.NAMESPACES, default="")
        updated = metadata.findtext("arxiv:updated", namespaces=self.NAMESPACES, default="")

        # Optional fields
        doi = metadata.findtext("arxiv:doi", namespaces=self.NAMESPACES)
        comment = metadata.findtext("arxiv:comments", namespaces=self.NAMESPACES)
        journal_ref = metadata.findtext("arxiv:journal-ref", namespaces=self.NAMESPACES)
        license_elem = metadata.find("arxiv:license", self.NAMESPACES)
        license_value: str | None = None
        if license_elem is not None:
            text_value = (license_elem.text or "").strip()
            if text_value:
                license_value = text_value
            else:
                license_value = license_elem.get("uri")

        return ArxivRecord(
            paper_id=identifier,
            title=title,
            abstract=abstract,
            categories=categories,
            primary_category=primary_category,
            authors=authors,
            published_at=created,
            updated_at=updated,
            doi=doi,
            comment=comment,
            journal_ref=journal_ref,
            license=license_value,
        )


__all__ = ["ArxivOAIClient", "ArxivRecord"]
