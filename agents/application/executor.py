import os
import json
import ast
import re
from typing import List, Dict, Any

import math

from dotenv import load_dotenv
from langchain_core.messages import HumanMessage, SystemMessage
from langchain_openai import ChatOpenAI
from langchain_openai import ChatOpenAI as ChatXAI

from agents.polymarket.gamma import GammaMarketClient as Gamma
from agents.connectors.chroma import PolymarketRAG as Chroma
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

class Executor:
    def __init__(self, default_model='grok-3-mini') -> None:
        load_dotenv()
        max_token_model = {'grok-3-mini': 100000, 'grok-3': 100000}
        self.token_limit = max_token_model.get(default_model, 100000)
        self.prompter = Prompter()
        self.openai_api_key = os.getenv("XAI_API_KEY")
        self.llm = ChatOpenAI(
            model=default_model,
            temperature=0,
            openai_api_key=os.getenv("XAI_API_KEY"),
            openai_api_base="https://api.x.ai/v1",
        )
        self.gamma = Gamma()
        self.chroma = Chroma()
        self.polymarket = Polymarket()

    def get_llm_response(self, user_input: str) -> str:
        system_message = SystemMessage(content=str(self.prompter.market_analyst()))
        human_message = HumanMessage(content=user_input)
        messages = [system_message, human_message]
        result = self.llm.invoke(messages)
        return result.content

    def get_superforecast(
        self, event_title: str, market_question: str, outcome: str
    ) -> str:
        messages = self.prompter.superforecaster(
            description=event_title, question=market_question, outcome=outcome
        )
        result = self.llm.invoke(messages)
        return result.content


    def estimate_tokens(self, text: str) -> int:
        # This is a rough estimate. For more accurate results, consider using a tokenizer.
        return len(text) // 4  # Assuming average of 4 characters per token

    def process_data_chunk(self, data1: List[Dict[Any, Any]], data2: List[Dict[Any, Any]], user_input: str) -> str:
        system_message = SystemMessage(
            content=str(self.prompter.prompts_polymarket(data1=data1, data2=data2))
        )
        human_message = HumanMessage(content=user_input)
        messages = [system_message, human_message]
        result = self.llm.invoke(messages)
        return result.content


    def divide_list(self, original_list, i):
        # Calculate the size of each sublist
        sublist_size = math.ceil(len(original_list) / i)
        
        # Use list comprehension to create sublists
        return [original_list[j:j+sublist_size] for j in range(0, len(original_list), sublist_size)]
    
    def get_polymarket_llm(self, user_input: str) -> str:
        data1 = self.gamma.get_current_events()
        data2 = self.gamma.get_current_markets()
        
        combined_data = str(self.prompter.prompts_polymarket(data1=data1, data2=data2))
        
        # Estimate total tokens
        total_tokens = self.estimate_tokens(combined_data)
        
        # Set a token limit (adjust as needed, leaving room for system and user messages)
        token_limit = self.token_limit
        if total_tokens <= token_limit:
            # If within limit, process normally
            return self.process_data_chunk(data1, data2, user_input)
        else:
            # If exceeding limit, process in chunks
            chunk_size = len(combined_data) // ((total_tokens // token_limit) + 1)
            print(f'total tokens {total_tokens} exceeding llm capacity, now will split and answer')
            group_size = (total_tokens // token_limit) + 1 # 3 is safe factor
            keys_no_meaning = ['image','pagerDutyNotificationEnabled','resolvedBy','endDate','clobTokenIds','negRiskMarketID','conditionId','updatedAt','startDate']
            useful_keys = ['id','questionID','description','liquidity','clobTokenIds','outcomes','outcomePrices','volume','startDate','endDate','question','questionID','events']
            data1 = retain_keys(data1, useful_keys)
            cut_1 = self.divide_list(data1, group_size)
            cut_2 = self.divide_list(data2, group_size)
            cut_data_12 = zip(cut_1, cut_2)

            results = []

            for cut_data in cut_data_12:
                sub_data1 = cut_data[0]
                sub_data2 = cut_data[1]
                sub_tokens = self.estimate_tokens(str(self.prompter.prompts_polymarket(data1=sub_data1, data2=sub_data2)))

                result = self.process_data_chunk(sub_data1, sub_data2, user_input)
                results.append(result)
            
            combined_result = " ".join(results)
            
        
            
            return combined_result
    def filter_events(self, events: "list[SimpleEvent]") -> str:
        prompt = self.prompter.filter_events(events)
        result = self.llm.invoke(prompt)
        return result.content

    def filter_events_with_rag(self, events: "list[SimpleEvent]") -> list:
        try:
            events_text = "\n".join([
                f"- ID:{e.id} | {e.title}"
                for e in events[:30]
            ])
            prompt = f"""
            {self.prompter.filter_events()}
            
            Here are the available events:
            {events_text}
            
            Return ONLY a Python list of event IDs that pass the filter.
            Example: [123, 456, 789]
            Return ONLY the list, nothing else.
            """
            messages = [HumanMessage(content=prompt)]
            result = self.llm.invoke(messages)
            content = result.content.strip()
            import ast
            ids = ast.literal_eval(content)
            filtered = [e for e in events if e.id in ids]
            return filtered
        except Exception as ex:
            print(f"Filter error: {ex}")
            return events[:5]
            
    def map_filtered_events_to_markets(
            self, filtered_events: "list[SimpleEvent]"
        ) -> "list[SimpleMarket]":
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
                            formatted_market_data = self.polymarket.map_api_to_market(market_data)
                            markets.append(formatted_market_data)
                except Exception as ex:
                    print(f"Market mapping error: {ex}")
                    continue
            return markets

    def filter_markets(self, markets) -> list:
        try:
            markets_text = "\n".join([
                f"- ID:{m.id if hasattr(m, 'id') else i} | {m.question if hasattr(m, 'question') else str(m)}"
                for i, m in enumerate(markets[:20])
            ])
            prompt = f"""
            {self.prompter.filter_markets()}
            
            Here are the available markets:
            {markets_text}
            
            Return ONLY a Python list with the index numbers of the 3 best markets.
            Example: [0, 2, 5]
            Return ONLY the list, nothing else.
            """
            messages = [HumanMessage(content=prompt)]
            result = self.llm.invoke(messages)
            content = result.content.strip()
            import ast
            indices = ast.literal_eval(content)
            filtered = [markets[i] for i in indices if i < len(markets)]
            return filtered
        except Exception as ex:
            print(f"Filter markets error: {ex}")
            return markets[:3]

    def source_best_trade(self, market_object) -> str:
        market_document = market_object[0].dict()
        market = market_document["metadata"]
        outcome_prices = ast.literal_eval(market["outcome_prices"])
        outcomes = ast.literal_eval(market["outcomes"])
        question = market["question"]
        description = market_document["page_content"]

        prompt = self.prompter.superforecaster(question, description, outcomes)
        print()
        print("... prompting ... ", prompt)
        print()
        result = self.llm.invoke(prompt)
        content = result.content

        print("result: ", content)
        print()
        prompt = self.prompter.one_best_trade(content, outcomes, outcome_prices)
        print("... prompting ... ", prompt)
        print()
        result = self.llm.invoke(prompt)
        content = result.content

        print("result: ", content)
        print()
        return content

    def format_trade_prompt_for_execution(self, best_trade: str) -> float:
        data = best_trade.split(",")
        # price = re.findall("\d+\.\d+", data[0])[0]
        size = re.findall("\d+\.\d+", data[1])[0]
        usdc_balance = self.polymarket.get_usdc_balance()
        return float(size) * usdc_balance

    def source_best_market_to_create(self, filtered_markets) -> str:
        prompt = self.prompter.create_new_market(filtered_markets)
        print()
        print("... prompting ... ", prompt)
        print()
        result = self.llm.invoke(prompt)
        content = result.content
        return content
