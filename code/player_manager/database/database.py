# accesso al database sqlite del player manager.

import os
import sqlite3
from pathlib import Path


class Database:
    # queste eccezioni le metto qui cosi posso usarle anche dagli altri file.
    # non le sto creando io, sono gia quelle di sqlite3.
    Error = sqlite3.Error
    IntegrityError = sqlite3.IntegrityError

    # questo metodo serve per il with: viene chiamato appena entriamo nel blocco.
    # qui si apre la connessione, poi alla fine del with ci pensa __exit__ a chiuderla.
    # vedi approfondimento [a] in fondo al file.
    def __enter__(self):
        # la directory la prendiamo dalla variabile d'ambiente che abbiamo messo in docker compose.
        # aggiungiamo il nome del file, quindi il percorso finale è /data/players.sqlite.
        path = Path(os.getenv("DATA_DIR", "/data")) / "players.sqlite"
        path.parent.mkdir(parents=True, exist_ok=True)  # crea la cartella solo se non c'è.

        # apre il file sqlite; se non esiste, lo crea.
        # i 10 secondi servono se il db è bloccato, non sono un limite di tempo alla query.
        self.connection = sqlite3.connect(path, timeout=10)

        # una select restituisce righe accessibili per nome: row["email"].
        self.connection.row_factory = sqlite3.Row

        # sqlite verifica le chiavi esterne solo se questa opzione è abilitata.
        self.connection.execute("PRAGMA foreign_keys = ON")

        # restituisco questo oggetto, che nel with verrà chiamato db.
        return self

    def __exit__(self, exc_type, exc_value, traceback):
        # python esegue questo metodo quando usciamo dal with, anche in caso di errore.
        # per commit, rollback e close c'è un esempio in fondo, punto [b].
        try:
            if exc_type is None:
                self.connection.commit()  # salva le modifiche fatte nel blocco with. dato che non ci sono errori in exc_type.
            else:
                self.connection.rollback()  # annulla quelle non ancora salvate. rollback viene chiamato se c'è un errore, ed elimina tutte le modifiche fatte nel blocco with. 
        finally:
            self.connection.close()  # qui la chiudiamo sempre.

    def execute(self, query, parameters=()):
        # questo lo uso per inserire, modificare o eliminare dei record.
        # i parametri si passano nei ? invece di attaccarli alla stringa sql.
        cursor = self.connection.execute(query, parameters)
        try:
            return cursor.rowcount  # numero di righe coinvolte.
        finally:
            cursor.close()

    def execute_many(self, query, parameters):
        # stessa istruzione sql, più gruppi di parametri (esempio in [d]).
        cursor = self.connection.executemany(query, parameters)
        try:
            return cursor.rowcount
        finally:
            cursor.close()

    def fetch_one(self, query, parameters=()):
        # utile quando mi serve un solo player.
        cursor = self.connection.execute(query, parameters)
        try:
            return cursor.fetchone()  # una sqlite3.row, oppure none.
        finally:
            cursor.close()

    def fetch_all(self, query, parameters=()):
        # qui invece recupero tutte le righe trovate.
        cursor = self.connection.execute(query, parameters)
        try:
            return cursor.fetchall()  # lista di sqlite3.row; [] se non trova nulla.
        finally:
            cursor.close()

    @staticmethod
    def initialize_database():
        # /player_manager/app.py lo richiama all'avvio, senza creare prima un oggetto database.
        with Database() as db:
            # wal migliora la convivenza tra letture e scritture su sqlite.
            # non significa che due processi possano scrivere contemporaneamente.
            db.execute("PRAGMA journal_mode = WAL")

            # crea la tabella soltanto se manca. non aggiorna uno schema già esistente.
            # unique su email/nickname è importante anche per la registrazione.
            db.execute("""
                CREATE TABLE IF NOT EXISTS players (
                    player_id TEXT PRIMARY KEY,
                    email TEXT NOT NULL UNIQUE,
                    password_hash TEXT NOT NULL,
                    nickname TEXT NOT NULL UNIQUE,
                    avatar TEXT NOT NULL,
                    bio TEXT NOT NULL,
                    created_at TEXT NOT NULL
                )
            """)


# ============================================================================
# qualche spiegazione in piu e degli esempi
# gli esempi qui sotto non partono quando avvio il servizio.
# ============================================================================

# [a] perché esistono __enter__ e __exit__
# ad esempio in authentication.py troviamo:
#
#   with Database() as db:
#       db.execute("INSERT INTO ...", (...))
#
# il with è di python, non è una funzione propria di sqlite.
# python crea database(), chiama __enter__ e assegna a "db" il suo return.
# dentro il blocco facciamo le query; uscendo, python chiama __exit__.
# cosi non dobbiamo ricordarci ogni volta di aprire, salvare e chiudere la connessione.
# ogni nuovo "with database()" crea una nuova connessione allo stesso file,
# non un altro database con dati separati. il file rimane nel volume docker.

# [b] differenza tra commit, rollback e close
# esempio: vogliamo fare due modifiche che devono riuscire insieme.
#
#   with Database() as db:
#       db.execute("UPDATE players SET avatar = ? WHERE player_id = ?", ("mage", "123"))
#       db.execute("UPDATE players SET avatar = ? WHERE player_id = ?", ("ranger", "456"))
#
# se entrambe terminano senza errori, __exit__ fa commit: le modifiche restano.
# se la seconda genera un'eccezione, __exit__ fa rollback della transazione.
# close() invece libera la connessione: non è il comando che salva i dati.
# il blocco with garantisce qui una transazione per più operazioni sullo stesso db.

# [c] come leggere il risultato di una select
# con row_factory = sqlite3.row, fetch_one restituisce una riga indicizzabile
# per nome della colonna; fetch_all restituisce una lista di queste righe.
#
#   with Database() as db:
#       player = db.fetch_one("SELECT player_id, email FROM players WHERE player_id = ?",
#                             ("123",))
#   if player is not None:
#       print(player["email"])
#
# invece, con fetch_all:
#   with Database() as db:
#       players = db.fetch_all("SELECT player_id, email FROM players")
#   for player in players:
#       print(player["player_id"], player["email"])
#
# non otteniamo una struttura organizzata per colonne come {"email": [...], "player_id": [...]}:
# prima selezioniamo la riga, poi la colonna (es. players[0]["email"]).
# e attenzione: execute() su select non restituisce i record, ma rowcount.

# [d] esempi delle query usate dal player manager
# registrazione (authentication.py): email e nickname duplicati sono bloccati
# dai vincoli unique della tabella; sqlite solleva integrityerror.
#
#   with Database() as db:
#       db.execute(
#           """INSERT INTO players
#              (player_id, email, password_hash, nickname, avatar, bio, created_at)
#              VALUES (?, ?, ?, ?, ?, ?, ?)""",
#           (player_id, email, password_hash, nickname, avatar, bio, created_at)
#       )
# qui le variabili sono già state preparate da register_player().
#
# login (authentication.py): ricerco il player e poi verifico la password
# con check_password_hash, che si trova nella componente di autenticazione.
#
#   with Database() as db:
#       row = db.fetch_one("SELECT * FROM players WHERE email = ?", (email,))
#
# modifica profilo (player_profile.py): update e select usano lo stesso with.
#
#   with Database() as db:
#       db.execute("UPDATE players SET nickname = ? WHERE player_id = ?",
#                  (nickname, player_id))
#       row = db.fetch_one("SELECT * FROM players WHERE player_id = ?", (player_id,))
#
# eliminazione: execute restituisce il numero di righe eliminate (0 oppure 1
# nel nostro caso, perché player_id è una chiave primaria).
#
#   with Database() as db:
#       deleted = db.execute("DELETE FROM players WHERE player_id = ?", (player_id,))
#
# esecuzione multipla: stessa query, parametri diversi.
#
#   with Database() as db:
#       db.execute_many("UPDATE players SET avatar = ? WHERE player_id = ?",
#                       [("mage", "123"), ("ranger", "456")])
#
# occhio alla virgola in ("123",): in python serve per creare una tupla con un solo valore.
# il ? permette di passare valori separati dal testo sql ed evita di costruire
# query concatenando direttamente i dati ricevuti nelle richieste http.