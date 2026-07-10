# sync-resources

Sincroniza los repos *starred* de GitHub a notas markdown en el digital brain,
de forma idempotente e incremental. Pensado para correr desde cron.

## Setup

```bash
python3 -m venv venv
./venv/bin/pip install -r requirements.txt
cp .env.example .env   # completar OPENAI_API_KEY
```

Requiere `gh` CLI autenticado (`gh auth status`). La reindexación GBrain es
opcional y defensiva: si `gbrain` no está instalado, se omite con un warning.

## Uso

```bash
./venv/bin/python sync_repos.py
```

Solo genera notas para repos faveados nuevos (los ya presentes en
`Recursos externos/` se saltean). Al generar notas nuevas: commit + push al repo
del digital brain y reindexación GBrain.

## Cron (ejemplo, diario 4am)

```
0 4 * * * cd /home/matiapa/Applications/sync-resources && ./venv/bin/python sync_repos.py >> sync.log 2>&1
```

## Logfile

Cada corrida agrega una línea de resumen a `sync.log` (fecha, resultado,
métricas y detalle de errores). Este archivo queda en esta carpeta y no se copia
al digital brain.
