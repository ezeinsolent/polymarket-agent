import time
from agents.application.trade import Trader

while True:
    try:
        print("🚀 Ciclo del agente iniciado...")
        t = Trader()
        t.one_best_trade()
    except Exception as e:
        print(f"❌ Error: {e}")
    print("⏳ Esperando 10 minutos para próximo ciclo...")
    time.sleep(600)
