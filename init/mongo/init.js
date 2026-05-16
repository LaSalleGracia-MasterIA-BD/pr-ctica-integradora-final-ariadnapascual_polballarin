// ============================================================================
// Hospital laSalle — Inicialización de MongoDB
// ============================================================================
// Ejecutado automáticamente por la imagen oficial de mongo:7 cuando el
// contenedor arranca por primera vez (/docker-entrypoint-initdb.d/).
//
// Principios:
// - Anonimización por diseño (SDD-01 RNF-8, SDD-03 RF-14, RF-15): ningún
//   campo personal directamente identificable. Referencias cruzadas a
//   PostgreSQL por pseudo_id.
// - Trazabilidad obligatoria (SDD-03 RF-9): source, ingested_at, processed_by
//   son convención en todo documento (aquí no se puede forzar a nivel de
//   motor; se valida en los servicios escritores).
// - GridFS para binarios de imagen de radiografías (SDD-03 RF-2).
// - Colecciones dedicadas alineadas con SDD-02, SDD-03, SDD-04, SDD-06, SDD-08.
// - Sin datos de ejemplo con identificadores reales.
// ============================================================================

(function () {
  const dbName = 'hospital';
  const hospital = db.getSiblingDB(dbName);

  // --------------------------------------------------------------------------
  // Colecciones del dominio
  // --------------------------------------------------------------------------
  const collections = [
    'predictions_radiography', // SDD-06 — una por radiografía, versionada por model_version
    'predictions_triage',      // SDD-08 — una por ficha de paciente, versionada por model_version
    'predictions_disease',     // DESIGN-08b — sospecha de enfermedad (diagnóstico diferencial)
    'reports',                 // SDD-04 — informes diarios (PDF en GridFS + JSON inline)
    'alerts',                  // SDD-04 — alertas emitidas (clínicas y operativas)
    'system_events',           // SDD-03/SDD-07 — eventos de dominio (auditoría)
    'ingestion_rejects'        // SDD-02 — registros rechazados por validación
  ];

  const existing = new Set(hospital.getCollectionInfos().map(function (c) { return c.name; }));
  collections.forEach(function (name) {
    if (!existing.has(name)) {
      hospital.createCollection(name);
    }
  });

  // --------------------------------------------------------------------------
  // GridFS: bucket 'radiographs' para bytes de imagen (SDD-03 RF-2, RF-12)
  // Las colecciones radiographs.files / radiographs.chunks se crean on-demand
  // en la primera subida; aquí solo dejamos índice explícito sobre filename.
  // --------------------------------------------------------------------------
  hospital.createCollection('radiographs.files');
  hospital.createCollection('radiographs.chunks');
  hospital['radiographs.files'].createIndex({ filename: 1 });
  hospital['radiographs.chunks'].createIndex({ files_id: 1, n: 1 }, { unique: true });

  // --------------------------------------------------------------------------
  // Índices para consultas típicas (SDD-03 RF-13, SDD-05 endpoints de lista)
  // --------------------------------------------------------------------------
  hospital.predictions_radiography.createIndex({ radiograph_id: 1 });
  hospital.predictions_radiography.createIndex({ patient_pseudo_id: 1 });
  hospital.predictions_radiography.createIndex({ created_at: -1 });
  hospital.predictions_radiography.createIndex({ model_version: 1 });

  hospital.predictions_triage.createIndex({ patient_pseudo_id: 1 });
  hospital.predictions_triage.createIndex({ created_at: -1 });
  hospital.predictions_triage.createIndex({ model_version: 1 });

  hospital.predictions_disease.createIndex({ patient_pseudo_id: 1 });
  hospital.predictions_disease.createIndex({ ingested_at: -1 });
  hospital.predictions_disease.createIndex({ model_version: 1 });
  hospital.predictions_disease.createIndex({ inference_status: 1 });

  hospital.reports.createIndex({ report_date: -1 }, { unique: true });

  hospital.alerts.createIndex({ emitted_at: -1 });
  hospital.alerts.createIndex({ type: 1, correlation_id: 1 });
  hospital.alerts.createIndex({ severity: 1, status: 1 });

  hospital.system_events.createIndex({ timestamp: -1 });
  hospital.system_events.createIndex({ correlation_id: 1 });
  hospital.system_events.createIndex({ service: 1, event: 1 });

  hospital.ingestion_rejects.createIndex({ ingested_at: -1 });
  hospital.ingestion_rejects.createIndex({ source: 1 });

  // --------------------------------------------------------------------------
  // Usuario de aplicación con permisos mínimos (readWrite sobre 'hospital').
  // --------------------------------------------------------------------------
  try {
    hospital.createUser({
      user: 'appuser',
      pwd: 'app-pass',
      roles: [{ role: 'readWrite', db: dbName }]
    });
  } catch (e) {
    // Usuario ya existente (reinicios): ignorar.
  }

  // --------------------------------------------------------------------------
  // NOTA: no se insertan documentos de ejemplo con identificadores personales.
  // El seed sintético se carga por el pipeline (SDD-02 RF-6) con pseudo_ids
  // generados reproduciblemente a partir de una semilla.
  // --------------------------------------------------------------------------
})();
