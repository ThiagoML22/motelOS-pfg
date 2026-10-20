-- db/migraciones/002_v2_caja.sql
-- Prototipo v2 (AE3): operadores, guardias de 8 h, arqueo de caja ciego y atribucion de cada operacion.
-- Requisitos: RF-08, RF-09, RNF-04. Reglas: RN-RES-02, RN-RES-03, RN-DER-03 y RN-DER-04.
-- Se aplica con el usuario dueno de las tablas, despues de 001_esquema_v1.sql.

-- Precondicion: la migracion se hace en un recambio, sin turnos en curso. Los turnos de la v1 no tienen
-- operador (la v1 no tenia autenticacion) y la restriccion de atribucion rige para lo que se modifique.
DO $$
BEGIN
    IF EXISTS (SELECT 1 FROM turnos WHERE estado = 'En Curso') THEN
        RAISE EXCEPTION 'Migracion 002: hay turnos En Curso. Cerrarlos antes de migrar.';
    END IF;
END $$;

-- ---------------------------------------------------------------------------------------------------
-- Operadores (RNF-04). Personal del motel: solo usuario y nombre visible, sin DNI ni otros datos.
-- No se borran (la historia los referencia): se desactivan. El alta y el cambio de rol los hace el
-- dueno de las tablas (src/backend/scripts/crear_operador.py); la aplicacion no tiene ese permiso.
-- ---------------------------------------------------------------------------------------------------
CREATE TABLE operadores (
    id SERIAL PRIMARY KEY,
    usuario VARCHAR(40) UNIQUE NOT NULL CHECK (usuario ~ '^[a-z0-9._-]{3,40}$'),
    nombre_visible VARCHAR(60) NOT NULL,
    hash_clave VARCHAR(255) NOT NULL,
    rol VARCHAR(20) NOT NULL CHECK (rol IN ('OPERADOR', 'ADMINISTRADOR')),
    activo BOOLEAN NOT NULL DEFAULT TRUE,
    intentos_fallidos INTEGER NOT NULL DEFAULT 0 CHECK (intentos_fallidos >= 0),
    bloqueado_hasta TIMESTAMP WITH TIME ZONE,
    ultimo_acceso TIMESTAMP WITH TIME ZONE,
    creado_en TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT CURRENT_TIMESTAMP
);

-- ---------------------------------------------------------------------------------------------------
-- Guardias: la caja de un operador durante su franja de 8 h (06:00, 14:00 o 22:00).
-- Hay una sola ventanilla, por lo tanto una sola guardia abierta a la vez.
-- ---------------------------------------------------------------------------------------------------
CREATE TABLE guardias (
    id SERIAL PRIMARY KEY,
    operador_id INTEGER NOT NULL REFERENCES operadores(id),
    franja VARCHAR(5) NOT NULL CHECK (franja IN ('06:00', '14:00', '22:00')),
    fondo_inicial NUMERIC(12, 2) NOT NULL DEFAULT 0 CHECK (fondo_inicial >= 0),
    abierta_en TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT CURRENT_TIMESTAMP,
    cerrada_en TIMESTAMP WITH TIME ZONE,
    estado VARCHAR(10) NOT NULL DEFAULT 'Abierta' CHECK (estado IN ('Abierta', 'Cerrada')),
    CONSTRAINT guardia_cierre_coherente CHECK ((estado = 'Abierta') = (cerrada_en IS NULL))
);

CREATE UNIQUE INDEX guardias_una_abierta ON guardias (estado) WHERE estado = 'Abierta';

-- ---------------------------------------------------------------------------------------------------
-- Arqueo de caja (RF-08, RF-09): uno por guardia. El operador declara lo que cuenta; la base calcula lo
-- que registra el sistema, la diferencia y la categoria (RN-DER-03), y despues el arqueo no cambia.
-- ---------------------------------------------------------------------------------------------------
CREATE TABLE arqueos_caja (
    id SERIAL PRIMARY KEY,
    guardia_id INTEGER NOT NULL UNIQUE REFERENCES guardias(id),
    operador_id INTEGER NOT NULL REFERENCES operadores(id),
    declarado_efectivo NUMERIC(12, 2) NOT NULL CHECK (declarado_efectivo >= 0),
    declarado_posnet NUMERIC(12, 2) NOT NULL DEFAULT 0 CHECK (declarado_posnet >= 0),
    declarado_mercado_pago NUMERIC(12, 2) NOT NULL DEFAULT 0 CHECK (declarado_mercado_pago >= 0),
    total_declarado NUMERIC(12, 2) NOT NULL,
    sistema_efectivo NUMERIC(12, 2) NOT NULL DEFAULT 0,
    sistema_posnet NUMERIC(12, 2) NOT NULL DEFAULT 0,
    sistema_mercado_pago NUMERIC(12, 2) NOT NULL DEFAULT 0,
    total_sistema NUMERIC(12, 2) NOT NULL DEFAULT 0,
    diferencia NUMERIC(12, 2) NOT NULL,
    categoria VARCHAR(10) NOT NULL CHECK (categoria IN ('Correcto', 'Faltante', 'Sobrante')),
    confirmado_en TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT arqueo_total_declarado CHECK (
        total_declarado = declarado_efectivo + declarado_posnet + declarado_mercado_pago),
    CONSTRAINT arqueo_total_sistema CHECK (
        total_sistema = sistema_efectivo + sistema_posnet + sistema_mercado_pago),
    -- RN-DER-03: diferencia = total declarado - total del sistema, y la categoria sigue su signo.
    CONSTRAINT arqueo_diferencia CHECK (diferencia = total_declarado - total_sistema),
    CONSTRAINT arqueo_categoria CHECK (
        (diferencia = 0 AND categoria = 'Correcto')
        OR (diferencia < 0 AND categoria = 'Faltante')
        OR (diferencia > 0 AND categoria = 'Sobrante'))
);

-- ---------------------------------------------------------------------------------------------------
-- Atribucion (RNF-04 y RN-DER-04): quien abre el turno, quien despacha cada consumo y quien cobra, y en
-- que guardia. El pago se imputa a la guardia abierta en la ventanilla al registrarse el cobro.
-- NOT VALID: rige para las filas nuevas o modificadas; las de la v1 (sin autenticacion) no se reescriben.
-- ---------------------------------------------------------------------------------------------------
ALTER TABLE turnos
    ADD COLUMN operador_apertura_id INTEGER REFERENCES operadores(id),
    ADD COLUMN guardia_apertura_id INTEGER REFERENCES guardias(id),
    ADD COLUMN operador_cierre_id INTEGER REFERENCES operadores(id);
ALTER TABLE turnos ADD CONSTRAINT turnos_apertura_atribuida
    CHECK (operador_apertura_id IS NOT NULL AND guardia_apertura_id IS NOT NULL) NOT VALID;
ALTER TABLE turnos ADD CONSTRAINT turnos_cierre_atribuido
    CHECK (estado <> 'FINALIZADO' OR operador_cierre_id IS NOT NULL) NOT VALID;

ALTER TABLE detalles_consumo ADD COLUMN operador_id INTEGER REFERENCES operadores(id);
ALTER TABLE detalles_consumo ADD CONSTRAINT consumos_atribuidos CHECK (operador_id IS NOT NULL) NOT VALID;

ALTER TABLE pagos
    ADD COLUMN operador_id INTEGER REFERENCES operadores(id),
    ADD COLUMN guardia_id INTEGER REFERENCES guardias(id);
ALTER TABLE pagos ADD CONSTRAINT pagos_atribuidos
    CHECK (operador_id IS NOT NULL AND guardia_id IS NOT NULL) NOT VALID;

CREATE INDEX pagos_por_guardia ON pagos (guardia_id);

-- ---------------------------------------------------------------------------------------------------
-- Triggers
-- ---------------------------------------------------------------------------------------------------

-- Un pago solo entra a la caja de la guardia abierta, a nombre de su operador y sobre un turno en curso.
-- FOR SHARE espera a un arqueo que se este confirmando: si la guardia se cierra, el pago se rechaza.
CREATE OR REPLACE FUNCTION check_pago_en_guardia_abierta()
RETURNS TRIGGER AS $$
DECLARE
    g RECORD;
    estado_turno VARCHAR(20);
BEGIN
    IF NEW.guardia_id IS NULL THEN
        RETURN NEW;  -- lo rechaza la restriccion pagos_atribuidos
    END IF;
    SELECT estado, operador_id INTO g FROM guardias WHERE id = NEW.guardia_id FOR SHARE;
    IF g.estado IS DISTINCT FROM 'Abierta' THEN
        RAISE EXCEPTION 'RN-RES-02: La guardia % esta cerrada; su caja ya fue arqueada.', NEW.guardia_id;
    END IF;
    IF NEW.operador_id IS DISTINCT FROM g.operador_id THEN
        RAISE EXCEPTION 'RNF-04: El pago debe registrarlo el operador de la guardia abierta.';
    END IF;
    SELECT estado INTO estado_turno FROM turnos WHERE id = NEW.turno_id;
    IF estado_turno IS DISTINCT FROM 'En Curso' THEN
        RAISE EXCEPTION 'RN-RES-01: No se registran pagos sobre un turno que no esta En Curso.';
    END IF;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER trigger_pago_en_guardia_abierta
BEFORE INSERT ON pagos
FOR EACH ROW
EXECUTE FUNCTION check_pago_en_guardia_abierta();

-- El arqueo lo confirma el operador de la guardia abierta. La base calcula el total del sistema con los
-- pagos de la guardia (mas el fondo inicial en efectivo), la diferencia y la categoria: lo que envie la
-- aplicacion en esas columnas se reemplaza. Bloquea la guardia para que no entren pagos durante el calculo.
CREATE OR REPLACE FUNCTION calcular_arqueo()
RETURNS TRIGGER AS $$
DECLARE
    g RECORD;
BEGIN
    SELECT estado, operador_id, fondo_inicial INTO g FROM guardias WHERE id = NEW.guardia_id FOR UPDATE;
    IF g.estado IS DISTINCT FROM 'Abierta' THEN
        RAISE EXCEPTION 'RN-RES-02: La guardia % ya esta cerrada.', NEW.guardia_id;
    END IF;
    IF NEW.operador_id IS DISTINCT FROM g.operador_id THEN
        RAISE EXCEPTION 'RNF-04: Solo el operador de la guardia confirma su arqueo.';
    END IF;

    SELECT g.fondo_inicial + COALESCE(SUM(monto) FILTER (WHERE medio_pago = 'EFECTIVO'), 0),
           COALESCE(SUM(monto) FILTER (WHERE medio_pago = 'POSNET'), 0),
           COALESCE(SUM(monto) FILTER (WHERE medio_pago = 'MERCADO_PAGO'), 0)
      INTO NEW.sistema_efectivo, NEW.sistema_posnet, NEW.sistema_mercado_pago
      FROM pagos WHERE guardia_id = NEW.guardia_id;

    NEW.total_declarado := NEW.declarado_efectivo + NEW.declarado_posnet + NEW.declarado_mercado_pago;
    NEW.total_sistema := NEW.sistema_efectivo + NEW.sistema_posnet + NEW.sistema_mercado_pago;
    NEW.diferencia := NEW.total_declarado - NEW.total_sistema;
    NEW.categoria := CASE WHEN NEW.diferencia = 0 THEN 'Correcto'
                          WHEN NEW.diferencia < 0 THEN 'Faltante'
                          ELSE 'Sobrante' END;
    NEW.confirmado_en := CURRENT_TIMESTAMP;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER trigger_calcular_arqueo
BEFORE INSERT ON arqueos_caja
FOR EACH ROW
EXECUTE FUNCTION calcular_arqueo();

-- RN-RES-02: confirmado el arqueo, no admite UPDATE ni DELETE.
CREATE OR REPLACE FUNCTION check_arqueo_inmutable()
RETURNS TRIGGER AS $$
BEGIN
    RAISE EXCEPTION 'RN-RES-02: Un arqueo confirmado no se puede modificar ni eliminar.';
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER trigger_arqueo_inmutable
BEFORE UPDATE OR DELETE ON arqueos_caja
FOR EACH ROW
EXECUTE FUNCTION check_arqueo_inmutable();

-- Una guardia solo pasa de Abierta a Cerrada, y solo con su arqueo confirmado. Cerrada, no cambia mas.
-- Los datos de apertura (operador, franja, fondo, hora) no se modifican nunca. No se borran guardias.
CREATE OR REPLACE FUNCTION check_guardia()
RETURNS TRIGGER AS $$
BEGIN
    IF TG_OP = 'DELETE' THEN
        RAISE EXCEPTION 'RN-RES-02: Las guardias no se eliminan.';
    END IF;
    IF OLD.estado = 'Cerrada' THEN
        RAISE EXCEPTION 'RN-RES-02: Una guardia cerrada no se puede reabrir ni modificar.';
    END IF;
    IF NEW.operador_id <> OLD.operador_id OR NEW.franja <> OLD.franja
       OR NEW.fondo_inicial <> OLD.fondo_inicial OR NEW.abierta_en <> OLD.abierta_en THEN
        RAISE EXCEPTION 'RN-RES-02: Los datos de apertura de la guardia no se modifican.';
    END IF;
    IF NEW.estado = 'Cerrada'
       AND NOT EXISTS (SELECT 1 FROM arqueos_caja WHERE guardia_id = NEW.id) THEN
        RAISE EXCEPTION 'RF-08: La guardia % no se cierra sin su arqueo confirmado.', NEW.id;
    END IF;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER trigger_guardia
BEFORE UPDATE OR DELETE ON guardias
FOR EACH ROW
EXECUTE FUNCTION check_guardia();

-- ---------------------------------------------------------------------------------------------------
-- Permisos del rol de la aplicacion (minimos, por columna donde corresponde).
-- motel_app no puede crear operadores, cambiar roles ni claves, reabrir guardias, ni modificar o borrar
-- arqueos. Esto es lo que impide escalar privilegios desde la aplicacion, aunque alguien lograra
-- ejecutar SQL con su conexion.
-- ---------------------------------------------------------------------------------------------------
GRANT SELECT ON operadores TO motel_app;
GRANT UPDATE (intentos_fallidos, bloqueado_hasta, ultimo_acceso) ON operadores TO motel_app;

GRANT SELECT, INSERT ON guardias TO motel_app;
GRANT UPDATE (estado, cerrada_en) ON guardias TO motel_app;
GRANT USAGE ON SEQUENCE guardias_id_seq TO motel_app;

GRANT SELECT, INSERT ON arqueos_caja TO motel_app;
GRANT USAGE ON SEQUENCE arqueos_caja_id_seq TO motel_app;

-- Correccion de la v1.2: la creacion de articulos (inventario) necesita INSERT y la secuencia.
GRANT INSERT ON articulos TO motel_app;
GRANT USAGE ON SEQUENCE articulos_id_seq TO motel_app;
