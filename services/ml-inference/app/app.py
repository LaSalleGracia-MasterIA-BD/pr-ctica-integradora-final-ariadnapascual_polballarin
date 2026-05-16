import logging
import sys
from fastapi import FastAPI, File, UploadFile, HTTPException, status
from contextlib import asynccontextmanager
from .predictor import get_predictor, is_model_ready
from .schemas import RadiographyPredictionOutput
from .config import LOG_LEVEL

# Configurar logging
logging.basicConfig(
    level=getattr(logging, LOG_LEVEL, "INFO"),
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    stream=sys.stdout,
)
logger = logging.getLogger(__name__)

@asynccontextmanager
async def lifespan(app: FastAPI):
    """Lifecycle: carga el modelo al arrancar"""
    logger.info("ML Inference service starting...")
    predictor = get_predictor()
    success = predictor.load_model()
    if success:
        logger.info("Model loaded successfully")
    else:
        logger.warning("Model failed to load - service will return 503 until model is available")
    yield
    logger.info("ML Inference service shutting down")

app = FastAPI(
    title="ML Inference Service",
    description="Deep Learning radiography classification (Sana/Neumonía/COVID-19)",
    version="1.0.0",
    lifespan=lifespan,
)

@app.get("/healthz", tags=["Health"])
async def health_check():
    """Healthcheck: 200 si el modelo está listo, 503 si no"""
    if not is_model_ready():
        logger.warning("Health check failed: model not ready")
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Model not loaded"
        )
    return {"status": "ok", "model_ready": True}

@app.post("/predict", response_model=RadiographyPredictionOutput, tags=["Prediction"])
async def predict(file: UploadFile = File(...)):
    """
    Predice la clase de una radiografía de tórax.
    
    ### Parámetros
    - **file**: Imagen JPEG/PNG de radiografía
    
    ### Respuesta
    - **predicted_class**: Una de [Sana, Neumonía, COVID-19]
    - **probabilities**: Distribución de probabilidades por clase
    - **model_version**: Versión del modelo utilizado
    - **inference_time_ms**: Tiempo de ejecución en milisegundos
    - **low_confidence**: True si max(probs) < 0.50
    - **triggers_covid_alert**: True si P(COVID-19) > umbral
    
    ### Códigos de error
    - 400: Archivo no es una imagen válida
    - 422: Imagen con dimensiones inválidas
    - 503: Modelo no cargado
    """
    
    if not is_model_ready():
        logger.error("Prediction attempted with model not ready")
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Model not loaded"
        )
    
    # Validar tipo de contenido
    if file.content_type not in ["image/jpeg", "image/png", "image/jpg"]:
        logger.warning(f"Invalid content type: {file.content_type}")
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid file type. Expected image/jpeg or image/png, got {file.content_type}"
        )
    
    try:
        # Leer contenido del archivo
        contents = await file.read()
        
        if len(contents) == 0:
            raise ValueError("Empty file")
        
        # Realizar predicción
        predictor = get_predictor()
        result = predictor.predict(contents)
        
        logger.info(f"Prediction successful: {result['predicted_class']} (confidence: {max(result['probabilities'].values()):.2%})")
        
        return RadiographyPredictionOutput(**result)
    
    except ValueError as e:
        logger.error(f"Validation error: {e}")
        if "too small" in str(e).lower():
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail=f"Image dimensions invalid: {str(e)}"
            )
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )
    
    except Exception as e:
        logger.error(f"Prediction error: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Prediction failed: {str(e)}"
        )

@app.get("/", tags=["Info"])
async def root():
    """Información del servicio"""
    return {
        "service": "ML Inference",
        "version": "1.0.0",
        "task": "Radiography classification (Sana / Neumonía / COVID-19)",
        "endpoints": {
            "health": "/healthz",
            "predict": "/predict",
            "docs": "/docs",
            "openapi": "/openapi.json",
        }
    }

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8001)
