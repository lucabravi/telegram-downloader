import asyncio
import logging
from datetime import datetime
from pyrogram.errors import FloodWait  # Assumiamo tu stia usando Pyrogram
from pyrogram.types import Message

# --- GLOBAL STATE ---
last_messages = []
# Inizializziamo al 1970 per evitare che il controllo scatti erroneamente all'avvio del bot
last_block = datetime.fromtimestamp(0) 
last_block_seconds = 0
last_sent_message_id = {}

# Lock per proteggere l'accesso alle variabili globali in ambiente concorrente
_rate_lock = asyncio.Lock()
_message_queue = asyncio.Queue()

def _log_rate_limited_message(function, kwargs, wait_time: int):
    text = kwargs.get("text")
    if text is None:
        return
    func_name = getattr(function, "__name__", "call")
    snippet = text.replace("\n", " ").strip()
    if len(snippet) > 200:
        snippet = f"{snippet[:200]}..."
    logging.info(f"FloodWait({wait_time}s) queued message via {func_name}: {snippet}")

async def catch_rate_limit(function, wait=True, *args, **kwargs):
    global last_block, last_block_seconds

    while True:
        # Variabile per sapere quanto dormire (calcolata sotto lock, eseguita fuori)
        sleep_needed = 0
        
        # --- INIZIO CRITICAL SECTION ---
        # Acquisiamo il lock per leggere e modificare lo stato in sicurezza
        async with _rate_lock:
            now = datetime.now()
            
            # 1. Controllo FloodWait (Blocco globale imposto da Telegram)
            delta_since_block = (now - last_block).total_seconds()
            remaining_block_time = (last_block_seconds + 2) - delta_since_block

            if remaining_block_time > 0:
                # Siamo ancora nel periodo di blocco/penalità
                if not wait:
                    return None
                sleep_needed = remaining_block_time

            # 2. Controllo Rate Limit locale (max 3 messaggi / 1 secondo)
            # Eseguiamo questo controllo solo se non siamo già bloccati dal FloodWait
            elif len(last_messages) >= 3:
                # Quanto tempo è passato dal terzultimo messaggio?
                delta_msg = (now - last_messages[-3]).total_seconds()
                
                if delta_msg <= 1:
                    if not wait:
                        return None
                    # Calcoliamo l'attesa esatta per liberare lo slot + un piccolo buffer (0.1s)
                    sleep_needed = (1 - delta_msg) + 0.1
                else:
                    # Abbiamo spazio: registriamo il messaggio ORA e aggiorniamo la lista
                    last_messages.append(now)
                    if len(last_messages) > 3:
                        last_messages.pop(0)
            else:
                # Meno di 3 messaggi in lista, via libera
                last_messages.append(now)
        
        # --- FINE CRITICAL SECTION ---

        # 3. Gestione Attesa (Fuori dal Lock)
        # Se dobbiamo aspettare, lo facciamo qui rilasciando il lock, 
        # permettendo ad altri task di fare i loro controlli.
        if sleep_needed > 0:
            await asyncio.sleep(sleep_needed)
            # Al risveglio ricominciamo il ciclo while per ricontrollare le condizioni
            continue

        # 4. Esecuzione Funzione (Chiamata API effettiva)
        try:
            result = await function(*args, **kwargs)
            func_name = getattr(function, "__name__", "")
            if func_name in ("send_message", "reply") and isinstance(result, Message):
                last_sent_message_id[result.chat.id] = result.id
            return result
        except FloodWait as e:
            logging.warning(f'async catch_rate_limit - FloodWait: {e.value}s')
            _log_rate_limited_message(function, kwargs, e.value)
            
            # Aggiorniamo lo stato globale del blocco acquisendo brevemente il lock
            async with _rate_lock:
                last_block = datetime.now()
                last_block_seconds = e.value
            
            if not wait:
                # Se wait è False, rinunciamo. 
                # Opzionale: piccolo sleep per evitare loop stretti in caso di chiamate errate ripetute
                await asyncio.sleep(1) 
                return None
            
            # Dormiamo per il tempo richiesto da Telegram (fuori dal lock)
            await asyncio.sleep(e.value)
            # Il ciclo while ripartirà


async def enqueue_message(function, *args, **kwargs):
    loop = asyncio.get_running_loop()
    future = loop.create_future()
    await _message_queue.put((function, args, kwargs, future))
    return future


async def run_message_queue():
    while True:
        function, args, kwargs, future = await _message_queue.get()
        try:
            result = await catch_rate_limit(function, wait=True, *args, **kwargs)
            if not future.done():
                future.set_result(result)
        except Exception as exc:
            logging.error(f'message_queue | {exc}')
            if not future.done():
                future.set_exception(exc)
        finally:
            _message_queue.task_done()
            await asyncio.sleep(0.35)
