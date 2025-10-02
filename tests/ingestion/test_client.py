"""Tests for arXiv OAI-PMH client."""

from __future__ import annotations

from unittest.mock import Mock, patch

import pytest

from papersys.ingestion.client import ArxivOAIClient, ArxivRecord


@pytest.fixture
def oai_client() -> ArxivOAIClient:
    """Create OAI client for testing."""
    return ArxivOAIClient(max_retries=1, retry_delay=0.1)


def test_parse_record_valid(oai_client: ArxivOAIClient) -> None:
    """Test parsing a valid OAI record."""
    xml = """
    <record xmlns="http://www.openarchives.org/OAI/2.0/"
            xmlns:arxiv="http://arxiv.org/OAI/arXiv/">
        <header>
            <identifier>oai:arXiv.org:2301.00001</identifier>
            <datestamp>2023-01-01</datestamp>
        </header>
        <metadata>
            <arxiv:arXiv>
                <arxiv:id>2301.00001</arxiv:id>
                <arxiv:title>Test Paper Title</arxiv:title>
                <arxiv:abstract>This is a test abstract.</arxiv:abstract>
                <arxiv:categories>cs.AI cs.CL</arxiv:categories>
                <arxiv:authors>
                    <arxiv:author>
                        <arxiv:keyname>Doe</arxiv:keyname>
                        <arxiv:forenames>John</arxiv:forenames>
                    </arxiv:author>
                    <arxiv:author>
                        <arxiv:keyname>Smith</arxiv:keyname>
                        <arxiv:forenames>Jane</arxiv:forenames>
                    </arxiv:author>
                </arxiv:authors>
                <arxiv:created>2023-01-01</arxiv:created>
                <arxiv:updated>2023-01-02</arxiv:updated>
                <arxiv:doi>10.1234/test.2023</arxiv:doi>
                <arxiv:comments>5 pages</arxiv:comments>
            </arxiv:arXiv>
        </metadata>
    </record>
    """
    from xml.etree import ElementTree as ET

    record_elem = ET.fromstring(xml)
    result = oai_client._parse_record(record_elem)

    assert result is not None
    assert result.paper_id == "2301.00001"
    assert result.title == "Test Paper Title"
    assert result.abstract == "This is a test abstract."
    assert result.categories == ["cs.AI", "cs.CL"]
    assert result.primary_category == "cs.AI"
    assert result.authors == ["John Doe", "Jane Smith"]
    assert result.published_at == "2023-01-01"
    assert result.updated_at == "2023-01-02"
    assert result.doi == "10.1234/test.2023"
    assert result.comment == "5 pages"


def test_parse_record_deleted(oai_client: ArxivOAIClient) -> None:
    """Test that deleted records return None."""
    xml = """
    <record xmlns="http://www.openarchives.org/OAI/2.0/"
            xmlns:arxiv="http://arxiv.org/OAI/arXiv/">
        <header status="deleted">
            <identifier>oai:arXiv.org:2301.00001</identifier>
            <datestamp>2023-01-01</datestamp>
        </header>
    </record>
    """
    from xml.etree import ElementTree as ET

    record_elem = ET.fromstring(xml)
    result = oai_client._parse_record(record_elem)

    assert result is None


def test_parse_record_missing_metadata(oai_client: ArxivOAIClient) -> None:
    """Test that records without metadata return None."""
    xml = """
    <record xmlns="http://www.openarchives.org/OAI/2.0/">
        <header>
            <identifier>oai:arXiv.org:2301.00001</identifier>
        </header>
    </record>
    """
    from xml.etree import ElementTree as ET

    record_elem = ET.fromstring(xml)
    result = oai_client._parse_record(record_elem)

    assert result is None


@patch("papersys.ingestion.client.requests.Session.get")
def test_list_records_with_resumption(mock_get: Mock, oai_client: ArxivOAIClient) -> None:
    """Test list_records with resumption token."""
    # First response with resumption token
    response1 = Mock()
    response1.text = """<?xml version="1.0" encoding="UTF-8"?>
    <OAI-PMH xmlns="http://www.openarchives.org/OAI/2.0/"
             xmlns:arxiv="http://arxiv.org/OAI/arXiv/">
        <ListRecords>
            <record>
                <header>
                    <identifier>oai:arXiv.org:2301.00001</identifier>
                </header>
                <metadata>
                    <arxiv:arXiv>
                        <arxiv:id>2301.00001</arxiv:id>
                        <arxiv:title>First Paper</arxiv:title>
                        <arxiv:abstract>First abstract</arxiv:abstract>
                        <arxiv:categories>cs.AI</arxiv:categories>
                        <arxiv:authors>
                            <arxiv:author>
                                <arxiv:keyname>Doe</arxiv:keyname>
                                <arxiv:forenames>John</arxiv:forenames>
                            </arxiv:author>
                        </arxiv:authors>
                        <arxiv:created>2023-01-01</arxiv:created>
                        <arxiv:updated>2023-01-01</arxiv:updated>
                    </arxiv:arXiv>
                </metadata>
            </record>
            <resumptionToken>token123</resumptionToken>
        </ListRecords>
    </OAI-PMH>
    """
    response1.raise_for_status = Mock()

    # Second response without resumption token
    response2 = Mock()
    response2.text = """<?xml version="1.0" encoding="UTF-8"?>
    <OAI-PMH xmlns="http://www.openarchives.org/OAI/2.0/"
             xmlns:arxiv="http://arxiv.org/OAI/arXiv/">
        <ListRecords>
            <record>
                <header>
                    <identifier>oai:arXiv.org:2301.00002</identifier>
                </header>
                <metadata>
                    <arxiv:arXiv>
                        <arxiv:id>2301.00002</arxiv:id>
                        <arxiv:title>Second Paper</arxiv:title>
                        <arxiv:abstract>Second abstract</arxiv:abstract>
                        <arxiv:categories>cs.CL</arxiv:categories>
                        <arxiv:authors>
                            <arxiv:author>
                                <arxiv:keyname>Smith</arxiv:keyname>
                                <arxiv:forenames>Jane</arxiv:forenames>
                            </arxiv:author>
                        </arxiv:authors>
                        <arxiv:created>2023-01-02</arxiv:created>
                        <arxiv:updated>2023-01-02</arxiv:updated>
                    </arxiv:arXiv>
                </metadata>
            </record>
        </ListRecords>
    </OAI-PMH>
    """
    response2.raise_for_status = Mock()

    mock_get.side_effect = [response1, response2]

    records = list(oai_client.list_records(from_date="2023-01-01"))

    assert len(records) == 2
    assert records[0].paper_id == "2301.00001"
    assert records[0].title == "First Paper"
    assert records[1].paper_id == "2301.00002"
    assert records[1].title == "Second Paper"

    # Verify API calls
    assert mock_get.call_count == 2
