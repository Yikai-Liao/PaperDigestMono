#!/usr/bin/env python3
"""Test real Google AI Studio API call with reasoning_effort parameter."""

import os
import sys
from pathlib import Path

# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from papersys.config.llm import LLMConfig
from papersys.summary.generator import SummaryGenerator, SummarySource
from loguru import logger


def main():
    # Check API key
    api_key = os.environ.get("GEMINI_API_KEY")
    if not api_key:
        logger.error("GEMINI_API_KEY environment variable not set")
        sys.exit(1)
    
    logger.info("GEMINI_API_KEY found: {}...", api_key[:10])
    
    # Create LLM config matching example.toml
    llm_config = LLMConfig(
        alias="gemini-2.5-flash",
        name="gemini/gemini-2.5-flash",
        base_url="",  # LiteLLM auto-routes via model prefix
        api_key=f"env:GEMINI_API_KEY",
        temperature=0.1,
        top_p=0.8,
        num_workers=10,
        reasoning_effort="high",
    )
    
    logger.info("LLM config created: alias={}, name={}, base_url={}", 
                llm_config.alias, llm_config.name, llm_config.base_url)
    logger.info("Reasoning effort: {}", llm_config.reasoning_effort)
    
    # Create test source
    test_source = SummarySource(
        paper_id="test-123",
        title="A Simple Test Paper",
        abstract="This is a test abstract to verify that the API call works correctly with reasoning_effort parameter.",
    )
    
    logger.info("Creating SummaryGenerator...")
    generator = SummaryGenerator(llm_config, default_language="en", allow_latex=False)
    
    logger.info("Calling real API with reasoning_effort='{}'...", llm_config.reasoning_effort)
    
    try:
        document = generator.generate(test_source)
        logger.success("✓ API call succeeded!")
        logger.info("Generated sections: {}", list(document.sections.keys()))
        logger.info("Highlights preview: {}", document.sections.get("Highlights", "")[:200])
        logger.info("Summary preview: {}", document.sections.get("Detailed Summary", "")[:200])
        return 0
    except Exception as e:
        logger.error("✗ API call failed: {}", e)
        import traceback
        traceback.print_exc()
        return 1


if __name__ == "__main__":
    sys.exit(main())
