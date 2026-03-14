import time
from agents.application.trade import Trader

while True:
    try:
        print("Ciclo iniciado")
        t = Trader()
        t.one_best_trade()
    except Exception as e:
        print(f"Error: {e}")
        time.sleep(60)
    print("Esperando 10 minutos...")
    time.sleep(600)
