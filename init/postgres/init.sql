-- ============================================================================
-- Hospital laSalle — Inicialización del esquema PostgreSQL
-- ============================================================================
-- Ejecutado automáticamente por la imagen oficial de PostgreSQL cuando el
-- contenedor arranca por primera vez (/docker-entrypoint-initdb.d/).
--
-- Principios:
-- - Anonimización por diseño (SDD-01 RNF-8, SDD-03 RF-14): ningún campo
--   personal directamente identificable (nombre, apellidos, DNI, dirección,
--   email, teléfono). Solo pseudo_id + atributos clínicos no identificativos.
-- - Trazabilidad obligatoria (SDD-03 RF-9): cada fila incluye `source`,
--   `ingested_at`, `processed_by`.
-- - Integridad referencial a nivel de motor (SDD-03 RNF-3).
-- - Sin datos de ejemplo hardcodeados: el seed sintético (SDD-01 RF-23,
--   SDD-02 RF-6) se carga por el pipeline con pseudo_ids generados con
--   semilla reproducible.
-- ============================================================================

-- ------------------------------------------------------------
-- Tabla: pacientes
-- Ficha del paciente (auto-reportada desde el formulario web — SDD-08 RF-1,
-- o poblada por el seed sintético).
-- ------------------------------------------------------------
CREATE TABLE IF NOT EXISTS pacientes (
    pseudo_id               TEXT PRIMARY KEY,
    edad                    INTEGER NOT NULL CHECK (edad >= 0 AND edad <= 120),
    sexo                    TEXT    NOT NULL CHECK (sexo IN ('M', 'F', 'Otro')),
    peso_kg                 INTEGER          CHECK (peso_kg IS NULL OR peso_kg > 0),
    altura_cm               INTEGER          CHECK (altura_cm IS NULL OR altura_cm > 0),
    fumador                 TEXT             CHECK (fumador IN ('no', 'si', 'exfumador')),
    embarazo                TEXT             CHECK (embarazo IN ('si', 'no', 'na')),
    enfermedades_cronicas   TEXT[]  NOT NULL DEFAULT ARRAY[]::TEXT[],

    -- Trazabilidad (SDD-03 RF-9)
    source                  TEXT    NOT NULL,
    ingested_at             TIMESTAMPTZ NOT NULL DEFAULT now(),
    processed_by            TEXT    NOT NULL,

    created_at              TIMESTAMPTZ NOT NULL DEFAULT now()
);

COMMENT ON TABLE  pacientes IS 'Pacientes anonimizados — identificados solo por pseudo_id.';
COMMENT ON COLUMN pacientes.pseudo_id     IS 'Identificador sintético (ej. PAT-000001). Única clave pública del paciente.';
COMMENT ON COLUMN pacientes.source        IS 'Origen del dato: seed_synthetic, formulario_web, csv_batch, etc.';
COMMENT ON COLUMN pacientes.processed_by  IS 'Servicio/proceso que creó este registro (ej. pipeline, api-form).';

-- ------------------------------------------------------------
-- Tabla: ingresos
-- Episodios de atención del paciente. Incluye los síntomas declarados en el
-- formulario (describen el EPISODIO concreto, no al paciente como tal).
-- ------------------------------------------------------------
CREATE TABLE IF NOT EXISTS ingresos (
    id                                      SERIAL PRIMARY KEY,
    paciente_pseudo_id                      TEXT   NOT NULL REFERENCES pacientes(pseudo_id) ON DELETE RESTRICT,

    fecha_ingreso                           TIMESTAMPTZ NOT NULL DEFAULT now(),
    motivo                                  TEXT,

    -- Síntomas y exposición epidemiológica (SDD-08 RF-1, entradas del modelo de triaje).
    motivo_principal                        TEXT CHECK (motivo_principal IN (
        'dolor_toracico', 'dificultad_respiratoria', 'fiebre',
        'dolor_abdominal', 'traumatismo', 'sintomas_neurologicos', 'otro'
    )),
    duracion_sintomas                       TEXT CHECK (duracion_sintomas IN ('<24h', '1-3d', '4-7d', '>1sem')),
    intensidad_dolor                        INTEGER CHECK (intensidad_dolor BETWEEN 0 AND 10),
    fiebre_subjetiva                        TEXT CHECK (fiebre_subjetiva IN ('no', 'leve', 'alta')),
    dificultad_respiratoria_subjetiva       TEXT CHECK (dificultad_respiratoria_subjetiva IN ('no', 'leve', 'moderada', 'grave')),
    tos                                     TEXT CHECK (tos IN ('no', 'seca', 'con_flema')),
    contacto_covid_reciente                 TEXT CHECK (contacto_covid_reciente IN ('si', 'no', 'no_se')),
    hora_envio                              INTEGER CHECK (hora_envio BETWEEN 0 AND 23),

    -- Trazabilidad (SDD-03 RF-9)
    source                  TEXT    NOT NULL,
    ingested_at             TIMESTAMPTZ NOT NULL DEFAULT now(),
    processed_by            TEXT    NOT NULL
);

COMMENT ON TABLE  ingresos IS 'Episodios asistenciales por paciente. Incluye los síntomas capturados en el formulario de triaje (SDD-08).';

CREATE INDEX IF NOT EXISTS ix_ingresos_paciente     ON ingresos(paciente_pseudo_id);
CREATE INDEX IF NOT EXISTS ix_ingresos_fecha        ON ingresos(fecha_ingreso DESC);
CREATE INDEX IF NOT EXISTS ix_pacientes_ingestado   ON pacientes(ingested_at DESC);

-- ------------------------------------------------------------
-- NOTA: no se insertan datos de ejemplo con identificadores personales.
--
-- El dataset clínico sintético se genera por el script versionado de SDD-01
-- RF-23 y se carga por el pipeline (SDD-02 RF-6), con pseudo_ids generados
-- reproduciblemente a partir de una semilla. Esto evita que el init SQL viole
-- anonimización y mantiene la trazabilidad desde el origen.
-- ------------------------------------------------------------
