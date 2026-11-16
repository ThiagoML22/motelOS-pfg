-- db/migraciones/020_qr_fijo_habitacion.sql
-- Demostracion del Sprint 4 (copia local, no entregada): un QR fijo en cada habitacion, sin hablar con la ventanilla.
-- Se aplica con el usuario dueno de las tablas, despues de 019_equipos_autorizados.sql.
--
-- El QR fijo dice que habitacion es (firmado por el servidor, con una version que la gerencia puede cambiar si se
-- filtra). El primer celular que lo escanea durante una estadia queda vinculado a ella con una cookie aleatoria (la
-- base guarda solo su resumen SHA-256); los demas ven solo la carta, como si la habitacion estuviera libre. Desde un
-- celular vinculado se suman los otros. Al terminar la estadia, el vinculo deja de abrir nada.
--
-- 1. habitaciones.qr_version: cambiarla invalida el QR impreso de esa habitacion.
-- 2. vinculos_cliente: que celular quedo vinculado a que estadia. Se agrega y se revoca; no se borra hasta los 30 dias.
-- 3. pedidos_cliente: el aviso «no puedo ver mi estadia» (tipo VINCULO), que la ventanilla resuelve liberando el QR.

-- 1. Version del QR impreso (motel_app ya puede actualizar habitaciones: migracion 001).
ALTER TABLE habitaciones ADD COLUMN qr_version INTEGER NOT NULL DEFAULT 1 CHECK (qr_version >= 1);

-- 2. Celulares vinculados a una estadia.
CREATE TABLE vinculos_cliente (
    id BIGSERIAL PRIMARY KEY,
    establecimiento_id INTEGER NOT NULL DEFAULT app_establecimiento() REFERENCES establecimientos(id),
    turno_id UUID NOT NULL,
    huella CHAR(64) NOT NULL CHECK (huella ~ '^[0-9a-f]{64}$'),
    origen VARCHAR(10) NOT NULL CHECK (origen IN ('QR', 'INVITADO')),
    creado_en TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT CURRENT_TIMESTAMP,
    revocado_en TIMESTAMP WITH TIME ZONE,
    revocado_por_id INTEGER,
    CONSTRAINT vinculos_un_celular_por_estadia UNIQUE (establecimiento_id, turno_id, huella),
    -- Lo revoca la ventanilla, a nombre de quien atiende.
    CONSTRAINT vinculos_revocacion_coherente CHECK ((revocado_en IS NULL) = (revocado_por_id IS NULL)),
    CONSTRAINT vinculos_turno_mismo_est FOREIGN KEY (establecimiento_id, turno_id)
        REFERENCES turnos (establecimiento_id, id),
    CONSTRAINT vinculos_revoca_mismo_est FOREIGN KEY (establecimiento_id, revocado_por_id)
        REFERENCES operadores (establecimiento_id, id)
);

CREATE INDEX vinculos_del_turno ON vinculos_cliente (establecimiento_id, turno_id);
CREATE INDEX vinculos_del_celular ON vinculos_cliente (establecimiento_id, huella, creado_en DESC);

-- Un celular nuevo se vincula solo a una estadia en curso, y la hora la pone la base.
CREATE OR REPLACE FUNCTION check_vinculo_alta()
RETURNS TRIGGER AS $$
DECLARE
    estado_turno VARCHAR(20);
BEGIN
    SELECT estado INTO estado_turno FROM turnos WHERE id = NEW.turno_id;
    IF estado_turno IS DISTINCT FROM 'En Curso' THEN
        RAISE EXCEPTION 'Vinculos del cliente: la estadia no esta en curso.';
    END IF;
    IF NEW.revocado_en IS NOT NULL OR NEW.revocado_por_id IS NOT NULL THEN
        RAISE EXCEPTION 'Vinculos del cliente: un vinculo nuevo no nace revocado.';
    END IF;
    NEW.creado_en := CURRENT_TIMESTAMP;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER trigger_vinculo_alta
BEFORE INSERT ON vinculos_cliente
FOR EACH ROW
EXECUTE FUNCTION check_vinculo_alta();

-- Solo se revoca, una vez, a nombre del usuario de la sesion; lo demas no cambia.
CREATE OR REPLACE FUNCTION check_vinculo_revocacion()
RETURNS TRIGGER AS $$
BEGIN
    IF OLD.revocado_en IS NOT NULL THEN
        RAISE EXCEPTION 'Vinculos del cliente: el vinculo % ya se revoco.', OLD.id;
    END IF;
    IF (NEW.establecimiento_id, NEW.turno_id, NEW.huella, NEW.origen, NEW.creado_en)
       IS DISTINCT FROM (OLD.establecimiento_id, OLD.turno_id, OLD.huella, OLD.origen, OLD.creado_en) THEN
        RAISE EXCEPTION 'Vinculos del cliente: solo se puede revocar un vinculo.';
    END IF;
    IF current_user = 'motel_app' AND NEW.revocado_por_id IS DISTINCT FROM app_operador() THEN
        RAISE EXCEPTION 'Vinculos del cliente: se revocan solo a nombre del usuario de la sesion.';
    END IF;
    NEW.revocado_en := CURRENT_TIMESTAMP;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER trigger_vinculo_revocacion
BEFORE UPDATE ON vinculos_cliente
FOR EACH ROW
EXECUTE FUNCTION check_vinculo_revocacion();

-- Se guardan 30 dias (alcanzan para la regla de las 12 horas y para revisar un reclamo); despues se depuran.
CREATE OR REPLACE FUNCTION check_vinculo_baja()
RETURNS TRIGGER AS $$
BEGIN
    IF OLD.creado_en > CURRENT_TIMESTAMP - INTERVAL '30 days' THEN
        RAISE EXCEPTION 'Vinculos del cliente: se guardan 30 dias; antes no se borran.';
    END IF;
    RETURN OLD;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER trigger_vinculo_baja
BEFORE DELETE ON vinculos_cliente
FOR EACH ROW
EXECUTE FUNCTION check_vinculo_baja();

ALTER TABLE vinculos_cliente ENABLE ROW LEVEL SECURITY;
CREATE POLICY aislamiento_establecimiento ON vinculos_cliente TO motel_app
    USING (establecimiento_id = app_establecimiento())
    WITH CHECK (establecimiento_id = app_establecimiento());

GRANT SELECT, INSERT, DELETE ON vinculos_cliente TO motel_app;
GRANT UPDATE (revocado_en, revocado_por_id) ON vinculos_cliente TO motel_app;
GRANT USAGE ON SEQUENCE vinculos_cliente_id_seq TO motel_app;

-- 3. El aviso «estoy en la habitacion y no veo mi estadia».
ALTER TABLE pedidos_cliente DROP CONSTRAINT pedidos_cliente_tipo_check;
ALTER TABLE pedidos_cliente ADD CONSTRAINT pedidos_cliente_tipo_check
    CHECK (tipo IN ('ARTICULO', 'TOALLAS', 'LLAMAR', 'SALIDA', 'TIEMPO', 'VINCULO'));
