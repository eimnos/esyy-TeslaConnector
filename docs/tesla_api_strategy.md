# Tesla API Strategy (Future Waves)

Obiettivo: integrare Tesla Fleet API in modo sicuro e cost-aware.

## Linee guida

- usare Tesla Fleet API con attenzione ai costi;
- evitare polling continuo;
- evitare wake-up inutili del veicolo;
- usare polling lento quando il veicolo e idle;
- aumentare la frequenza solo durante ricarica attiva;
- inviare `set charging amps` solo se la variazione e almeno `>= 2A`;
- usare dry-run obbligatorio prima di abilitare comandi reali.

## Guardrail

- nessun token hardcoded;
- configurazione via environment variables/secret manager;
- fallback sicuro: in caso di errore, nessun comando distruttivo.
