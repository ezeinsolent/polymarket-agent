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
        send_telegram("🚀 <b>Ciclo iniciado</b>")
        self.pre_trade_logic()

        events = self.polymarket.get_all_tradeable_events()
        print(f"1. FOUND {len(events)} EVENTS")
        send_telegram(f"📊 <b>Eventos encontrados:</b> {len(events)}")

        if not events:
            send_telegram("⚠️ <b>Sin eventos disponibles.</b> Saltando ciclo.")
            return

        send_telegram("⏳ <b>Filtrando eventos con RAG...</b>")
        filtered_events = self.agent.filter_events_with_rag(events)
        print(f"2. FILTERED {len(filtered_events)} EVENTS")
        send_telegram(f"🔍 <b>Eventos filtrados:</b> {len(filtered_events)}")

        if not filtered_events:
            send_telegram("⚠️ <b>
