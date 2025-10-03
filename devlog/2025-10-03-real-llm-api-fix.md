# Real LLM API Testing Fix - 2025-10-03
Status: Completed
Last-updated: 2025-10-03

## Problem
Initially, LLM client code was trying to manually set `base_url` and `custom_llm_provider` for Gemini models, which caused API routing failures. The error messages showed:
1. First attempt: `UnsupportedParamsError: google_ai_studio does not support parameters: ['reasoning_effort']`
2. Second attempt: `404 Not Found` due to double slashes in URL (`/openai//models/`)

## Root Cause
**Misunderstanding of LiteLLM's routing mechanism**: LiteLLM uses the `provider/model_name` format (e.g., `gemini/gemini-2.5-flash`) to automatically route requests to the correct endpoint. Manual `base_url` and `custom_llm_provider` settings were interfering with this auto-routing.

## Solution
1. **Config change** (`config/example.toml`):
   - Changed `name` from `"gemini-2.5-flash"` to `"gemini/gemini-2.5-flash"`
   - Set `base_url = ""` (empty string to let LiteLLM handle routing)
   - Kept `reasoning_effort = "high"` as-is

2. **Code simplification** (`papersys/summary/generator.py`):
   - Removed complex provider detection logic for Gemini
   - Simplified to: only set `api_base` if it's non-empty
   - Removed `custom_llm_provider` setting completely (LiteLLM infers from model prefix)
   - Kept `reasoning_effort` parameter (now works correctly)

3. **Test updates** (`tests/summary/test_generator_detection.py`):
   - Updated test to verify NO `custom_llm_provider` is set for Gemini
   - Verified `reasoning_effort` parameter is correctly passed

4. **Real API test** (`scripts/test_real_gemini_api.py`):
   - Created standalone test script for real API verification
   - Successfully validated against live Google AI Studio API
   - Confirmed `reasoning_effort` parameter works

## Verification
✅ Real API call succeeded with `reasoning_effort='high'`
✅ All 13 summary tests pass
✅ Config correctly uses LiteLLM's auto-routing

## Key Takeaways
1. **Trust LiteLLM's routing**: The `provider/model` format is the primary way to specify endpoints
2. **Don't override unless necessary**: Manual `base_url` and `custom_llm_provider` should only be used for custom endpoints
3. **Test with real APIs**: Mock tests alone can hide integration issues

## Files Modified
- `config/example.toml` - Updated Gemini config to use auto-routing
- `papersys/summary/generator.py` - Simplified provider logic
- `tests/summary/test_generator_detection.py` - Updated test expectations
- `scripts/test_real_gemini_api.py` - New real API test script
