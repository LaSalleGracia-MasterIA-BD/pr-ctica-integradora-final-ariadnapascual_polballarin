$ErrorActionPreference = "Stop"

Write-Host "==> Entrenamiento Docker de modelos tabulares: triaje + enfermedad" -ForegroundColor Cyan

Write-Host "==> Construyendo imagen ml-triage" -ForegroundColor Cyan
docker compose --env-file .env build ml-triage

Write-Host "==> Ejecutando training dentro del contenedor" -ForegroundColor Cyan

$ContainerScript = @'
set -e

echo "==> Python"
python --version

echo "==> Validando sintaxis"
python -m py_compile \
  training/model.py \
  training/rules.py \
  training/disease_rules.py \
  training/generate_dataset.py \
  training/train.py \
  training/train_disease.py \
  training/evaluate.py \
  training/evaluate_disease.py \
  training/critical_analysis.py \
  training/critical_analysis_disease.py \
  app/predictor.py

echo "==> Preparando directorios"
mkdir -p /app/data/synthetic/triage
mkdir -p /app/models/triage
mkdir -p /app/models/disease

echo "==> Generando dataset sintético"
python -m training.generate_dataset \
  --n 10000 \
  --seed 42 \
  --output /app/data/synthetic/triage/

echo "==> Entrenando modelo de triaje"
python -m training.train \
  --data /app/data/synthetic/triage/ \
  --output /app/models/triage/ \
  --seed 42

echo "==> Entrenando modelo de enfermedad"
python -m training.train_disease \
  --data /app/data/synthetic/triage/ \
  --output /app/models/disease/ \
  --seed 42

TRIAGE_ARTIFACT="$(ls -td /app/models/triage/tri-* | head -n 1)"
DISEASE_ARTIFACT="$(ls -td /app/models/disease/dis-* | head -n 1)"

if [ -z "$TRIAGE_ARTIFACT" ]; then
  echo "ERROR: no se ha generado artefacto tri-*"
  exit 1
fi

if [ -z "$DISEASE_ARTIFACT" ]; then
  echo "ERROR: no se ha generado artefacto dis-*"
  exit 1
fi

echo "==> Fijando current.txt"
basename "$TRIAGE_ARTIFACT" > /app/models/triage/current.txt
basename "$DISEASE_ARTIFACT" > /app/models/disease/current.txt

echo "==> Evaluando triaje"
python -m training.evaluate \
  --artifact "$TRIAGE_ARTIFACT" \
  --data /app/data/synthetic/triage/

echo "==> Evaluando enfermedad"
python -m training.evaluate_disease \
  --artifact "$DISEASE_ARTIFACT" \
  --data /app/data/synthetic/triage/

echo "==> Generando análisis crítico triaje"
python -m training.critical_analysis \
  --artifact "$TRIAGE_ARTIFACT"

echo "==> Generando análisis crítico enfermedad"
python -m training.critical_analysis_disease \
  --artifact "$DISEASE_ARTIFACT"

echo ""
echo "OK. Artefactos generados:"
echo "TRIAGE_ARTIFACT=$TRIAGE_ARTIFACT"
echo "DISEASE_ARTIFACT=$DISEASE_ARTIFACT"
echo ""
echo "Contenido /app/models:"
find /app/models -maxdepth 4 \( -type f -o -type l \) -print
'@

$ContainerScript | docker compose --env-file .env run --rm --no-deps -T ml-triage sh -s

Write-Host "==> Recreando servicio ml-triage" -ForegroundColor Cyan
docker compose --env-file .env up -d --force-recreate ml-triage

Write-Host "==> Healthcheck ml-triage" -ForegroundColor Cyan
Start-Sleep -Seconds 5
docker compose exec ml-triage curl -s http://localhost:8002/health

Write-Host ""
Write-Host "OK. Training Docker finalizado." -ForegroundColor Green