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
