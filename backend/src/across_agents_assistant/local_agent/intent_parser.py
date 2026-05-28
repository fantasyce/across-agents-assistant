import json
import re
from typing import Dict, Any, Optional

class ToolIntentParser:
    """
    Parses LLM output to extract structured tool calls instead of just conversational text.
    In M4, we expect the LLM to output a JSON block like:
    ```json
    {
      "plan_summary": "I will read the browser URL",
      "tool_calls": [{"name": "get_active_browser_url", "args": {}}]
    }
    ```
    """
    @staticmethod
    def parse_intent(llm_output: str) -> Optional[Dict[str, Any]]:
        if not llm_output:
            return None

        # Find JSON blocks in the output
        json_pattern = re.compile(r'```json\s*(\{.*?\})\s*```', re.DOTALL)
        match = json_pattern.search(llm_output)

        if not match:
            # Fallback: try to find any raw JSON block if backticks are missing
            try:
                start_idx = llm_output.find("{")
                end_idx = llm_output.rfind("}")
                if start_idx != -1 and end_idx != -1 and start_idx < end_idx:
                    json_str = llm_output[start_idx:end_idx+1]
                    data = json.loads(json_str)
                    if "tool_calls" in data:
                        return data
            except:
                pass
            return None

        try:
            data = json.loads(match.group(1))
            if "tool_calls" in data:
                return data
        except json.JSONDecodeError:
            pass

        return None
