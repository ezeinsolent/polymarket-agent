from agents.application.executor import Executor as Agent
from agents.polymarket.gamma import GammaMarketClient as Gamma
from agents.polymarket.polymarket import Polymarket
from notifier import send_telegram
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
        send_telegram("Ciclo iniciado")
        self.pre_trade_logic()

        events = self.polymarket.get_all_tradeable_events()
        print(f"1. FOUND {len(events)} EVENTS")
        send_telegram(f"Eventos encontrados: {len(events)}")

        if not events:
            send_telegram("Sin eventos disponibles. Saltando ciclo.")
            return

        send_telegram("Filtrando eventos con Grok...")
        filtered_events = self.agent.filter_events_with_rag(events)
        print(f"2. FILTERED {len(filtered_events)} EVENTS")
        send_telegram(f"Eventos filtrados: {len(filtered_events)}")

        if not filtered_events:
            send_telegram("Ningun evento paso el filtro. Saltando ciclo.")
            return

        send_telegram("Mapeando eventos a mercados...")
        markets = self.agent.map_filtered_events_to_markets(filtered_events)
        print(f"3. FOUND {len(markets)} MARKETS")
        send_telegram(f"Mercados encontrados: {len(markets)}")

        if not markets:
            send_telegram("Sin mercados disponibles. Saltando ciclo.")
            return

        send_telegram("Filtrando mejores mercados con Grok...")
        filtered_markets = self.agent.filter_markets(markets)
        print(f"4. FILTERED {len(filtered_markets)} MARKETS")
        send_telegram(f"Mercados filtrados: {len(filtered_markets)}")

        if not filtered_markets:
            send_telegram("Ningun mercado paso el filtro. Saltando ciclo.")
            return

        send_telegram("Grok analizando mejor trade...")
        market = filtered_markets[0]
        best_trade = self.agent.source_best_trade(market)
        print(f"5. CALCULATED TRADE {best_trade}")
        send_telegram(f"Analisis de Grok:\n{str(best_trade)[:1000]}")

        send_telegram("Calculando tamano de posicion...")
        try:
            amount = self.agent.format_trade_prompt_for_execution(best_trade)
            send_telegram(f"Tamano calculado: {round(float(amount), 4)} USDC - Simulacion, trade NO ejecutado")
        except Exception as e:
            send_telegram(f"Error calculando tamano: {e}")

        send_telegram("Ciclo completado. Proximo ciclo en 10 minutos.")

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
