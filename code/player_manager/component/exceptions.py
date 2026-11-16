"""Errori applicativi del Player Manager, indipendenti dal protocollo HTTP."""


class ApplicationError(Exception):
    # classe base: le componenti segnalano il problema, senza costruire risposte json.
    # code e message saranno usati da app.py per creare la risposta al frontend.
    def __init__(self, code, message):
        super().__init__(message)
        self.code = code
        self.message = message


class ValidationError(ApplicationError):
    # dati non validi, ad esempio un nickname vuoto.
    pass


class AuthenticationError(ApplicationError):
    # credenziali errate durante il login.
    pass


class NotFoundError(ApplicationError):
    # risorsa richiesta non presente nel database.
    pass


class ConflictError(ApplicationError):
    # vincolo di unicità violato, per esempio email già utilizzata.
    pass


class DependencyError(ApplicationError):
    # un altro microservizio non ha confermato l'operazione richiesta.
    pass


class StorageError(ApplicationError):
    # errore del database locale o di lettura di un file necessario al servizio.
    pass