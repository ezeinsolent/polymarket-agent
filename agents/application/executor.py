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
                        formatted = self.polymarket.map_api_to_market(market_data)
                        markets.append(formatted)
            except Exception as ex:
                print(f"Market mapping error: {ex}")
                continue
        return markets

    def filter_markets(self, markets: list) -> list:
        try:
            markets_text = "\n".join([
                f"- INDEX:{i} | {m.get('question', str(m)[:60]) if isinstance(m, dict) else (m.question if hasattr(m, 'question') else str(m)[:60])}"
                for i, m in enumerate(markets[:20])
            ])
            prompt = (
                f"{self.prompter.filter_markets()}\n\n"
                f"Here are the available markets:\n{markets_text}\n\n"
                "Return ONLY a Python list with the index numbers of the 3 best markets.\n"
                "Example: [0, 2, 5]\n"
                "Return ONLY the list, nothing else."
            )
            result = self.grok.chat(prompt)
            content = result["content"].strip()
            indices = ast.literal_eval(content)
            filtered = [markets[i] for i in indices if i < len(markets)]
            if not filtered:
                return markets[:3]
            return filtered
        except Exception as ex:
            print(f"Filter markets error: {ex}")
            return markets[:3]

    def source_best_trade(self, market_object) -> dict:
        try:
            if isinstance(market_object, dict):
                question = market_object.get('question', 'Unknown')
                description = market_object.get('description', question)
                outcome_prices = market_object.get('outcome_prices', '[0.5, 0.5]')
                outcomes = market_object.get('outcomes', "['Yes', 'No']")
            elif hasattr(market_object, 'question'):
                question = market_object.question
                description = getattr(market_object, 'description', question)
                outcome_prices = getattr(market_object, 'outcome_prices', '[0.5, 0.5]')
                outcomes = getattr(market_object, 'outcomes', "['Yes', 'No']")
            else:
                market_document = market_object[0].dict()
                market = market_document["metadata"]
                outcome_prices = market["outcome_prices"]
                outcomes = market["outcomes"]
                question = market["question"]
                description = market_document["page_content"]

            search_prompt = (
                "You are a real-time market analyst for Polymarket prediction markets.\n"
                f"Search the web and X/Twitter for the most recent information about:\n"
                f'"{question}"\n\n'
                "Find:\n"
                "1. Latest news articles (last 48 hours)\n"
                "2. Expert opinions and forecasts\n"
                "3. Relevant tweets and social sentiment\n"
                "4. Traditional betting market odds if available\n"
                "5. Any data that helps estimate the real probability\n\n"
                "Summarize what you found with sources."
            )

            print("Searching web and X for real-time data...")
            search_result = self.grok.search_and_chat(search_prompt)
            realtime_info = search_result["content"]
            sources = search_result["sources"]

            forecast_prompt = (
                f"{self.prompter.superforecaster(question, description, outcomes)}\n\n"
                f"REAL-TIME INFORMATION FOUND:\n{realtime_info}\n\n"
                "Use this real-time data to improve your probability estimate."
            )

            forecast_result = self.grok.chat(forecast_prompt)
            forecast = forecast_result["content"]

            trade_prompt = self.prompter.one_best_trade(forecast, outcomes, outcome_prices)
            trade_result = self.grok.chat(trade_prompt)
            trade = trade_result["content"]

            return {
                "question": question,
                "outcome_prices": outcome_prices,
                "outcomes": outcomes,
                "realtime_info": realtime_info,
                "sources": sources,
                "forecast": forecast,
                "trade": trade
            }

        except Exception as ex:
            print(f"source_best_trade error: {ex}")
            return {
                "question": "Unknown",
                "outcome_prices": "[0.5, 0.5]",
                "outcomes": "['Yes', 'No']",
                "realtime_info": "Error obtaining real-time data",
                "sources": [],
                "forecast": "Error in forecast",
                "trade": "price:0, size:0, side:NO_TRADE"
            }

    def format_trade_prompt_for_execution(self, trade_data: dict) -> float:
        try:
            trade = trade_data.get("trade", "")
            size_match = re.findall(r"size['\"]?\s*:\s*([0-9.]+)", trade)
            if size_match:
                size = float(size_match[0])
            else:
                size = 0.0
            usdc_balance = self.polymarket.get_usdc_balance()
            return size * usdc_balance
        except Exception as ex:
            print(f"format_trade error: {ex}")
            return 0.0

    def get_llm_response(self, user_input: str) -> str:
        result = self.grok.chat(user_input)
        return result["content"]

    def get_superforecast(self, event_title: str, market_question: str, outcome: str) -> str:
        prompt = self.prompter.superforecaster(
            description=event_title,
            question=market_question,
            outcome=outcome
        )
        result = self.grok.chat(prompt)
        return result["content"]

    def source_best_market_to_create(self, filtered_markets) -> str:
        prompt = self.prompter.create_new_market(filtered_markets)
        result = self.grok.chat(prompt)
        return result["content"]
