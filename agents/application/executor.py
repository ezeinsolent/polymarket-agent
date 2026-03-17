import os
import json
import ast
import re
import requests
from typing import List, Dict, Any
import math
from dotenv import load_dotenv
from agents.polymarket.gamma import GammaMarketClient as Gamma
from agents.utils.objects import SimpleEvent, SimpleMarket
from agents.application.prompts import Prompter
from agents.polymarket.polymarket import Polymarket


def retain_keys(data, keys_to_retain):
    if isinstance(data, dict):
        return {
            key: retain_keys(value, keys_to_retain)
            for key, value in data.items()
            if key in keys_to_retain
        }
    elif isinstance(data, list):
        return [retain_keys(item, keys_to_retain) for item in data]
    else:
        return data


class GrokClient:
    def __init__(self):
        load_dotenv()
        self.api_key = os.getenv("XAI_API_KEY")
        self.base_url = "https://api.x.ai/v1"
        self.model = "grok-3-mini"

    def chat(self, prompt: str) -> dict:
        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {self.api_key}"
        }
        body = {
            "model": self.model,
            "messages": [
                {"role": "user", "content": prompt}
            ],
            "max_tokens": 2000,
            "temperature": 0
        }
        response = requests.post(
            f"{self.base_url}/chat/completions",
            headers=headers,
            json=body,
            timeout=60
        )
        response.raise_for_status()
        data = response.json()
        content = data["choices"][0]["message"]["content"]
        return {"content": content, "sources": []}

    def search_and_chat(self, prompt: str) -> dict:
        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {self.api_key}"
        }
        body = {
            "model": "grok-3-mini",
            "input": [
                {"role": "user", "content": prompt}
            ],
            "tools": [
                {"type": "web_search"},
                {"type": "x_search"}
            ]
        }
        try:
            response = requests.post(
                f"{self.base_url}/responses",
                headers=headers,
                json=body,
                timeout=90
            )
            response.raise_for_status()
            data = response.json()
            content = ""
            sources = []
            for item in data.get("output", []):
                if item.get("type") == "message":
                    for block in item.get("content", []):
                        if block.get("type") == "output_text":
                            content = block.get("text", "")
                if item.get("type") == "web_search_call":
                    sources.append(f"Web: {item.get('query', '')}")
                if item.get("type") == "x_search_call":
                    sources.append(f"X: {item.get('query', '')}")
            return {"content": content, "sources": sources}
        except Exception as e:
            print(f"Search API error: {e}, falling back to chat")
            return self.chat(prompt)


class Executor:
    def __init__(self) -> None:
        load_dotenv()
        self.prompter = Prompter()
        self.grok = GrokClient()
        self.gamma = Gamma()
        self.polymarket = Polymarket()

    def filter_events_with_rag(self, events: list) -> list:
        try:
            events_text = "\n".join([
                f"- ID:{e.id} | {e.title}"
                for e in events[:30]
            ])
            prompt = (
                f"{self.prompter.filter_events()}\n\n"
                f"Here are the available events:\n{events_text}\n\n"
                "Return ONLY a Python list of the 5 best event IDs.\n"
                "Example: [123, 456, 789, 101, 202]\n"
                "Return ONLY the list, nothing else."
            )
            result = self.grok.chat(prompt)
            content = result["content"].strip()
            ids = ast.literal_eval(content)
            filtered = [e for e in events if e.id in ids]
            if not filtered:
                return events[:5]
            return filtered
        except Exception as ex:
            print(f"Filter events error: {ex}")
            return events[:5]

    def map_filtered_events_to_markets(self, filtered_events: list) -> list:
        markets = []
        for e in filtered_events:
            try:
                if hasattr(e, 'markets'):
                    market_ids = e.markets.split(",")
                else:
                    data = json.loads(e[0].json())
                    market_ids = data["metadata"]["markets"].split(",")
                for market_id in market_ids:
                    if market_id.strip():
                        market_data = self.gamma.get_market(market_id.strip())
                        formatted = self.pol
