-- db/migraciones/015_cliente_ampliado.sql
-- Demostracion del Sprint 4 (copia local, no entregada): la pagina del cliente, ampliada.
-- Se aplica con el usuario dueno de las tablas, despues de 014_tarifas_por_franja.sql.
--
-- Un carrito es un solo pedido: sus lineas comparten `lote`. Un pedido pasa por recibido, en camino y entregado. El
-- cliente puede avisar que se queda mas tiempo y pedir la cuenta diciendo como va a pagar: siguen siendo avisos, no
-- mueven plata ni stock. Al irse puede calificar la estadia: sin datos de la persona y sin texto libre.

ALTER TABLE pedidos_cliente DROP CONSTRAINT pedidos_cliente_tipo_check;
ALTER TABLE pedidos_cliente ADD CONSTRAINT pedidos_cliente_tipo_check
    CHECK (tipo IN ('ARTICULO', 'TOALLAS', 'LLAMAR', 'SALIDA', 'TIEMPO'));

ALTER TABLE pedidos_cliente DROP CONSTRAINT pedidos_cliente_estado_check;
ALTER TABLE pedidos_cliente ADD CONSTRAINT pedidos_cliente_estado_check
    CHECK (estado IN ('Pendiente', 'En camino', 'Atendido', 'Rechazado'));

ALTER TABLE pedidos_cliente ADD COLUMN lote UUID;
ALTER TABLE pedidos_cliente ADD COLUMN minutos INTEGER;
ALTER TABLE pedidos_cliente ADD COLUMN medio_pago VARCHAR(20);
ALTER TABLE pedidos_cliente ADD COLUMN llevado_por_id INTEGER;
ALTER TABLE pedidos_cliente ADD COLUMN llevado_en TIMESTAMP WITH TIME ZONE;

ALTER TABLE pedidos_cliente DROP CONSTRAINT pedidos_cliente_atencion_coherente;
ALTER TABLE pedidos_cliente ADD CONSTRAINT pedidos_cliente_atencion_coherente
    CHECK ((estado IN ('Pendiente', 'En camino')) = (atendido_por_id IS NULL AND atendido_en IS NULL));
ALTER TABLE pedidos_cliente ADD CONSTRAINT pedidos_cliente_llevado_coherente
    CHECK ((llevado_por_id IS NULL) = (llevado_en IS NULL) AND (estado <> 'En camino' OR llevado_en IS NOT NULL));
ALTER TABLE pedidos_cliente ADD CONSTRAINT pedidos_cliente_minutos_coherente
    CHECK ((tipo = 'TIEMPO') = (minutos IS NOT NULL) AND (minutos IS NULL OR minutos IN (30, 60, 120)));
ALTER TABLE pedidos_cliente ADD CONSTRAINT pedidos_cliente_medio_coherente
    CHECK (medio_pago IS NULL OR (tipo = 'SALIDA' AND medio_pago IN ('EFECTIVO', 'POSNET', 'MERCADO_PAGO')));
ALTER TABLE pedidos_cliente ADD CONSTRAINT pedidos_cliente_lleva_mismo_est
    FOREIGN KEY (establecimiento_id, llevado_por_id) REFERENCES operadores (establecimiento_id, id);

-- Pendiente -> En camino -> Atendido o Rechazado, una sola vez y sin volver atras. Lo pedido no cambia.
CREATE OR REPLACE FUNCTION check_pedido_cliente_atencion()
RETURNS TRIGGER AS $$
BEGIN
    IF OLD.estado IN ('Atendido', 'Rechazado') THEN
        RAISE EXCEPTION 'Pedidos del cliente: el pedido % ya se atendio.', OLD.id;
    END IF;
    IF NEW.estado = 'Pendiente' OR (OLD.estado = 'En camino' AND NEW.estado = 'En camino') THEN
        RAISE EXCEPTION 'Pedidos del cliente: el pedido % no vuelve atras.', OLD.id;
    END IF;
    IF (NEW.establecimiento_id, NEW.turno_id, NEW.tipo, NEW.articulo_id, NEW.cantidad, NEW.creado_en, NEW.lote,
        NEW.minutos, NEW.medio_pago)
       IS DISTINCT FROM (OLD.establecimiento_id, OLD.turno_id, OLD.tipo, OLD.articulo_id, OLD.cantidad, OLD.creado_en,
                         OLD.lote, OLD.minutos, OLD.medio_pago) THEN
        RAISE EXCEPTION 'Pedidos del cliente: lo pedido no se modifica.';
    END IF;
    IF current_user = 'motel_app' THEN
        IF NEW.estado = 'En camino' AND NEW.llevado_por_id IS DISTINCT FROM app_operador() THEN
            RAISE EXCEPTION 'Pedidos del cliente: se llevan solo a nombre del usuario de la sesion.';
        END IF;
        IF NEW.estado IN ('Atendido', 'Rechazado') AND NEW.atendido_por_id IS DISTINCT FROM app_operador() THEN
            RAISE EXCEPTION 'Pedidos del cliente: se atienden solo a nombre del usuario de la sesion.';
        END IF;
    END IF;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

GRANT UPDATE (llevado_por_id, llevado_en) ON pedidos_cliente TO motel_app;

-- Lo que la gerencia le cuenta al cliente en su pagina.
ALTER TABLE establecimientos ADD COLUMN wifi_nombre VARCHAR(60);
ALTER TABLE establecimientos ADD COLUMN wifi_clave VARCHAR(60);
ALTER TABLE establecimientos ADD COLUMN bienvenida VARCHAR(200);
GRANT INSERT (wifi_nombre, wifi_clave, bienvenida) ON establecimientos TO motel_app;
GRANT UPDATE (wifi_nombre, wifi_clave, bienvenida) ON establecimientos TO motel_app;

-- Una calificacion por turno. No guarda datos de la persona ni texto libre: un puntaje y lo que fallo.
CREATE TABLE calificaciones (
    id SERIAL PRIMARY KEY,
    establecimiento_id INTEGER NOT NULL DEFAULT app_establecimiento() REFERENCES establecimientos(id),
    turno_id UUID NOT NULL,
    habitacion_id INTEGER NOT NULL,
    puntaje SMALLINT NOT NULL CHECK (puntaje BETWEEN 1 AND 5),
    -- Mascara de lo que fallo: limpieza = 1, ruido = 2, aire = 4, TV o Wi-Fi = 8, bano = 16, atencion = 32.
    problemas SMALLINT NOT NULL DEFAULT 0 CHECK (problemas BETWEEN 0 AND 63),
    creado_en TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT calificaciones_una_por_turno UNIQUE (establecimiento_id, turno_id),
    CONSTRAINT calificaciones_turno_mismo_est FOREIGN KEY (establecimiento_id, turno_id)
        REFERENCES turnos (establecimiento_id, id),
    CONSTRAINT calificaciones_habitacion_mismo_est FOREIGN KEY (establecimiento_id, habitacion_id)
        REFERENCES habitaciones (establecimiento_id, id)
);

CREATE INDEX calificaciones_por_fecha ON calificaciones (establecimiento_id, creado_en);

-- Se califica durante la estadia o hasta una hora despues del cobro, la habitacion es la del turno y la hora la pone la base.
CREATE OR REPLACE FUNCTION check_calificacion_alta()
RETURNS TRIGGER AS $$
DECLARE
    el_turno turnos%ROWTYPE;
BEGIN
    SELECT * INTO el_turno FROM turnos WHERE id = NEW.turno_id;
    IF NOT FOUND OR el_turno.habitacion_id <> NEW.habitacion_id THEN
        RAISE EXCEPTION 'Calificaciones: la habitacion no es la del turno.';
    END IF;
    IF el_turno.estado <> 'En Curso'
       AND (el_turno.hora_fin IS NULL OR el_turno.hora_fin < CURRENT_TIMESTAMP - INTERVAL '60 minutes') THEN
        RAISE EXCEPTION 'Calificaciones: paso el tiempo para calificar esta estadia.';
    END IF;
    NEW.creado_en := CURRENT_TIMESTAMP;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER trigger_calificacion_alta
BEFORE INSERT ON calificaciones
FOR EACH ROW
EXECUTE FUNCTION check_calificacion_alta();

ALTER TABLE calificaciones ENABLE ROW LEVEL SECURITY;
CREATE POLICY aislamiento_establecimiento ON calificaciones TO motel_app
    USING (establecimiento_id = app_establecimiento())
    WITH CHECK (establecimiento_id = app_establecimiento());

GRANT SELECT, INSERT ON calificaciones TO motel_app;
GRANT USAGE ON SEQUENCE calificaciones_id_seq TO motel_app;
