from agents.application.executor import Executor as Agent
from agents.polymarket.gamma import GammaMarketClient as Gamma
from agents.polymarket.polymarket import Polymarket
import shutil

class Trader:
    def __init__(self):
        self.polymarket = Polymarket()
        self.gamma = Gamma()
        self.agent = Agent()

    def pre_trade_logic(self) -> None:
        self.clear_local_dbs()

    def clear_local_dbs(self) -> None:
        try:
            shutil.rmtree("local_db_events")
        except:
            pass
        try:
            shutil.rmtree("local_db_markets")
        except:
            pass

    def one_best_trade(self) -> None:
        self.pre_trade_logic()
        events = self.polymarket.get_all_tradeable_events()
        print(f"1. FOUND {len(events)} EVENTS")
        if not events:
            print("No events found, skipping cycle.")
            return
        filtered_events = self.agent.filter_events_with_rag(events)
        print(f"2. FILTERED {len(filtered_events)} EVENTS")
        if not filtered_events:
            print("No filtered events, skipping cycle.")
            return
        markets = self.agent.map_filtered_events_to_markets(filtered_events)
        print(f"3. FOUND {len(markets)} MARKETS")
        if not markets:
            print("No markets found, skipping cycle.")
            return
        filtered_markets = self.agent.filter_markets(markets)
        print(f"4. FILTERED {len(filtered_markets)} MARKETS")
        if not filtered_markets:
            print("No filtered markets, skipping cycle.")
            return
        market = filtered_markets[0]
        best_trade = self.agent.source_best_trade(market)
        print(f"5. CALCULATED TRADE {best_trade}")
        amount = self.agent.format_trade_prompt_for_execution(best_trade)
        # Please refer to TOS before uncommenting: polymarket.com/tos
        # trade = self.polymarket.execute_market_order(market, amount)
        # print(f"6. TRADED {trade}")

    def maintain_positions(self):
        pass

    def incentive_farm(self):
        pass

if __name__ == "__main__":
    t = Trader()
    t.one_best_trade()
