from agents.application.executor import Executor as Agent
from agents.polymarket.gamma import GammaMarketClient as Gamma
from agents.polymarket.polymarket import Polymarket
from notifier import send_telegram
from datetime import datetime
import shutil
import pytz


def get_timestamp():
    madrid = pytz.timezone("Europe/Madrid")
    now = datetime.now(madrid)
    return now.strftime("%d/%m/%Y %H:%M UTC+1")


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

    def get_wallet_info(self):
        try:
            balance = self.polymarket.get_usdc_balance()
            address = self.polymarket.get_address()
            short = f"{str(address)[:6]}...{str(address)[-4:]}"
            return balance, short
        except:
            return 0.0, "0x????...????"

    def one_best_trade(self) -> None:
        ts = get_timestamp()
        balance, wallet = self.get_wallet_info()

        send_telegram(
            f"AGENTE INICIADO\n"
            f"Fecha y hora: {ts}\n"
            f"Bankroll: ${round(float(balance), 2)} USDC\n"
            f"Wallet: {wallet}"
        )

        self.pre_trade_logic()

        events = self.polymarket.get_all_tradeable_events()
        send_telegram(
            f"PASO 1 - BUSQUEDA\n"
            f"Eventos activos encontrados: {len(events)}\n"
            f"Fuente: Polymarket API"
        )

        if not events:
            send_telegram("SIN EVENTOS DISPONIBLES. Saltando ciclo.")
            return

        send_telegram("PASO 2 - FILTRANDO EVENTOS CON GROK...")
        filtered_events = self.agent.filter_events_with_rag(events)

        events_list = "\n".join([
            f"  - {e.title[:60]}" for e in filtered_events[:5]
        ])
        send_telegram(
            f"EVENTOS SELECCIONADOS: {len(filtered_events)}\n"
            f"{events_list}"
        )

        if not filtered_events:
            send_telegram("NINGUN EVENTO PASO EL FILTRO. Saltando ciclo.")
            return

        send_telegram("PASO 3 - MAPEANDO MERCADOS...")
        markets = self.agent.map_filtered_events_to_markets(filtered_events)
        send_telegram(
            f"MERCADOS ENCONTRADOS: {len(markets)}\n"
            f"Procesando para seleccionar los mejores..."
        )

        if not markets:
            send_telegram("SIN MERCADOS DISPONIBLES. Saltando ciclo.")
            return

        send_telegram("PASO 4 - FILTRANDO MEJORES MERCADOS CON GROK...")
        filtered_markets = self.agent.filter_markets(markets)
        send_telegram(
            f"DEBUG mercado: {type(filtered_markets[0])} | {str(filtered_markets[0])[:200]}"
        )

        markets_list = "\n".join([
            f"  - {m.question[:60] if hasattr(m, 'question') else str(m)[:60]}"
            for m in filtered_markets[:3]
        ])
        send_telegram(
            f"MERCADOS SELECCIONADOS: {len(filtered_markets)}\n"
            f"{markets_list}"
        )

        if not filtered_markets:
            send_telegram("NINGUN MERCADO PASO EL FILTRO. Saltando ciclo.")
            return

        market = filtered_markets[0]
        if isinstance(market, dict):
            question = market.get('question', 'Unknown')
            price_yes = market.get('outcome_prices', 'N/A')
        else:
            question = market.question if hasattr(market, 'question') else "Unknown"
            price_yes = market.outcome_prices if hasattr(market, 'outcome_prices') else "N/A"

        send_telegram(
            f"PASO 5 - MERCADO PARA ANALISIS:\n"
            f"Pregunta: {question[:100]}\n"
            f"Precios: {price_yes}"
        )

        send_telegram("PASO 6 - BUSCANDO INFO EN TIEMPO REAL...\n(Web + X/Twitter via Grok)")
        trade_data = self.agent.source_best_trade(market)

        sources_text = "\n".join([
            f"  - {s}" for s in trade_data.get("sources", [])[:5]
        ]) or "  - Sin fuentes externas encontradas"

        send_telegram(
            f"INFORMACION EN TIEMPO REAL:\n"
            f"{trade_data.get('realtime_info', 'No disponible')[:500]}\n\n"
            f"FUENTES CONSULTADAS:\n{sources_text}\n\n"
            f"DEBUG API: {trade_data.get('api_debug', 'Sin debug')}"
        )

        send_telegram(
            f"PASO 7 - ANALISIS GROK (SUPERFORECASTER):\n"
            f"{trade_data.get('forecast', 'No disponible')[:600]}"
        )

        trade = trade_data.get("trade", "price:0, size:0, side:NO_TRADE")
        send_telegram(
            f"PASO 8 - DECISION FINAL:\n"
            f"{trade[:400]}"
        )

        try:
            amount = self.agent.format_trade_prompt_for_execution(trade_data)
            send_telegram(
                f"PASO 9 - GESTION DE CAPITAL:\n"
                f"Tamano calculado: ${round(float(amount), 4)} USDC\n"
                f"Estado: SIMULACION - Trade NO ejecutado\n"
                f"Proximo ciclo en 10 minutos."
            )
        except Exception as e:
            send_telegram(f"Error calculando tamano: {e}\nProximo ciclo en 10 minutos.")

        # trade = self.polymarket.execute_market_order(market, amount)
        # print(f"6. TRADED {trade}")

    def maintain_positions(self):
        pass

    def incentive_farm(self):
        pass


if __name__ == "__main__":
    t = Trader()
    t.one_best_trade()
