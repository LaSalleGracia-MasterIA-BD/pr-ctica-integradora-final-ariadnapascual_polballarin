$ErrorActionPreference = "Stop"

Write-Host "==> Evaluación de modelos tabulares dentro de Docker" -ForegroundColor Cyan

$ContainerScript = @'
set -eu

echo "==> Versiones instaladas"
python - <<'PY'
import matplotlib
import sklearn
import pandas
import numpy
import joblib

print("matplotlib:", matplotlib.__version__)
print("sklearn:", sklearn.__version__)
print("pandas:", pandas.__version__)
print("numpy:", numpy.__version__)
print("joblib:", joblib.__version__)
PY

echo "==> Localizando artefactos activos"

TRIAGE_ARTIFACT="$(find /app/models/triage -maxdepth 1 -type d -name 'tri-*' | sort | tail -n 1)"
DISEASE_ARTIFACT="$(find /app/models/disease -maxdepth 1 -type d -name 'dis-*' | sort | tail -n 1)"

if [ -z "$TRIAGE_ARTIFACT" ]; then
  echo "ERROR: no hay artefacto tri-* en /app/models/triage"
  exit 1
fi

if [ -z "$DISEASE_ARTIFACT" ]; then
  echo "ERROR: no hay artefacto dis-* en /app/models/disease"
  exit 1
fi

echo "TRIAGE_ARTIFACT=$TRIAGE_ARTIFACT"
echo "DISEASE_ARTIFACT=$DISEASE_ARTIFACT"

echo "==> Fijando current.txt"
basename "$TRIAGE_ARTIFACT" > /app/models/triage/current.txt
basename "$DISEASE_ARTIFACT" > /app/models/disease/current.txt

echo "==> Evaluando modelo de triaje"
python -m training.evaluate \
  --artifact "$TRIAGE_ARTIFACT" \
  --data /app/data/synthetic/triage/

echo "==> Evaluando modelo de enfermedad"
python -m training.evaluate_disease \
  --artifact "$DISEASE_ARTIFACT" \
  --data /app/data/synthetic/triage/

echo "==> Generando análisis crítico de triaje"
python -m training.critical_analysis \
  --artifact "$TRIAGE_ARTIFACT"

echo "==> Generando análisis crítico de enfermedad"
python -m training.critical_analysis_disease \
  --artifact "$DISEASE_ARTIFACT"

echo "==> Artefactos generados"
find /app/models/triage /app/models/disease -maxdepth 3 -type f | grep -E 'metrics\.json|confusion_matrix\.png|critical_analysis\.md' || true
'@

$ContainerScript | docker compose --env-file .env run -T --rm --no-deps ml-triage sh -s

if ($LASTEXITCODE -ne 0) {
    throw "La evaluación ha fallado dentro del contenedor."
}

Write-Host ""
Write-Host "OK. Evaluación y análisis crítico generados." -ForegroundColor Green