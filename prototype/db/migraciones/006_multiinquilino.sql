-- db/migraciones/006_multiinquilino.sql
-- Demostracion del Sprint 4 (copia local, no entregada): MotelOS como servicio para varios establecimientos.
-- Se aplica con el usuario dueno de las tablas, despues de 005_panel_configuracion.sql.
--
-- Modelo elegido: una sola base y un solo esquema compartidos, con la columna establecimiento_id en cada tabla
-- y Row Level Security (RLS) de PostgreSQL. Se descartaron:
--   * una base por establecimiento: aislamiento maximo, pero N bases que migrar, respaldar y monitorear;
--   * un esquema por establecimiento: migraciones repetidas por esquema y search_path dependiente de la sesion.
--
-- Tres capas de aislamiento, de afuera hacia adentro:
--   1. La aplicacion filtra cada consulta del ORM por el establecimiento de la sesion (app/core/inquilino.py).
--   2. RLS: aunque una consulta olvide el filtro, motel_app solo ve y escribe las filas del establecimiento que
--      fija la transaccion (set_config('app.establecimiento_id', ...)). Sin ese valor no ve ninguna fila.
--   3. Claves foraneas compuestas (establecimiento_id, id): ningun pago, consumo o turno puede apuntar a una
--      fila de otro establecimiento, ni siquiera desde el dueno de las tablas.
--
-- El establecimiento de la sesion sale del token firmado (JWT, claim "est"), nunca del cuerpo de la peticion.
-- El valor 0 identifica a la plataforma: el equipo que da de alta establecimientos y no ve su operacion.

-- ---------------------------------------------------------------------------------------------------
-- Establecimientos (inquilinos)
-- ---------------------------------------------------------------------------------------------------
CREATE TABLE establecimientos (
    id SERIAL PRIMARY KEY,
    codigo VARCHAR(30) UNIQUE NOT NULL CHECK (codigo ~ '^[a-z0-9-]{3,30}$'),
    nombre VARCHAR(80) NOT NULL,
    domicilio VARCHAR(120),
    telefono VARCHAR(40),
    -- Texto al pie del comprobante de arqueo en PDF (RF-10).
    leyenda_comprobante VARCHAR(200),
    activo BOOLEAN NOT NULL DEFAULT TRUE,
    creado_en TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT CURRENT_TIMESTAMP
);

-- El establecimiento que ya usaba el sistema pasa a ser el numero 1 con todos sus datos.
INSERT INTO establecimientos (id, codigo, nombre) VALUES (1, 'motelcc', 'Motel C.C.');
SELECT setval('establecimientos_id_seq', 1);

-- Establecimiento de la transaccion en curso; -1 (ninguna fila) si la aplicacion no lo fijo.
CREATE OR REPLACE FUNCTION app_establecimiento() RETURNS INTEGER AS $$
    SELECT coalesce(nullif(current_setting('app.establecimiento_id', true), ''), '-1')::INTEGER;
$$ LANGUAGE sql STABLE;

-- ---------------------------------------------------------------------------------------------------
-- Columna establecimiento_id en cada tabla de la operacion. Las filas existentes quedan en el establecimiento 1.
-- El valor por defecto es el establecimiento de la transaccion: si la aplicacion no lo fija, la fila apunta a
-- -1, que no existe, y la clave foranea la rechaza.
-- ---------------------------------------------------------------------------------------------------
DO $$
DECLARE
    tabla TEXT;
BEGIN
    FOREACH tabla IN ARRAY ARRAY['habitaciones', 'tarifas', 'turnos', 'estadias_activas', 'articulos',
                                 'detalles_consumo', 'pagos', 'operadores', 'guardias', 'arqueos_caja',
                                 'configuracion_caja']
    LOOP
        -- ADD COLUMN con DEFAULT completa las filas existentes sin un UPDATE: no dispara los triggers que
        -- protegen turnos, pagos, guardias y arqueos cerrados (un UPDATE los rechazaria).
        EXECUTE format('ALTER TABLE %I ADD COLUMN establecimiento_id INTEGER %s DEFAULT 1 '
                       'REFERENCES establecimientos(id)', tabla,
                       CASE WHEN tabla = 'operadores' THEN '' ELSE 'NOT NULL' END);
        EXECUTE format('ALTER TABLE %I ALTER COLUMN establecimiento_id SET DEFAULT app_establecimiento()', tabla);
        EXECUTE format('CREATE INDEX %I ON %I (establecimiento_id)', tabla || '_por_establecimiento', tabla);
    END LOOP;
END $$;

-- Los usuarios de la plataforma no pertenecen a ningun establecimiento; todos los demas pertenecen a uno.
ALTER TABLE operadores DROP CONSTRAINT operadores_rol_check;
ALTER TABLE operadores ADD CONSTRAINT operadores_rol_check
    CHECK (rol IN ('OPERADOR', 'ADMINISTRADOR', 'PLATAFORMA'));
ALTER TABLE operadores ADD CONSTRAINT operador_de_un_establecimiento
    CHECK ((rol = 'PLATAFORMA') = (establecimiento_id IS NULL));

-- ---------------------------------------------------------------------------------------------------
-- Unicidad por establecimiento: dos moteles pueden tener la habitacion 1, el articulo MIN-001 o el usuario
-- conserje1. Lo que era unico en toda la base pasa a ser unico dentro de cada establecimiento.
-- ---------------------------------------------------------------------------------------------------
ALTER TABLE habitaciones DROP CONSTRAINT habitaciones_numero_key;
ALTER TABLE habitaciones ADD CONSTRAINT habitaciones_numero_por_establecimiento UNIQUE (establecimiento_id, numero);
ALTER TABLE tarifas DROP CONSTRAINT tarifas_nombre_key;
ALTER TABLE tarifas ADD CONSTRAINT tarifas_nombre_por_establecimiento UNIQUE (establecimiento_id, nombre);
ALTER TABLE articulos DROP CONSTRAINT articulos_codigo_key;
ALTER TABLE articulos ADD CONSTRAINT articulos_codigo_por_establecimiento UNIQUE (establecimiento_id, codigo);
ALTER TABLE operadores DROP CONSTRAINT operadores_usuario_key;
ALTER TABLE operadores ADD CONSTRAINT operadores_usuario_por_establecimiento UNIQUE (establecimiento_id, usuario);
CREATE UNIQUE INDEX operadores_usuario_plataforma ON operadores (usuario) WHERE establecimiento_id IS NULL;

-- Una guardia abierta y una tarifa vigente por establecimiento (antes, en toda la base).
DROP INDEX guardias_una_abierta;
CREATE UNIQUE INDEX guardias_una_abierta ON guardias (establecimiento_id) WHERE estado = 'Abierta';
DROP INDEX tarifas_una_vigente;
CREATE UNIQUE INDEX tarifas_una_vigente ON tarifas (establecimiento_id) WHERE vigente;

-- La configuracion de la caja pasa de una fila (id = 1) a una fila por establecimiento.
ALTER TABLE configuracion_caja DROP CONSTRAINT configuracion_caja_pkey;
ALTER TABLE configuracion_caja DROP COLUMN id;
ALTER TABLE configuracion_caja ADD PRIMARY KEY (establecimiento_id);

-- ---------------------------------------------------------------------------------------------------
-- Claves foraneas compuestas: cada referencia queda dentro del mismo establecimiento. MATCH SIMPLE (el valor
-- por defecto) no controla las filas con la referencia nula, como los turnos de la v1 sin operador.
-- ---------------------------------------------------------------------------------------------------
ALTER TABLE habitaciones ADD CONSTRAINT habitaciones_est_id UNIQUE (establecimiento_id, id);
ALTER TABLE tarifas ADD CONSTRAINT tarifas_est_id UNIQUE (establecimiento_id, id);
ALTER TABLE turnos ADD CONSTRAINT turnos_est_id UNIQUE (establecimiento_id, id);
ALTER TABLE articulos ADD CONSTRAINT articulos_est_id UNIQUE (establecimiento_id, id);
ALTER TABLE operadores ADD CONSTRAINT operadores_est_id UNIQUE (establecimiento_id, id);
ALTER TABLE guardias ADD CONSTRAINT guardias_est_id UNIQUE (establecimiento_id, id);

ALTER TABLE turnos
    ADD CONSTRAINT turnos_habitacion_mismo_est FOREIGN KEY (establecimiento_id, habitacion_id)
        REFERENCES habitaciones (establecimiento_id, id),
    ADD CONSTRAINT turnos_tarifa_mismo_est FOREIGN KEY (establecimiento_id, tarifa_id)
        REFERENCES tarifas (establecimiento_id, id),
    ADD CONSTRAINT turnos_apertura_mismo_est FOREIGN KEY (establecimiento_id, operador_apertura_id)
        REFERENCES operadores (establecimiento_id, id),
    ADD CONSTRAINT turnos_guardia_mismo_est FOREIGN KEY (establecimiento_id, guardia_apertura_id)
        REFERENCES guardias (establecimiento_id, id),
    ADD CONSTRAINT turnos_cierre_mismo_est FOREIGN KEY (establecimiento_id, operador_cierre_id)
        REFERENCES operadores (establecimiento_id, id);
ALTER TABLE estadias_activas
    ADD CONSTRAINT estadias_turno_mismo_est FOREIGN KEY (establecimiento_id, turno_id)
        REFERENCES turnos (establecimiento_id, id);
ALTER TABLE detalles_consumo
    ADD CONSTRAINT consumos_turno_mismo_est FOREIGN KEY (establecimiento_id, turno_id)
        REFERENCES turnos (establecimiento_id, id),
    ADD CONSTRAINT consumos_articulo_mismo_est FOREIGN KEY (establecimiento_id, articulo_id)
        REFERENCES articulos (establecimiento_id, id),
    ADD CONSTRAINT consumos_operador_mismo_est FOREIGN KEY (establecimiento_id, operador_id)
        REFERENCES operadores (establecimiento_id, id);
ALTER TABLE pagos
    ADD CONSTRAINT pagos_turno_mismo_est FOREIGN KEY (establecimiento_id, turno_id)
        REFERENCES turnos (establecimiento_id, id),
    ADD CONSTRAINT pagos_guardia_mismo_est FOREIGN KEY (establecimiento_id, guardia_id)
        REFERENCES guardias (establecimiento_id, id),
    ADD CONSTRAINT pagos_operador_mismo_est FOREIGN KEY (establecimiento_id, operador_id)
        REFERENCES operadores (establecimiento_id, id);
ALTER TABLE guardias
    ADD CONSTRAINT guardias_operador_mismo_est FOREIGN KEY (establecimiento_id, operador_id)
        REFERENCES operadores (establecimiento_id, id);
ALTER TABLE arqueos_caja
    ADD CONSTRAINT arqueos_guardia_mismo_est FOREIGN KEY (establecimiento_id, guardia_id)
        REFERENCES guardias (establecimiento_id, id),
    ADD CONSTRAINT arqueos_operador_mismo_est FOREIGN KEY (establecimiento_id, operador_id)
        REFERENCES operadores (establecimiento_id, id),
    ADD CONSTRAINT arqueos_confirma_mismo_est FOREIGN KEY (establecimiento_id, confirmado_por_id)
        REFERENCES operadores (establecimiento_id, id);
ALTER TABLE tarifas
    ADD CONSTRAINT tarifas_creada_por_mismo_est FOREIGN KEY (establecimiento_id, creada_por_id)
        REFERENCES operadores (establecimiento_id, id);
ALTER TABLE configuracion_caja
    ADD CONSTRAINT caja_actualizada_por_mismo_est FOREIGN KEY (establecimiento_id, actualizado_por_id)
        REFERENCES operadores (establecimiento_id, id);

-- ---------------------------------------------------------------------------------------------------
-- Row Level Security. Las politicas rigen para motel_app; el dueno de las tablas (migraciones y scripts de
-- administracion) no las tiene aplicadas, como en cualquier tabla con RLS sin FORCE.
-- ---------------------------------------------------------------------------------------------------
DO $$
DECLARE
    tabla TEXT;
BEGIN
    FOREACH tabla IN ARRAY ARRAY['habitaciones', 'tarifas', 'turnos', 'estadias_activas', 'articulos',
                                 'detalles_consumo', 'pagos', 'guardias', 'arqueos_caja', 'configuracion_caja']
    LOOP
        EXECUTE format('ALTER TABLE %I ENABLE ROW LEVEL SECURITY', tabla);
        EXECUTE format(
            'CREATE POLICY aislamiento_establecimiento ON %I TO motel_app '
            'USING (establecimiento_id = app_establecimiento()) '
            'WITH CHECK (establecimiento_id = app_establecimiento())', tabla);
    END LOOP;
END $$;

-- En operadores, la plataforma (establecimiento 0) ve y actualiza (intentos, ultimo acceso) solo a los usuarios de la
-- plataforma. No puede crear uno: el alta no escribe el rol, que queda en OPERADOR, y un OPERADOR sin establecimiento
-- lo rechaza la restriccion operador_de_un_establecimiento.
ALTER TABLE operadores ENABLE ROW LEVEL SECURITY;
CREATE POLICY aislamiento_establecimiento ON operadores TO motel_app
    USING (coalesce(establecimiento_id, 0) = app_establecimiento())
    WITH CHECK (coalesce(establecimiento_id, 0) = app_establecimiento());

-- Los establecimientos se leen sin restriccion (el inicio de sesion busca el codigo antes de saber el
-- establecimiento; solo son nombres y datos de contacto). Los crea la plataforma; los modifica la plataforma o
-- la gerencia del propio establecimiento.
ALTER TABLE establecimientos ENABLE ROW LEVEL SECURITY;
CREATE POLICY lectura ON establecimientos FOR SELECT TO motel_app USING (true);
CREATE POLICY alta_por_plataforma ON establecimientos FOR INSERT TO motel_app
    WITH CHECK (app_establecimiento() = 0);
CREATE POLICY cambio_propio_o_plataforma ON establecimientos FOR UPDATE TO motel_app
    USING (app_establecimiento() IN (0, id)) WITH CHECK (app_establecimiento() IN (0, id));

-- Solo la plataforma suspende o reactiva un establecimiento; la gerencia no puede reactivarse a si misma.
CREATE OR REPLACE FUNCTION check_establecimiento_activo()
RETURNS TRIGGER AS $$
BEGIN
    IF NEW.activo IS DISTINCT FROM OLD.activo AND current_user = 'motel_app' AND app_establecimiento() <> 0 THEN
        RAISE EXCEPTION 'Plataforma: solo la plataforma suspende o reactiva un establecimiento.';
    END IF;
    IF NEW.codigo <> OLD.codigo THEN
        RAISE EXCEPTION 'Plataforma: el codigo de un establecimiento no cambia (lo usan sus inicios de sesion).';
    END IF;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER trigger_establecimiento_activo
BEFORE UPDATE ON establecimientos
FOR EACH ROW
EXECUTE FUNCTION check_establecimiento_activo();

-- ---------------------------------------------------------------------------------------------------
-- Funciones de la plataforma (SECURITY DEFINER: corren con los permisos del dueno de las tablas).
-- ---------------------------------------------------------------------------------------------------

-- La primera gerencia de un establecimiento recien creado. motel_app sigue sin poder escribir la columna rol
-- (migracion 005): esta funcion es la unica via, y solo funciona si el establecimiento de la transaccion no
-- tiene ningun usuario. No sirve para agregar un gerente a un establecimiento que ya opera.
CREATE OR REPLACE FUNCTION crear_gerencia_inicial(p_usuario TEXT, p_nombre_visible TEXT, p_hash_clave TEXT)
RETURNS INTEGER
SECURITY DEFINER
SET search_path = public, pg_temp
AS $$
DECLARE
    est INTEGER := app_establecimiento();
    nuevo_id INTEGER;
BEGIN
    IF est <= 0 OR NOT EXISTS (SELECT 1 FROM establecimientos WHERE id = est) THEN
        RAISE EXCEPTION 'Plataforma: la transaccion no tiene un establecimiento valido.';
    END IF;
    IF EXISTS (SELECT 1 FROM operadores WHERE establecimiento_id = est) THEN
        RAISE EXCEPTION 'Plataforma: el establecimiento % ya tiene usuarios; la gerencia inicial no se repite.', est;
    END IF;
    INSERT INTO operadores (establecimiento_id, usuario, nombre_visible, hash_clave, rol)
    VALUES (est, p_usuario, p_nombre_visible, p_hash_clave, 'ADMINISTRADOR')
    RETURNING id INTO nuevo_id;
    RETURN nuevo_id;
END;
$$ LANGUAGE plpgsql;

-- Resumen de todos los establecimientos para la plataforma: solo cantidades y totales, nunca filas de la
-- operacion (ni turnos, ni pagos, ni patentes).
CREATE OR REPLACE FUNCTION resumen_plataforma()
RETURNS TABLE (
    establecimiento_id INTEGER,
    habitaciones BIGINT,
    ocupadas BIGINT,
    usuarios BIGINT,
    turnos_ultimas_24h BIGINT,
    cobrado_ultimas_24h NUMERIC,
    guardia_abierta BOOLEAN
)
SECURITY DEFINER
SET search_path = public, pg_temp
AS $$
BEGIN
    IF app_establecimiento() <> 0 THEN
        RAISE EXCEPTION 'Plataforma: el resumen es solo para la plataforma.';
    END IF;
    RETURN QUERY
    SELECT e.id,
           (SELECT count(*) FROM habitaciones h WHERE h.establecimiento_id = e.id AND h.activa),
           (SELECT count(*) FROM habitaciones h WHERE h.establecimiento_id = e.id AND h.estado = 'Ocupada'),
           (SELECT count(*) FROM operadores o WHERE o.establecimiento_id = e.id AND o.activo),
           (SELECT count(*) FROM turnos t
             WHERE t.establecimiento_id = e.id AND t.hora_inicio >= now() - interval '24 hours'),
           (SELECT coalesce(sum(p.monto), 0) FROM pagos p
             WHERE p.establecimiento_id = e.id AND p.created_at >= now() - interval '24 hours'),
           EXISTS (SELECT 1 FROM guardias g WHERE g.establecimiento_id = e.id AND g.estado = 'Abierta')
      FROM establecimientos e;
END;
$$ LANGUAGE plpgsql;

REVOKE ALL ON FUNCTION crear_gerencia_inicial(TEXT, TEXT, TEXT) FROM PUBLIC;
REVOKE ALL ON FUNCTION resumen_plataforma() FROM PUBLIC;
GRANT EXECUTE ON FUNCTION crear_gerencia_inicial(TEXT, TEXT, TEXT) TO motel_app;
GRANT EXECUTE ON FUNCTION resumen_plataforma() TO motel_app;
GRANT EXECUTE ON FUNCTION app_establecimiento() TO motel_app;

-- ---------------------------------------------------------------------------------------------------
-- Permisos de motel_app
-- ---------------------------------------------------------------------------------------------------
GRANT SELECT ON establecimientos TO motel_app;
GRANT INSERT (codigo, nombre, domicilio, telefono, leyenda_comprobante, activo, creado_en)
    ON establecimientos TO motel_app;
GRANT UPDATE (nombre, domicilio, telefono, leyenda_comprobante, activo) ON establecimientos TO motel_app;
GRANT USAGE ON SEQUENCE establecimientos_id_seq TO motel_app;

-- Las tablas con permisos por columna necesitan tambien la columna nueva (la aplicacion la envia explicita).
GRANT INSERT (establecimiento_id) ON operadores, tarifas TO motel_app;
-- Un establecimiento nuevo necesita su fila de configuracion de caja (una por establecimiento: clave primaria).
GRANT INSERT ON configuracion_caja TO motel_app;
