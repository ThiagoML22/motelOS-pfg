-- db/migraciones/019_equipos_autorizados.sql
-- Prototipo v3 (Sprint 4, AE4): el conserje entra solo desde equipos que autorizo la gerencia.
-- Se aplica con el usuario dueno de las tablas, despues de 018_lavanderia_otro_resena.sql.
--
-- Filtrar solo por direccion IP no alcanza: dentro del motel, el celular conectado al Wi-Fi tiene una IP de la misma red
-- que la PC de la ventanilla, y desde internet todos los equipos del motel salen con la misma IP publica, que ademas
-- cambia. Por eso cada navegador recibe una marca propia (una cookie aleatoria que la pagina no puede leer; la base
-- guarda solo su resumen SHA-256) y la gerencia autoriza los equipos. La red del motel queda como filtro opcional.
--
-- 1. establecimientos: si el control esta activo y, opcional, las redes desde donde se puede entrar.
-- 2. equipos: cada navegador que uso un conserje, con su estado (pendiente, autorizado o bloqueado).
-- 3. intentos_acceso: cada intento de un conserje desde un equipo o una red no permitidos. Solo agregado; se depura a
--    los 90 dias (son datos del personal: Ley 25.326, se guardan lo justo).

-- 1. El control lo activa la gerencia; arranca apagado para no dejar a nadie afuera al actualizar.
ALTER TABLE establecimientos ADD COLUMN control_equipos BOOLEAN NOT NULL DEFAULT false;
ALTER TABLE establecimientos ADD COLUMN redes_permitidas VARCHAR(200);
GRANT INSERT (control_equipos, redes_permitidas) ON establecimientos TO motel_app;
GRANT UPDATE (control_equipos, redes_permitidas) ON establecimientos TO motel_app;

-- 2. Equipos.
CREATE TABLE equipos (
    id SERIAL PRIMARY KEY,
    establecimiento_id INTEGER NOT NULL DEFAULT app_establecimiento() REFERENCES establecimientos(id),
    huella CHAR(64) NOT NULL CHECK (huella ~ '^[0-9a-f]{64}$'),
    nombre VARCHAR(40),
    estado VARCHAR(12) NOT NULL DEFAULT 'PENDIENTE' CHECK (estado IN ('PENDIENTE', 'AUTORIZADO', 'BLOQUEADO')),
    descripcion VARCHAR(60) NOT NULL,
    ultima_ip VARCHAR(45),
    ultimo_operador_id INTEGER,
    ultimo_uso TIMESTAMP WITH TIME ZONE,
    decidido_por_id INTEGER,
    decidido_en TIMESTAMP WITH TIME ZONE,
    creado_en TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT equipos_una_huella UNIQUE (establecimiento_id, huella),
    CONSTRAINT equipos_id_por_est UNIQUE (establecimiento_id, id),
    -- Un equipo autorizado tiene nombre y quien lo autorizo.
    CONSTRAINT equipos_autorizado_con_nombre CHECK (
        estado <> 'AUTORIZADO' OR (nombre IS NOT NULL AND length(btrim(nombre)) > 0 AND decidido_por_id IS NOT NULL)
    ),
    CONSTRAINT equipos_operador_mismo_est FOREIGN KEY (establecimiento_id, ultimo_operador_id)
        REFERENCES operadores (establecimiento_id, id),
    CONSTRAINT equipos_decidido_mismo_est FOREIGN KEY (establecimiento_id, decidido_por_id)
        REFERENCES operadores (establecimiento_id, id)
);

CREATE INDEX equipos_recientes ON equipos (establecimiento_id, ultimo_uso DESC);

-- Solo la gerencia autoriza o bloquea: la aplicacion no puede cambiar el estado a nombre de un conserje.
CREATE OR REPLACE FUNCTION check_equipo_decision()
RETURNS TRIGGER AS $$
DECLARE
    rol_de VARCHAR(20);
BEGIN
    IF NEW.estado IS DISTINCT FROM OLD.estado AND current_user = 'motel_app' THEN
        SELECT rol INTO rol_de FROM operadores WHERE id = app_operador();
        IF rol_de IS DISTINCT FROM 'ADMINISTRADOR' OR NEW.decidido_por_id IS DISTINCT FROM app_operador() THEN
            RAISE EXCEPTION 'Equipos: solo la gerencia autoriza o bloquea un equipo, y a su nombre.';
        END IF;
        NEW.decidido_en := CURRENT_TIMESTAMP;
    END IF;
    IF NEW.huella IS DISTINCT FROM OLD.huella OR NEW.creado_en IS DISTINCT FROM OLD.creado_en THEN
        RAISE EXCEPTION 'Equipos: la marca y la fecha de alta de un equipo no cambian.';
    END IF;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER trigger_equipo_decision
BEFORE UPDATE ON equipos
FOR EACH ROW
EXECUTE FUNCTION check_equipo_decision();

-- Un equipo nuevo entra siempre pendiente, salvo que lo autorice la gerencia desde su sesion («Autorizar este equipo»).
CREATE OR REPLACE FUNCTION check_equipo_alta()
RETURNS TRIGGER AS $$
DECLARE
    rol_de VARCHAR(20);
BEGIN
    IF NEW.estado <> 'PENDIENTE' AND current_user = 'motel_app' THEN
        SELECT rol INTO rol_de FROM operadores WHERE id = app_operador();
        IF rol_de IS DISTINCT FROM 'ADMINISTRADOR' OR NEW.decidido_por_id IS DISTINCT FROM app_operador() THEN
            RAISE EXCEPTION 'Equipos: un equipo nuevo entra pendiente hasta que lo autorice la gerencia.';
        END IF;
        NEW.decidido_en := CURRENT_TIMESTAMP;
    END IF;
    NEW.creado_en := CURRENT_TIMESTAMP;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER trigger_equipo_alta
BEFORE INSERT ON equipos
FOR EACH ROW
EXECUTE FUNCTION check_equipo_alta();

-- 3. Intentos desde un equipo o una red no permitidos. El usuario se guarda solo si existe (un texto cualquiera podria
-- ser una clave escrita en el campo equivocado).
CREATE TABLE intentos_acceso (
    id BIGSERIAL PRIMARY KEY,
    establecimiento_id INTEGER NOT NULL DEFAULT app_establecimiento() REFERENCES establecimientos(id),
    equipo_id INTEGER,
    operador_id INTEGER,
    clave_correcta BOOLEAN NOT NULL,
    motivo VARCHAR(10) NOT NULL CHECK (motivo IN ('EQUIPO', 'RED')),
    ip VARCHAR(45),
    descripcion VARCHAR(60) NOT NULL,
    creado_en TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT intentos_equipo_mismo_est FOREIGN KEY (establecimiento_id, equipo_id)
        REFERENCES equipos (establecimiento_id, id),
    CONSTRAINT intentos_operador_mismo_est FOREIGN KEY (establecimiento_id, operador_id)
        REFERENCES operadores (establecimiento_id, id)
);

CREATE INDEX intentos_recientes ON intentos_acceso (establecimiento_id, creado_en DESC);

-- La hora es la de la base, y solo se borra lo que paso el plazo de retencion.
CREATE OR REPLACE FUNCTION check_intento_alta()
RETURNS TRIGGER AS $$
BEGIN
    NEW.creado_en := CURRENT_TIMESTAMP;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER trigger_intento_alta
BEFORE INSERT ON intentos_acceso
FOR EACH ROW
EXECUTE FUNCTION check_intento_alta();

CREATE OR REPLACE FUNCTION check_intento_baja()
RETURNS TRIGGER AS $$
BEGIN
    IF OLD.creado_en > CURRENT_TIMESTAMP - INTERVAL '90 days' THEN
        RAISE EXCEPTION 'Intentos de acceso: se guardan 90 dias; antes no se borran.';
    END IF;
    RETURN OLD;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER trigger_intento_baja
BEFORE DELETE ON intentos_acceso
FOR EACH ROW
EXECUTE FUNCTION check_intento_baja();

ALTER TABLE equipos ENABLE ROW LEVEL SECURITY;
CREATE POLICY aislamiento_establecimiento ON equipos TO motel_app
    USING (establecimiento_id = app_establecimiento())
    WITH CHECK (establecimiento_id = app_establecimiento());
ALTER TABLE intentos_acceso ENABLE ROW LEVEL SECURITY;
CREATE POLICY aislamiento_establecimiento ON intentos_acceso TO motel_app
    USING (establecimiento_id = app_establecimiento())
    WITH CHECK (establecimiento_id = app_establecimiento());

-- Equipos: se agregan y se actualizan (uso, nombre, estado), nunca se borran. Intentos: solo agregado, mas la depuracion.
GRANT SELECT, INSERT ON equipos TO motel_app;
GRANT UPDATE (nombre, estado, ultima_ip, ultimo_operador_id, ultimo_uso, decidido_por_id, decidido_en, descripcion)
    ON equipos TO motel_app;
GRANT SELECT, INSERT, DELETE ON intentos_acceso TO motel_app;
GRANT USAGE ON SEQUENCE equipos_id_seq, intentos_acceso_id_seq TO motel_app;
