# Occupa molta meno memoria e riduce la superficie di attacco per la sicurezza
FROM python:3.12.10-slim-bookworm
WORKDIR /app
# Gunicorn è un server HTTP WSGI (Web Server Gateway Interface) pensato per il linguaggio Python
# utilizzato principalmente per far girare applicazioni web in ambiente di produzione.
# Con Flask, quando scrivi codice in locale usi un server di sviluppo integrato 
# (es. quello che parte con python manage.py runserver). Quel server è comodo per fare i test, ma non è sicuro,
# non è scalabile e non è pensato per reggere il traffico reale di utenti su internet. Gunicorn serve esattamente a 
# colmare questo divario. Si posiziona nel mezzo tra il web server principale (come Nginx o Apache) e la tua applicazione Python.
COPY collector/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt \
    && useradd --system --uid 10001 --create-home appuser \
    && mkdir -p /data \
    && chown -R appuser:appuser /app /data

# quella sopra è una best practice per la sicurezza, Invece di far girare tutto con i privilegi massimi
# (come root), si compiono queste operazioni per isolare l'applicazione, proteggere il sistema e rispettare il principio del minimo privilegio.

# crea un utente "appuser" con UID 10001, crea la cartella /data e cambia il proprietario di /app e /data a "appuser".

# contiene moduli condivisi da microservizi diversi, come la logica di gioco, le classi dei mostri e le funzioni per caricare il catalogo.
COPY common /app/common
# Il catalogo e le immagini delle carte sono risorse condivise dal progetto.
COPY shared/catalog.json /app/shared/catalog.json
COPY shared/assets /app/shared/assets
COPY collector/app.py /app/app.py
# indica a Docker di eseguire i comandi successivi e il processo del container come utente ID 10001 e gruppo ID 10001.
USER 10001:10001
EXPOSE 5005

# - Avvia l'applicazione Flask (app.py, istanza "app") esponendola sulla porta 5005 all'interno del container.
# - Il parametro "--bind 0.0.0.0:5005" permette al server di accettare traffico proveniente dall'esterno del container Docker.
# - Il parametro "--workers 2" avvia 2 processi worker paralleli per gestire le richieste degli utenti sfruttando più risorse.
CMD ["gunicorn", "--bind", "0.0.0.0:5005", "--workers", "2", "app:app"]

# se facessi CMD ["flask", "--app", "app", "run", "--host=0.0.0.0", "--port=5005"]
# Usa un server di sviluppo (basato su Werkzeug) che in genere è single-threaded o gestisce le richieste in modo 
# molto limitato. Se due utenti fanno una richiesta pesante nello stesso momento, il secondo utente dovrà aspettare
# che il primo finisca (blocco).

# Con Gunicorn: Sfrutta un modello pre-fork worker. Nel tuo comando hai impostato --workers 2, il che significa
# che Gunicorn avvia due processi distinti e indipendenti in parallelo per gestire le richieste. Può servire più 
# utenti contemporaneamente senza bloccarsi.